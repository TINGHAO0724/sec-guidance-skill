"""
Light-mode SEC guidance extractor: self-contained, no ES / Ollama / RAG infra.

Fetches the most recent filing for a ticker directly from EDGAR (10-Q/10-K for
domestic filers, 20-F/40-F/6-K for foreign private issuers — `--form auto`
walks that chain), chunks the filing in memory, ranks passages with BM25, and
asks Claude (or OpenAI) to answer with inline citations.

Trades ~20% answer quality vs the heavy pipeline for zero-infra setup — good
enough for a single-ticker one-off lookup. For 100+ tickers/day, use the heavy
pipeline (mode=heavy, requires SEC_PIPELINE_DIR).

With no LLM API key set, degrades to retrieval-only output (ranked passages
with quotes) instead of failing.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: `requests` is required. Install: pip install -r requirements.txt")
    sys.exit(1)

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("ERROR: `beautifulsoup4` is required. Install: pip install -r requirements.txt")
    sys.exit(1)

try:
    from rank_bm25 import BM25Okapi
except ImportError:
    print("ERROR: `rank_bm25` is required. Install: pip install -r requirements.txt")
    sys.exit(1)

UA = os.environ.get(
    "SEC_GUIDANCE_UA",
    "sec-guidance-skill contact@example.com",
)
HEADERS = {"User-Agent": UA}
CACHE_DIR = Path.home() / ".cache" / "sec-guidance"
CHUNK_CHARS = 1500
CHUNK_OVERLAP = 200
DEFAULT_TOP_K = 8

# `--form auto` tries these in order; foreign private issuers file 20-F/40-F
# (annual) and 6-K (interim) instead of 10-K/10-Q.
FORM_CHAIN = ["10-Q", "10-K", "20-F", "40-F", "6-K"]
FORM_CHOICES = ["auto"] + FORM_CHAIN

# Chunks with >=3 hits are counted as "guidance-dense" for the recall check.
GUIDANCE_KEYWORD_RE = re.compile(
    r"\b(guidance|outlook|expect(?:s|ed|ing)?|anticipat\w*|forecast\w*|"
    r"target(?:s|ed|ing)?|project(?:s|ed|ing)?|fiscal (?:year )?20\d\d)\b",
    re.IGNORECASE,
)

GUIDANCE_QUERIES = [
    "What is management's guidance and outlook for future revenue and earnings?",
    "What forward-looking statements did management make about future performance expectations?",
    "What did management say about expected gross margins and profitability going forward?",
    "What new product launches, services, or business expansions did management project or plan?",
    "What macroeconomic conditions, risks, or uncertainties did management highlight for upcoming quarters?",
]


def _cache_path(key: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", key)
    return CACHE_DIR / safe


def _get(url: str, timeout: int = 30) -> requests.Response:
    """GET with retry/backoff — EDGAR throttles (429) and hiccups under load."""
    last = ""
    for pause in (0, 2, 5):
        if pause:
            time.sleep(pause)
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout)
            if r.status_code in (429, 500, 502, 503, 504):
                last = f"HTTP {r.status_code}"
                continue
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            last = str(e)
    print(f"ERROR: EDGAR request failed after 3 attempts ({last}): {url}")
    if "429" in last:
        print("Hint: set SEC_GUIDANCE_UA=\"yourname you@example.com\" — SEC "
              "rate-limits generic User-Agents aggressively.")
    sys.exit(1)


def _lookup_cik(ticker: str) -> str | None:
    """Resolve ticker → 10-digit CIK from SEC's bulk file, cached."""
    cache = _cache_path("company_tickers.json")
    if not cache.exists() or (time.time() - cache.stat().st_mtime) > 86400:
        r = _get("https://www.sec.gov/files/company_tickers.json")
        cache.write_bytes(r.content)
    data = json.loads(cache.read_text())
    for rec in data.values():
        if rec.get("ticker", "").upper() == ticker.upper():
            return f"{int(rec['cik_str']):010d}"
    return None


def _recent_filings(cik: str) -> dict:
    """Fetch the submissions index once per run (recent filings block)."""
    r = _get(f"https://data.sec.gov/submissions/CIK{cik}.json")
    return r.json().get("filings", {}).get("recent", {})


def _latest_filing(recent: dict, cik: str, form: str) -> dict | None:
    """Return {accession, filing_date, primary_doc_url} for the most recent form."""
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accs = recent.get("accessionNumber", [])
    docs = recent.get("primaryDocument", [])
    form_norm = form.replace("-", "").upper()
    for f, d, acc, doc in zip(forms, dates, accs, docs):
        if f.replace("-", "").upper() == form_norm:
            acc_nodash = acc.replace("-", "")
            url = (f"https://www.sec.gov/Archives/edgar/data/"
                   f"{int(cik)}/{acc_nodash}/{doc}")
            return {"accession": acc, "filing_date": d, "primary_doc_url": url}
    return None


