#!/usr/bin/env python3
"""
Extract forward-looking guidance from SEC 10-K/10-Q filings via the RAG pipeline.

Usage:
  python extract_guidance.py --ticker AAPL --form 10-Q
  python extract_guidance.py --ticker AAPL --form 10-K --top-k 8
  python extract_guidance.py --query "What did management say about iPhone revenue?"
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_pipeline_env = os.environ.get("SEC_PIPELINE_DIR")
if not _pipeline_env:
    print("ERROR: SEC_PIPELINE_DIR is not set. Point it at your SEC RAG pipeline directory.")
    sys.exit(1)
PIPELINE_DIR = Path(_pipeline_env)
sys.path.insert(0, str(PIPELINE_DIR))

GUIDANCE_QUERIES = [
    "What is management's guidance and outlook for future revenue and earnings?",
    "What forward-looking statements did management make about future performance expectations?",
    "What did management say about expected gross margins and profitability going forward?",
    "What new product launches, services, or business expansions did management project or plan?",
    "What macroeconomic conditions, risks, or uncertainties did management highlight for upcoming quarters?",
]


def check_index_status(es) -> tuple[int, list[str]]:
    from pipeline.index import INDEX
    if not es.indices.exists(index=INDEX):
        return 0, []
    count = es.count(index=INDEX)["count"]
    files = []
    try:
        agg = es.search(
            index=INDEX,
            body={"size": 0, "aggs": {"files": {"terms": {"field": "source_file", "size": 200}}}},
        )
        files = [b["key"] for b in agg["aggregations"]["files"]["buckets"]]
    except Exception:
        pass
    return count, files


def run_guidance_extraction(
    ticker: str = "AAPL",
    form_type: str = "10-Q",
    top_k: int = 5,
    custom_query: str | None = None,
) -> None:
    try:
        from pipeline.embed import Embedder
        from pipeline.index import get_es
        from pipeline.retrieve import hybrid_search
        from pipeline.rerank import Reranker
        from pipeline.answer import generate_answer
    except ImportError as e:
        print(f"ERROR: Cannot import pipeline — {e}")
        print(f"Pipeline expected at: {PIPELINE_DIR}")
        sys.exit(1)

    print(f"\n{'='*64}")
    print(f"  SEC GUIDANCE EXTRACTOR | {ticker.upper()} {form_type.upper()}")
    print(f"{'='*64}\n")

    try:
        embedder = Embedder()
        es = get_es()
    except Exception as e:
        print(f"ERROR: Pipeline init failed — {e}")
        print("Is Elasticsearch running? Try: docker ps | grep elastic")
        sys.exit(1)

    doc_count, indexed_files = check_index_status(es)
    if doc_count == 0:
        print("ERROR: Index is empty. Run first:")
        print(f"  cd '{PIPELINE_DIR}' && python run_pipeline.py ingest")
        sys.exit(1)

    print(f"Index: {doc_count} docs across {len(indexed_files)} files\n")

    try:
        reranker = Reranker()
    except Exception as e:
        print(f"WARNING: Reranker unavailable ({e}), using raw retrieval scores.\n")
        reranker = None

    queries = [custom_query] if custom_query else GUIDANCE_QUERIES

    for i, query in enumerate(queries, 1):
        print(f"[{i}/{len(queries)}] {query}")
        print("─" * 64)

        try:
            candidates = hybrid_search(query, embedder, es, top_k=top_k * 4)
            if not candidates:
                print("  No relevant passages found.\n")
                continue

            if reranker:
                results = reranker.rerank(query, candidates, top_k=top_k)
            else:
                results = candidates[:top_k]

            out = generate_answer(query, results)
            print(out["answer"])
            print("\nSources:")
            for src in out["sources"]:
                date = src.get("filing_date", "?")
                page = src.get("page_number", "?")
                print(f"  [{src['num']}] {src['source_file']}  p.{page}  filed {date}")
            print()

        except Exception as e:
            print(f"  ERROR: {e}\n")

    print(f"{'='*64}")
    print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Extract management guidance from SEC 10-K/10-Q filings"
    )
    parser.add_argument("--ticker", default="AAPL", help="Stock ticker (default: AAPL)")
    parser.add_argument("--form", default="10-Q", choices=["10-Q", "10-K"],
                        help="SEC form type (default: 10-Q)")
    parser.add_argument("--top-k", type=int, default=5,
                        help="Passages per query (default: 5)")
    parser.add_argument("--query", help="Run a single custom guidance question instead")
    args = parser.parse_args()

    run_guidance_extraction(
        ticker=args.ticker,
        form_type=args.form,
        top_k=args.top_k,
        custom_query=args.query,
    )
