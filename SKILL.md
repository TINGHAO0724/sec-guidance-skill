---
name: sec-guidance
description: Extract management guidance and forward-looking statements from SEC 10-K/10-Q filings using a local RAG pipeline.
version: 0.1.0
metadata:
  openclaw:
    requires:
      env: ["SEC_PIPELINE_DIR"]
      bins: ["python3"]
    primaryEnv: SEC_PIPELINE_DIR
    homepage: https://github.com/TINGHAO0724/sec-guidance-skill
---

# SEC Guidance Extractor

Extracts forward-looking management guidance from SEC 10-K/10-Q filings using a local multi-modal RAG pipeline (Elasticsearch + sentence-transformers + Ollama).

The pipeline directory is read from the `SEC_PIPELINE_DIR` environment variable.

## When to invoke

- User asks what management said about future revenue, earnings, margins, or outlook
- User asks for guidance from a 10-K or 10-Q filing
- User asks "what is [company]'s guidance for next quarter?"
- User wants forward-looking statements or risk factors from SEC filings

## Setup (first time only)

### 1. Set the env var

In `~/.openclaw/openclaw.json`:

```json5
{
  skills: {
    entries: {
      "sec-guidance": {
        enabled: true,
        env: { SEC_PIPELINE_DIR: "/path/to/your/sec-rag-pipeline" }
      }
    }
  }
}
```

Or export in your shell before starting the gateway:
```bash
export SEC_PIPELINE_DIR="/path/to/your/sec-rag-pipeline"
```

### 2. Start Elasticsearch

```bash
docker ps | grep elastic   # confirm it's running
```

### 3. Download and index filings

```bash
cd "$SEC_PIPELINE_DIR"

# Download filings (any ticker, any form type)
python download_sec_filings.py --ticker AAPL --form 10-Q --format pdf
python download_sec_filings.py --ticker AAPL --form 10-K --format pdf

# Ingest into Elasticsearch
python run_pipeline.py ingest
```

Check index status:
```bash
python run_pipeline.py stats
```

## Run guidance extraction

Default (5 standard guidance queries):
```bash
python "{baseDir}/extract_guidance.py"
```

With options:
```bash
python "{baseDir}/extract_guidance.py" --ticker AAPL --form 10-K --top-k 8
```

Single custom question:
```bash
python "{baseDir}/extract_guidance.py" --query "What did management say about iPhone revenue next year?"
```

Or use the pipeline's ask command directly:
```bash
python "$SEC_PIPELINE_DIR/run_pipeline.py" ask "What is management's outlook for gross margins?"
```

## Add a new ticker

```bash
cd "$SEC_PIPELINE_DIR"
python download_sec_filings.py --ticker MSFT --form 10-Q --format pdf --limit 8
python run_pipeline.py ingest
```

## Standard guidance queries the script runs

1. Future revenue and earnings outlook
2. Forward-looking performance expectations
3. Expected gross margins and profitability
4. New product launches, services, or expansion plans
5. Macroeconomic risks and uncertainties for upcoming quarters

## Output format

Each query prints the LLM answer with inline citations `[1]`, `[2]`, etc., plus a source list (filename, page number, filing date).

## Pipeline requirements

| Component | Purpose |
|---|---|
| Elasticsearch (local/Docker) | Hybrid search index |
| `sentence-transformers` | Embedding model (`all-MiniLM-L6-v2`) |
| `cross-encoder` | Neural reranker |
| Ollama (`hermes3:8b` or similar) | Answer generation |
| `pymupdf`, `pdfplumber` | PDF ingestion |
