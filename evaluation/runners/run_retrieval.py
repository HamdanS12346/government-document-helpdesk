#!/usr/bin/env python
"""Run the Retrieval evaluation dataset.

Usage:
    python -m evaluation.runners.run_retrieval \
        [--dataset PATH] [--output PATH] [--top-k N] [--no-langfuse]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, List, Optional
from dotenv import load_dotenv
load_dotenv()

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Local imports (evaluation package)
from evaluation.case_loader import load_cases, find_default_dataset, validate_case_ids
from evaluation.evaluators.retrieval.evaluator import (
    evaluate_retrieval_case,
    summarize_retrieval_results,
)
from evaluation.langfuse_reporting import LangfuseReporter

# Retriever pipeline import (from the main app)
from app.rag.node import RetrieverPipeline, get_default_retriever_pipeline


def initialize_and_validate_corpus(pipeline: RetrieverPipeline) -> tuple[int, int]:
    """Warm dense resources, populate BM25 from Chroma, and validate both corpora.

    Returns:
        tuple[int, int]: (chroma_document_count, bm25_document_count)

    Raises:
        RuntimeError: If either Chroma or BM25 has 0 documents.
    """
    print("[INFO] Initializing retrieval environment...", flush=True)

    # 1. Warm dense resources and verify Chroma
    pipeline.warm_dense_resources()
    collection = getattr(pipeline.vector_retriever, "_get_collection", lambda: None)()

    chroma_count = 0
    if collection is not None and hasattr(collection, "count"):
        try:
            chroma_count = collection.count()
        except Exception as exc:
            print(f"[WARN] Failed to read Chroma collection count: {exc}", flush=True)
    elif hasattr(pipeline.vector_retriever, "document_count"):
        chroma_count = pipeline.vector_retriever.document_count
    elif hasattr(pipeline.vector_retriever, "_documents"):
        chroma_count = len(pipeline.vector_retriever._documents)

    if chroma_count == 0:
        raise RuntimeError(
            "Chroma corpus is empty (0 documents found). "
            "Make sure ChromaDB is populated and accessible before running retrieval evaluation."
        )
    print(f"[SUCCESS] Chroma vector store initialized ({chroma_count} documents).", flush=True)

    # 2. Warm lexical index (BM25) and verify
    print("[INFO] Loading documents into BM25 in-memory index from Chroma...", flush=True)
    pipeline.warm_lexical_index()
    bm25_count = getattr(pipeline.lexical_searcher, "document_count", 0)
    is_indexed = getattr(pipeline.lexical_searcher, "is_indexed", False)

    if bm25_count == 0 or not is_indexed:
        raise RuntimeError(
            f"BM25 corpus is empty ({bm25_count} documents indexed). "
            "Failed to build BM25 lexical index from Chroma corpus."
        )
    print(f"[SUCCESS] BM25 lexical index initialized ({bm25_count} documents).", flush=True)

    return chroma_count, bm25_count


def run_dataset(
    dataset_path: Path,
    *,
    top_k: int = 5,
    limit: Optional[int] = None,
    start: Optional[int] = None,
    end: Optional[int] = None,
    pipeline: Optional[RetrieverPipeline] = None,
) -> dict[str, Any]:
    """Execute the retrieval evaluation on a dataset.

    Returns a report dictionary with per‑case results and aggregated metrics.
    """
    all_cases = load_cases(dataset_path)
    validate_case_ids(all_cases)

    # Slice cases by start/end or limit if specified
    start_idx = (start - 1) if (start and start > 0) else 0
    end_idx = min(len(all_cases), end) if (end and end > 0) else len(all_cases)
    cases = all_cases[start_idx:end_idx]
    if limit is not None and limit > 0:
        cases = cases[:limit]

    print(f"[INFO] Running evaluation on {len(cases)} cases (out of {len(all_cases)} total)...", flush=True)

    if pipeline is None:
        pipeline = get_default_retriever_pipeline()

    # Initialize Chroma & BM25 in-process and fail if either corpus is empty
    chroma_count, bm25_count = initialize_and_validate_corpus(pipeline)

    # Override the final `final_top_k` if the user requested a different value.
    pipeline.final_top_k = top_k

    case_results: List[dict[str, Any]] = []
    for idx, case in enumerate(cases, start=1):
        query = case.get("query", "")
        # Minimal LangGraph state – only the normalized input the retriever expects.
        state = {"normalized_input": {"user_query": query, "image_content": [], "pdf_content": [], "combined_text": ""}}
        retriever_out = pipeline.execute(state)
        retrieved_docs = retriever_out.get("documents", [])
        retrieved_ids = [doc.id for doc in retrieved_docs]

        retrieval_status = retriever_out.get("retrieval_status")
        if isinstance(retrieval_status, dict):
            dense_count = retrieval_status.get("dense_result_count", 0)
            lexical_count = retrieval_status.get("lexical_result_count", 0)
        elif hasattr(retrieval_status, "dense_result_count"):
            dense_count = getattr(retrieval_status, "dense_result_count", 0)
            lexical_count = getattr(retrieval_status, "lexical_result_count", 0)
        else:
            dense_count = 0
            lexical_count = 0

        print(
            f"[{idx}/{len(cases)}] Evaluating case {case.get('id')}: {query[:45]}... "
            f"(Dense: {dense_count}, Lexical: {lexical_count}, Top-k: {len(retrieved_ids)})",
            flush=True,
        )

        case_res = evaluate_retrieval_case(
            case,
            retrieved_ids,
            dense_result_count=dense_count,
            lexical_result_count=lexical_count,
        )
        case_results.append(case_res)

    metrics = summarize_retrieval_results(case_results)
    metrics["chroma_document_count"] = chroma_count
    metrics["bm25_document_count"] = bm25_count
    metrics["hybrid_retrieval_verified"] = (
        chroma_count > 0
        and bm25_count > 0
        and metrics.get("average_dense_result_count", 0) > 0
        and metrics.get("average_lexical_result_count", 0) > 0
    )

    corpus_evidence = {
        "chroma_document_count": chroma_count,
        "bm25_document_count": bm25_count,
        "average_dense_result_count": metrics.get("average_dense_result_count", 0.0),
        "average_lexical_result_count": metrics.get("average_lexical_result_count", 0.0),
        "hybrid_retrieval_verified": metrics["hybrid_retrieval_verified"],
    }

    return {
        "corpus_evidence": corpus_evidence,
        "metrics": metrics,
        "cases": case_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=None,
        help="Path to a JSONL/JSON retrieval evaluation dataset (default: evaluation/datasets/retrieval/cases.jsonl)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="File to write the JSON report (default: evaluation/reports/retrieval/latest.json)",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of top documents to return from the retriever (default: 5)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of cases to evaluate (e.g. --limit 10)",
    )
    parser.add_argument(
        "--start",
        type=int,
        default=None,
        help="1-based start index of cases to evaluate (e.g. --start 1)",
    )
    parser.add_argument(
        "--end",
        type=int,
        default=None,
        help="1-based end index of cases to evaluate (inclusive, e.g. --end 10)",
    )
    langfuse_group = parser.add_mutually_exclusive_group()
    langfuse_group.add_argument(
        "--langfuse",
        action="store_true",
        help="Publish results to Langfuse (default).",
    )
    langfuse_group.add_argument(
        "--no-langfuse",
        action="store_true",
        help="Skip Langfuse publishing for this run.",
    )
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    args = parser.parse_args()

    dataset = args.dataset or find_default_dataset(Path.cwd() / "evaluation/datasets/retrieval")
    try:
        report = run_dataset(
            dataset,
            top_k=args.top_k,
            limit=args.limit,
            start=args.start,
            end=args.end,
        )
    except RuntimeError as exc:
        print(f"\n[FATAL ERROR] Retrieval evaluation aborted: {exc}", file=sys.stderr, flush=True)
        return 1

    if not args.no_langfuse:
        LangfuseReporter.from_environment().publish("retrieval", report)

    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        default_path = PROJECT_ROOT / "evaluation/reports/retrieval/latest.json"
        default_path.parent.mkdir(parents=True, exist_ok=True)
        default_path.write_text(rendered + "\n", encoding="utf-8")

    evidence = report.get("corpus_evidence", {})
    metrics = report.get("metrics", {})
    print("\n" + "=" * 60)
    print("HYBRID RETRIEVAL EVALUATION EVIDENCE SUMMARY")
    print("=" * 60)
    print(f"Total Cases Evaluated:       {metrics.get('total_cases', len(report.get('cases', [])))}")
    print(f"Chroma Indexed Documents:    {evidence.get('chroma_document_count', 'N/A')}")
    print(f"BM25 Indexed Documents:      {evidence.get('bm25_document_count', 'N/A')}")
    print(f"Average Dense Candidates:    {evidence.get('average_dense_result_count', 0.0):.2f}")
    print(f"Average Lexical Candidates:  {evidence.get('average_lexical_result_count', 0.0):.2f}")
    verified_str = "YES" if evidence.get("hybrid_retrieval_verified") else "NO"
    print(f"Hybrid Evaluation Verified:  {verified_str}")
    print("=" * 60 + "\n")

    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
