# sec-guidance — OpenClaw Skill

An [OpenClaw](https://docs.openclaw.ai) skill that extracts management
guidance and forward-looking statements from SEC filings — 10-K/10-Q for
domestic filers, 20-F/40-F/6-K for foreign private issuers.

**Light mode (default): zero infrastructure.** Fetches the filing straight
from SEC EDGAR, ranks passages with in-memory BM25, and asks Claude (or
OpenAI) to answer with inline citations and direct quotes. No Docker, no
Elasticsearch, no Ollama.

## What it does

Ask your agent things like *"what is AAPL's guidance for next quarter?"*
and the skill runs five standard guidance queries (or your custom one)
against the latest filing, returning cited answers where every source
line carries a direct quote you can check against the filing URL.

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...   # or OPENAI_API_KEY; optional
python extract_guidance.py --ticker AAPL
python extract_guidance.py --ticker BABA                  # foreign issuer → 20-F, automatically
python extract_guidance.py --ticker NVDA --json           # structured output
python extract_guidance.py --ticker MSFT --query "What did management say about Azure growth?"
```

With no API key set, the skill degrades to retrieval-only output (ranked
passages with quotes) instead of failing.

## Honest-retrieval features

- **Recall check** — after retrieval, reports how many "guidance-dense"
  chunks of the filing the retrieved set covered, and warns loudly when
  coverage is low. BM25 misses become visible instead of silent.
- **Verifiable citations** — every source line: chunk index, BM25 score,
  and a direct quote, next to the EDGAR URL of the filing.
- **No trading advice** — the model is prompted to extract and cite, never
  to recommend.

## Heavy mode (optional)

If you already run a local SEC RAG pipeline (Elasticsearch +
sentence-transformers + cross-encoder rerank), set `SEC_PIPELINE_DIR` and
the skill auto-detects and delegates to it for higher-quality retrieval
over a full filing history. Worth it only at hundreds of tickers/day.

The heavy pipeline is a slimmed-down open version of the system behind
[deltavigil.com](https://deltavigil.com) — daily SEC-guidance monitoring
across 1000+ US tickers (currently invite-only).

## Files

| File | Purpose |
|---|---|
| `SKILL.md` | Skill definition: triggers, boundaries, setup, commands |
| `extract_guidance.py` | Dispatcher: auto-selects light/heavy mode |
| `sec_guidance_light.py` | Self-contained light mode (EDGAR + BM25 + LLM) |
| `requirements.txt` | Light-mode deps: requests, beautifulsoup4, rank-bm25, anthropic |
| `CHANGELOG.md` | Version history |

## Install

```bash
clawhub install sec-guidance
```

No credentials are embedded; everything runs locally against public SEC
EDGAR data. Filing text is cached under `~/.cache/sec-guidance/`.
