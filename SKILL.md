---
name: sec-guidance
description: Extract management guidance and forward-looking statements from SEC filings (10-K/10-Q, and 20-F/40-F/6-K for foreign private issuers). Self-contained by default (fetches from EDGAR, in-memory BM25, Claude/OpenAI). Optional heavy mode delegates to a local RAG pipeline.
version: 0.3.0
metadata:
  openclaw:
    requires:
      bins: ["python3"]
    optionalEnv: ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "SEC_PIPELINE_DIR", "SEC_GUIDANCE_UA", "SEC_GUIDANCE_MODEL"]
    homepage: https://github.com/TINGHAO0724/sec-guidance-skill
---

# SEC Guidance Extractor

Fetches the latest SEC filing for a ticker from EDGAR, ranks passages with
BM25, and asks Claude (or OpenAI) to answer forward-looking questions with
inline citations. Handles both domestic filers (10-Q/10-K) and foreign
private issuers (20-F/40-F/6-K) via `--form auto`.

## Quickstart (light mode — default)

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...     # or OPENAI_API_KEY; optional, see below
python extract_guidance.py --ticker AAPL
```

That's it. No Docker, no Elasticsearch, no Ollama.

**No API key?** The skill still runs: it prints the top-ranked filing
passages with quotes instead of synthesized answers, and tells you which
key to set to get full answers.

## When to invoke

- User asks what management said about future revenue, earnings, margins, or outlook
- User asks for guidance from an SEC filing (10-K, 10-Q, 20-F, 6-K)
- User asks "what is [company]'s guidance for next quarter?"
- User wants forward-looking statements or risk factors from SEC filings

## When NOT to invoke (boundaries)

- **Stock prices or valuation** — this reads filings, not market data. Use a
  market-data skill for quotes, charts, or ratios.
- **Companies that don't file with the SEC** — private companies and non-US
  companies without a US listing have no EDGAR filings. The skill fails with
  a clear error, but don't invoke it for these.
- **Earnings-call transcripts or news** — only EDGAR filing text is fetched.
  What the CEO said on the call is out of scope.
- **Buy/sell recommendations** — the skill extracts and cites what management
  said; it is prompted to never produce trading advice.

Division of labor: this skill answers *"what did management commit to in the
filing"*. Pair it with market-data skills for prices and transcript tools for
call commentary.

## Options

```bash
# Auto form selection (default): 10-Q → 10-K → 20-F → 40-F → 6-K
python extract_guidance.py --ticker BABA          # foreign issuer → picks 20-F/6-K

# Specific form
python extract_guidance.py --ticker AAPL --form 10-K --top-k 8

# Single custom question
python extract_guidance.py --ticker MSFT --query "What did management say about Azure growth?"

# Structured output (JSON on stdout, progress on stderr)
python extract_guidance.py --ticker NVDA --json

# Force a mode (default: auto)
python extract_guidance.py --mode light --ticker NVDA
python extract_guidance.py --mode heavy --ticker NVDA
```

## Env vars

| Var | Required | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | no* | Claude API key (preferred) |
| `OPENAI_API_KEY` | no* | OpenAI API key (fallback) |
| `SEC_GUIDANCE_UA` | no | User-Agent for EDGAR requests. SEC rate-limits generic UAs — set to `"yourname you@example.com"` if you make many requests. |
| `SEC_GUIDANCE_MODEL` | no | Override default LLM model. Anthropic default: `claude-sonnet-4-6`. OpenAI default: `gpt-4o-mini`. |
| `SEC_PIPELINE_DIR` | no | Enables heavy mode — see below. |

*With neither key set, output degrades to ranked passages with quotes (no
synthesized answers).

## Standard queries (default, when `--query` not given)

1. Future revenue and earnings outlook
2. Forward-looking performance expectations
3. Expected gross margins and profitability
4. New product launches, services, or expansion plans
5. Macroeconomic risks and uncertainties

## Output & citations

For each query: an LLM answer with inline `[1]`, `[2]` citations, plus a
source list showing chunk index, BM25 score, **and a direct quote from each
cited chunk** so every claim can be checked against the filing URL printed
at the top. `--json` emits the same content as structured JSON (answers,
sources with quotes, filing metadata, recall stats).

**Recall check:** after retrieval, the skill reports how many
"guidance-dense" chunks (≥3 forward-looking keywords) the retrieved set
covered, and warns when coverage is low — BM25 can miss relevant sections,
and this makes that visible instead of silent. Raise `--top-k` or ask a
narrower `--query` when warned.

EDGAR requests retry 3× with backoff on 429/5xx. Filings are cached under
`~/.cache/sec-guidance/` so repeat runs on the same ticker are fast.

## Heavy mode (optional — for bulk / repeat users)

If you already run a local SEC RAG pipeline (Elasticsearch + sentence-transformers +
cross-encoder rerank + Ollama), you can wire this skill to it:

```bash
export SEC_PIPELINE_DIR=/path/to/your/pipeline
python extract_guidance.py --ticker AAPL  # auto-detects heavy mode
```

The skill auto-detects heavy mode when `SEC_PIPELINE_DIR` is set, the
pipeline is importable, and Elasticsearch is reachable. Otherwise it silently
falls back to light mode. Heavy mode gives higher-quality retrieval on
large indexed corpora (cross-encoder rerank, hybrid dense+sparse search) —
worth the setup only if you're querying hundreds of tickers per day.
`--json` and `--form auto` are light-mode features; heavy mode maps `auto`
to 10-Q.

Heavy-mode pipeline expected layout:
- `pipeline/index.py` exports `get_es()`, `INDEX`
- `pipeline/embed.py` exports `Embedder`
- `pipeline/retrieve.py` exports `hybrid_search(query, embedder, es, top_k)`
- `pipeline/rerank.py` exports `Reranker` (optional)
- `pipeline/answer.py` exports `generate_answer(query, results)`

See the reference implementation at the homepage repo. The heavy pipeline
is a slimmed-down open version of the system behind
[deltavigil.com](https://deltavigil.com) — daily SEC-guidance monitoring
across 1000+ US tickers (currently invite-only).

## Limitations of light mode

- One filing at a time (the most recent matching form). Heavy mode indexes
  the full history.
- BM25 only, no semantic embeddings or reranking. Roughly ~20% quality gap
  on the same single-filing query, larger gap on ambiguous questions. The
  recall check surfaces (but cannot fix) retrieval misses.
- 6-K filings are thin wrappers around press releases; guidance content
  varies much more than in 10-Q/10-K and answers may be sparse.
- Full filing text is sent through chunking (~1500 char chunks); very large
  10-Ks (>500 chunks) may be slow to rank. Not slow enough to matter for
  interactive use.