def _resolve_filing(cik: str, form: str) -> tuple[str | None, dict | None]:
    """Resolve `auto` through the domestic→foreign form chain."""
    recent = _recent_filings(cik)
    for f in (FORM_CHAIN if form == "auto" else [form]):
        filing = _latest_filing(recent, cik, f)
        if filing:
            return f, filing
    return None, None


def _fetch_and_extract_text(url: str, filing_key: str) -> str:
    """Fetch primary doc, strip HTML/XBRL, return plain text. Cached per filing."""
    cache = _cache_path(f"filing__{filing_key}.txt")
    if cache.exists():
        return cache.read_text()
    r = _get(url, timeout=60)
    soup = BeautifulSoup(r.text, "html.parser")
    for tag in soup(["script", "style", "meta", "link"]):
        tag.decompose()
    # Inject paragraph breaks before block-level tags so text isn't a wall
    for block in soup.find_all(["p", "div", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6"]):
        block.insert_before("\n\n")
    text = soup.get_text(" ")
    # Collapse whitespace but keep paragraph breaks
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    # Strip XBRL namespace noise lines
    lines = [ln for ln in text.split("\n")
             if not re.match(r"^(xmlns|xbrli:|iso4217:|us-gaap:)", ln.strip())]
    text = "\n".join(lines)
    cache.write_text(text)
    return text


def _chunk(text: str, size: int = CHUNK_CHARS, overlap: int = CHUNK_OVERLAP) -> list[str]:
    chunks = []
    i = 0
    n = len(text)
    while i < n:
        chunks.append(text[i:i + size])
        if i + size >= n:
            break
        i += size - overlap
    return chunks


def _bm25_topk(query: str, chunks: list[str], k: int) -> list[tuple[int, float, str]]:
    tokenized = [re.findall(r"\w+", c.lower()) for c in chunks]
    bm25 = BM25Okapi(tokenized)
    q_tok = re.findall(r"\w+", query.lower())
    scores = bm25.get_scores(q_tok)
    ranked = sorted(enumerate(scores), key=lambda x: -x[1])[:k]
    return [(idx, float(score), chunks[idx]) for idx, score in ranked]


def _snippet(text: str, chars: int = 180) -> str:
    return re.sub(r"\s+", " ", text.strip())[:chars]


def _recall_note(chunks: list[str], picked: set[int]) -> tuple[str, dict]:
    """Coverage of guidance-dense chunks by the retrieved set — a cheap
    honesty check on BM25, not a guarantee of completeness."""
    hits = [len(GUIDANCE_KEYWORD_RE.findall(c)) for c in chunks]
    # Adaptive threshold: terse filings (e.g. AAPL 10-Qs) never reach 3
    # keywords per chunk — fall back so the check doesn't go blind on them.
    threshold = 3 if any(h >= 3 for h in hits) else 2
    dense = [i for i, h in enumerate(hits) if h >= threshold]
    stats = {"guidance_dense_chunks": len(dense),
             "keyword_threshold": threshold,
             "covered": len(picked & set(dense)),
             "missed_chunk_indices": sorted(set(dense) - picked)[:10]}
    if not dense:
        return "Recall check: no guidance-dense chunks detected in this filing.", stats
    note = (f"Recall check: retrieved set covers {stats['covered']}/{len(dense)} "
            f"guidance-dense chunks")
    if stats["covered"] / len(dense) < 0.3:
        note += ("  ⚠ LOW — raise --top-k or ask a more specific --query; "
                 f"unretrieved dense chunks start at {stats['missed_chunk_indices'][:5]}")
    return note, stats


def _pick_llm() -> tuple[str | None, str | None]:
    """Return (provider, model). Prefer Anthropic, fall back to OpenAI.
    Returns (None, None) when no key is set — caller degrades to retrieval-only."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic", os.environ.get("SEC_GUIDANCE_MODEL", "claude-sonnet-4-6")
    if os.environ.get("OPENAI_API_KEY"):
        return "openai", os.environ.get("SEC_GUIDANCE_MODEL", "gpt-4o-mini")
    return None, None


def _ask_llm(query: str, passages: list[tuple[int, float, str]],
             provider: str, model: str) -> str:
    """Send prompt + numbered passages to the LLM, return answer text."""
    context = "\n\n".join(
        f"[{i + 1}] (chunk #{idx}, bm25={score:.2f})\n{text}"
        for i, (idx, score, text) in enumerate(passages)
    )
    system = ("You are a financial analyst extracting forward-looking guidance "
              "from SEC filings. Answer the question using ONLY the numbered "
              "passages below. Cite passages inline as [1], [2], etc. If the "
              "passages don't contain the answer, say so — do not speculate. "
              "Never give buy/sell/hold recommendations.")
    user = f"QUESTION: {query}\n\nPASSAGES:\n{context}"
    if provider == "anthropic":
        try:
            import anthropic
        except ImportError:
            print("ERROR: `anthropic` SDK required. pip install anthropic")
            sys.exit(1)
        client = anthropic.Anthropic()
        resp = client.messages.create(
            model=model, max_tokens=1024, system=system,
            messages=[{"role": "user", "content": user}],
        )
        return resp.content[0].text
    if provider == "openai":
        try:
            import openai
        except ImportError:
            print("ERROR: `openai` SDK required. pip install openai")
            sys.exit(1)
        client = openai.OpenAI()
        resp = client.chat.completions.create(
            model=model, max_tokens=1024,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
        )
        return resp.choices[0].message.content
    raise RuntimeError(f"Unknown provider: {provider}")


def run_light(ticker: str, form: str, top_k: int, custom_query: str | None,
              as_json: bool = False) -> None:
    # With --json, human-readable progress goes to stderr; stdout is pure JSON.
    say = (lambda *a, **k: print(*a, file=sys.stderr, **k)) if as_json else print

    say(f"\n{'='*64}")
    say(f"  SEC GUIDANCE (light mode) | {ticker.upper()} {form.upper()}")
    say(f"{'='*64}\n")

    cik = _lookup_cik(ticker)
    if not cik:
        print(f"ERROR: no CIK found for ticker {ticker} — the company may not "
              f"file with the SEC (private, or non-US without a US listing).")
        sys.exit(1)

    resolved_form, filing = _resolve_filing(cik, form)
    if not filing:
        tried = " / ".join(FORM_CHAIN) if form == "auto" else form
        print(f"ERROR: no {tried} filing found for {ticker} (CIK {cik}).")
        if form != "auto":
            print("Hint: try --form auto — foreign private issuers file "
                  "20-F/40-F/6-K instead of 10-K/10-Q.")
        sys.exit(1)
    if form == "auto" and resolved_form not in ("10-Q", "10-K"):
        say(f"[form auto] no 10-Q/10-K — foreign private issuer, using {resolved_form}")

    say(f"Filing: {resolved_form} {filing['filing_date']}  accession={filing['accession']}")
    say(f"URL: {filing['primary_doc_url']}\n")

    filing_key = f"{ticker.upper()}_{resolved_form.replace('-','')}_{filing['accession']}"
    text = _fetch_and_extract_text(filing['primary_doc_url'], filing_key)
    chunks = _chunk(text)
    say(f"Extracted {len(text):,} chars → {len(chunks)} chunks\n")

    provider, model = _pick_llm()
    if provider:
        say(f"LLM: {provider}/{model}\n")
    else:
        say("No LLM API key set (ANTHROPIC_API_KEY / OPENAI_API_KEY) — "
            "showing ranked passages only, no synthesized answers.\n")

    queries = [custom_query] if custom_query else GUIDANCE_QUERIES
    all_picked: set[int] = set()
    results = []
    for i, query in enumerate(queries, 1):
        say(f"[{i}/{len(queries)}] {query}")
        say("─" * 64)
        entry = {"query": query, "answer": None, "sources": [], "error": None}
        try:
            passages = _bm25_topk(query, chunks, top_k)
            if not passages:
                say("  No candidate passages.\n")
                results.append(entry)
                continue
            all_picked.update(idx for idx, _, _ in passages)
            entry["sources"] = [
                {"n": j, "chunk": idx, "bm25": round(score, 2), "quote": _snippet(t)}
                for j, (idx, score, t) in enumerate(passages, 1)
            ]
            if provider:
                entry["answer"] = _ask_llm(query, passages, provider, model)
                say(entry["answer"])
            say("\nSources (verify against the filing URL above):")
            for s in entry["sources"]:
                say(f"  [{s['n']}] chunk #{s['chunk']}  score={s['bm25']}")
                say(f"      \"{s['quote']}…\"")
            say("")
        except Exception as e:
            entry["error"] = str(e)
            say(f"  ERROR: {e}\n")
        results.append(entry)

    recall_line, recall_stats = _recall_note(chunks, all_picked)
    say(recall_line)
    say(f"{'='*64}\nDone.")

    if as_json:
        print(json.dumps({
            "ticker": ticker.upper(),
            "form": resolved_form,
            "filing_date": filing["filing_date"],
            "accession": filing["accession"],
            "filing_url": filing["primary_doc_url"],
            "llm": f"{provider}/{model}" if provider else None,
            "results": results,
            "recall_check": recall_stats,
        }, indent=2))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Light-mode SEC guidance extractor")
    p.add_argument("--ticker", default="AAPL")
    p.add_argument("--form", default="auto", choices=FORM_CHOICES,
                   help="auto tries 10-Q → 10-K → 20-F → 40-F → 6-K")
    p.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    p.add_argument("--query", help="Single custom question (skips the 5 default queries)")
    p.add_argument("--json", action="store_true",
                   help="Emit structured JSON on stdout (progress goes to stderr)")
    args = p.parse_args()
    run_light(args.ticker, args.form, args.top_k, args.query, as_json=args.json)
