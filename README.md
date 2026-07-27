# sec-guidance — OpenClaw Skill

An [OpenClaw](https://docs.openclaw.ai) skill that extracts management
guidance and forward-looking statements from SEC 10-K/10-Q filings using
a local RAG pipeline (Elasticsearch + sentence-transformers +
cross-encoder reranking + Ollama).

## What it does

Ask your agent things like *"what is AAPL's guidance for next quarter?"*
and the skill runs five standard guidance queries (or your custom one)
against a locally indexed corpus of SEC filings, returning cited answers
with source file, page number, and filing date.

## Requirements

- A local SEC filing RAG pipeline (downloader + Elasticsearch ingestion);
  the skill calls it through the `SEC_PIPELINE_DIR` environment variable
- Elasticsearch running locally (Docker is fine)
- Python 3 with `sentence-transformers`, a cross-encoder reranker, and
  an Ollama model for answer generation

No credentials are embedded; everything runs locally against public SEC
EDGAR data.

## Files

| File | Purpose |
|---|---|
| `SKILL.md` | Skill definition: triggers, setup, commands |
| `extract_guidance.py` | Guidance extraction runner (5 standard queries or `--query`) |
| `CHANGELOG.md` | Version history |

## Install

```bash
clawhub install sec-guidance
```

Then set `SEC_PIPELINE_DIR` as described in `SKILL.md`.

## License

MIT-0 (per ClawHub platform policy).
