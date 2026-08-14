# Changelog

## 0.3.0 — 2026-08-14

Mentor-review round: foreign issuers, verifiable citations, recall check, UX.

- **Foreign private issuers**: `--form auto` (new default) walks
  10-Q → 10-K → 20-F → 40-F → 6-K, so BABA/TSM-style filers work without
  the user knowing which form they file. Explicit `--form 20-F` etc. also
  accepted.
- **Verifiable citations**: every source line now prints a direct quote
  from the cited chunk alongside chunk index + BM25 score, so answers can
  be checked against the filing URL.
- **Recall check**: after retrieval, reports coverage of "guidance-dense"
  chunks (≥3 forward-looking keywords, adaptive down to ≥2 for terse
  filings like AAPL 10-Qs) by the retrieved set and warns loudly when
  low — BM25 misses become visible instead of silent.
- **No-key degradation**: with neither `ANTHROPIC_API_KEY` nor
  `OPENAI_API_KEY` set, the skill prints ranked passages with quotes
  instead of exiting — usable for retrieval without any LLM.
- **Retry/backoff**: EDGAR requests retry 3× on 429/5xx with a hint to set
  `SEC_GUIDANCE_UA` when throttled.
- **`--json`**: structured output (answers, sources with quotes, filing
  metadata, recall stats) on stdout; progress on stderr.
- **Boundaries documented**: SKILL.md gains a "When NOT to invoke" section
  (no market data, no non-SEC companies, no transcripts, no trading
  advice) and division-of-labor notes vs other financial skills.
- Submissions index fetched once per run (was once per form probe).

## 0.2.0 — 2026-08-03

Self-contained light mode + auto-detect dispatcher.

- New `sec_guidance_light.py`: fetches the latest 10-K/10-Q directly from
  SEC EDGAR, extracts text (BeautifulSoup), chunks in memory, ranks with
  BM25, calls Claude or OpenAI with inline citations. No Elasticsearch,
  no Ollama, no external RAG pipeline required.
- `extract_guidance.py` now dispatches by runtime detection:
  `--mode auto` (default) runs heavy if `SEC_PIPELINE_DIR` is set AND the
  pipeline is importable AND Elasticsearch is reachable; otherwise light.
  `--mode {light,heavy}` forces one.
- `SEC_PIPELINE_DIR` demoted from required to optional; light mode needs
  only `ANTHROPIC_API_KEY` (or `OPENAI_API_KEY`).
- `requirements.txt` added: `requests`, `beautifulsoup4`, `rank-bm25`,
  `anthropic`.
- Filings cached under `~/.cache/sec-guidance/` for repeat runs.

## 0.1.0 — 2026-07-26

Initial ClawHub release.

- `extract_guidance.py`: runs 5 standard guidance queries (or a single
  custom `--query`) against a local SEC filing RAG pipeline
  (Elasticsearch + sentence-transformers + cross-encoder rerank + Ollama),
  printing cited answers with source file / page / filing date.
- Pipeline location is taken strictly from the `SEC_PIPELINE_DIR`
  environment variable (no hardcoded paths); the script exits with a
  clear error when unset, when the pipeline can't be imported, or when
  the index is empty.
- SKILL.md documents setup (env var, Elasticsearch, ingestion), trigger
  scenarios, and all commands.
