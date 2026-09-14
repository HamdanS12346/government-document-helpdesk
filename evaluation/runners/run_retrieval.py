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
from typing import Any, List
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
from app.rag.node import get_default_retriever_pipeline


def run_dataset(dataset_path: Path, *, top_k: int = 5) -> dict[str, Any]:
    """Execute the retrieval evaluation on a dataset.

    Returns a report dictionary with per‑case results and aggregated metrics.
    """
    cases = load_cases(dataset_path)
    validate_case_ids(cases)

    pipeline = get_default_retriever_pipeline()
    # Override the final `final_top_k` if the user requested a different value.
    pipeline.final_top_k = top_k

    case_results: List[dict[str, Any]] = []
    for case in cases:
        query = case.get("query", "")
        # Minimal LangGraph state – only the normalized input the retriever expects.
        state = {"normalized_input": {"user_query": query, "image_content": [], "pdf_content": [], "combined_text": ""}}
        retriever_out = pipeline.execute(state)
        retrieved_docs = retriever_out.get("documents", [])
        retrieved_ids = [doc.id for doc in retrieved_docs]
        case_res = evaluate_retrieval_case(case, retrieved_ids)
        case_results.append(case_res)

    metrics = summarize_retrieval_results(case_results)
    return {"metrics": metrics, "cases": case_results}


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
    report = run_dataset(dataset, top_k=args.top_k)

    if not args.no_langfuse:
        LangfuseReporter.from_environment().publish("retrieval", report)

    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        default_path = PROJECT_ROOT / "evaluation/reports/retrieval/latest.json"
        default_path.parent.mkdir(parents=True, exist_ok=True)
        default_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
