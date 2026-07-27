# Changelog

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
