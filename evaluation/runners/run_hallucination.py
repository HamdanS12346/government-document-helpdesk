#!/usr/bin/env python
"""Run the Hallucination and Unsupported Information Evaluation on the connected chatbot graph.

Evaluates claim-level context support, detection of fabricated facts, refusal to guess,
and handling of false premises using the real connected RAG graph.

Usage:
    python -m evaluation.runners.run_hallucination \\
        [--dataset PATH] [--output PATH] [--limit N] [--start N] [--end N] [--no-langfuse]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

# Ensure project root is on sys.path and load .env
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

from evaluation.case_loader import find_default_dataset, load_cases, validate_case_ids
from evaluation.evaluators.hallucination.evaluator import (
    DEFAULT_PASS_THRESHOLD,
    evaluate_hallucination_case,
    summarize_hallucination_results,
)
from evaluation.graph.adapter import ConnectedGraphAdapter, GraphEvaluationOutput
from evaluation.langfuse_reporting import LangfuseReporter
from app.rag.node import get_default_retriever_pipeline
from evaluation.runners.run_retrieval import initialize_and_validate_corpus

logger = logging.getLogger(__name__)


def ensure_corpus_indexed() -> tuple[int, int]:
    """Ensure both dense vector store and BM25 lexical index are populated and validated."""
    pipeline = get_default_retriever_pipeline()
    return initialize_and_validate_corpus(pipeline)


def print_hallucination_report(report: Dict[str, Any]) -> None:
    """Print clean formatted report matching Section 22 of the evaluation plan."""
    metrics = report.get("metrics", {})
    cases = report.get("cases", [])

    print("\n" + "=" * 80)
    print("Hallucination Evaluation Report")
    print("=" * 80)
    print(f"\nTotal Cases: {metrics.get('total_cases', 0)}")
    print(f"\nAverage Hallucination Score: {metrics.get('average_hallucination_score', 0.0):.2f}")
    print(f"\nHallucination Rate: {metrics.get('hallucination_rate', 0.0) * 100:.1f}%")
    print(f"\nUnsupported Claim Rate: {metrics.get('unsupported_claim_rate', 0.0) * 100:.1f}%")
    print(f"\nUnsupported Information Handling: {metrics.get('unsupported_information_handling', 0.0) * 100:.1f}%")
    print(f"\nCases with Hallucinations: {metrics.get('cases_with_hallucinations', 0)}")
    print(f"\nCases Correctly Handling Missing Information: {metrics.get('cases_correctly_handling_missing_information', 0)}")
    print(f"\nPassed Cases: {metrics.get('passed_cases', 0)}")
    print(f"Failed Cases: {metrics.get('failed_cases', 0)}")

    failed_cases = [c for c in cases if not c.get("passed", True) or c.get("hallucination_detected", False)]
    if failed_cases:
        print("\n" + "-" * 80)
        print("Failure / Hallucination Details:")
        print("-" * 80)
        for fc in failed_cases:
            case_id = fc.get("id", "UNKNOWN")
            query = fc.get("query", "")
            reason = fc.get("reason", "")
            claims = fc.get("claims", [])
            unsupported = [c.get("claim") for c in claims if not c.get("supported", False)]

            print(f"\n[{case_id}]")
            print(f"Query: {query}")
            if unsupported:
                print("Unsupported Claim(s):")
                for claim in unsupported:
                    print(f'  - "{claim}"')
            print(f"Reason: {reason}")
    print("\n" + "=" * 80)


def run_hallucination_evaluation(
    dataset_path: Path,
    *,
    adapter: Optional[ConnectedGraphAdapter] = None,
    limit: Optional[int] = None,
    start: Optional[int] = None,
    end: Optional[int] = None,
    pass_threshold: float = DEFAULT_PASS_THRESHOLD,
    llm: Optional[Any] = None,
) -> Dict[str, Any]:
    """Execute hallucination evaluation across the dataset using the connected chatbot graph.

    Args:
        dataset_path: Path to cases.jsonl.
        adapter: ConnectedGraphAdapter instance (created if None).
        limit: Max number of cases to evaluate.
        start: 1-indexed start offset.
        end: 1-indexed end offset.
        pass_threshold: Passing threshold score.
        llm: Injected chat model instance for judge testing.

    Returns:
        Report dictionary with aggregate metrics and per-case results.
    """
    all_cases = load_cases(dataset_path)
    validate_case_ids(all_cases)

    # Slice range if specified
    start_idx = max(1, start) if start is not None else 1
    end_idx = min(len(all_cases), end) if end is not None else len(all_cases)
    selected_cases = all_cases[start_idx - 1 : end_idx]
    if limit is not None:
        selected_cases = selected_cases[:limit]

    if adapter is None:
        try:
            ensure_corpus_indexed()
        except Exception as exc:
            logger.warning("Corpus warm-up skipped or failed: %s", exc)
        adapter = ConnectedGraphAdapter()

    print(f"Evaluating {len(selected_cases)} hallucination test cases using connected graph...\n")

    case_results: List[Dict[str, Any]] = []

    for idx, case in enumerate(selected_cases, 1):
        case_id = case.get("id", f"HAL-{idx:03d}")
        query = case.get("query", "")
        test_type = case.get("metadata", {}).get("test_type", "unknown")
        print(f"[{idx}/{len(selected_cases)}] Case {case_id} ({test_type}): \"{query[:60]}...\"")

        # 1. Execute through real connected graph
        try:
            graph_output: GraphEvaluationOutput = adapter.run(query=query)
            if not graph_output.success:
                logger.error("Graph execution failed for %s: %s", case_id, graph_output.error)
                case_results.append({
                    "id": case_id,
                    "query": query,
                    "generated_response": "",
                    "score": 0.0,
                    "hallucination_detected": False,
                    "claims": [],
                    "supported_claims": 0,
                    "unsupported_claims": 0,
                    "total_claims": 0,
                    "unsupported_information_handling": 0.0,
                    "reason": f"Graph execution error: {graph_output.error}",
                    "passed": False,
                    "expected_behavior": case.get("expected_behavior", ""),
                    "metadata": case.get("metadata", {}),
                })
                continue

            # 2. Extract actual retrieved context and actual response
            retrieved_context = graph_output.formatted_context or (
                graph_output.retrieved_context.formatted_context
                if graph_output.retrieved_context is not None
                else ""
            )
            response_text = graph_output.response or graph_output.clarification_question or ""

            # 3. Evaluate claim-level context support
            eval_result = evaluate_hallucination_case(
                case=case,
                generated_response=response_text,
                retrieved_context=retrieved_context,
                llm=llm,
                pass_threshold=pass_threshold,
            )
            eval_result["retrieved_chunk_ids"] = graph_output.retrieved_chunk_ids
            eval_result["citations"] = graph_output.citations
            eval_result["token_usage"] = graph_output.token_usage
            case_results.append(eval_result)

            status = "PASSED" if eval_result["passed"] else "FAILED"
            hallucination_flag = " [HALLUCINATION DETECTED]" if eval_result["hallucination_detected"] else ""
            print(f"    -> Score: {eval_result['score']:.2f} | Status: {status}{hallucination_flag}")

        except Exception as exc:
            logger.error("Evaluation error for %s: %s", case_id, exc)
            case_results.append({
                "id": case_id,
                "query": query,
                "generated_response": "",
                "score": 0.0,
                "hallucination_detected": False,
                "claims": [],
                "supported_claims": 0,
                "unsupported_claims": 0,
                "total_claims": 0,
                "unsupported_information_handling": 0.0,
                "reason": f"Evaluation error: {exc}",
                "passed": False,
                "expected_behavior": case.get("expected_behavior", ""),
                "metadata": case.get("metadata", {}),
            })

    metrics = summarize_hallucination_results(case_results)
    return {"metrics": metrics, "cases": case_results}


def main() -> int:
    """CLI entry point for running the hallucination evaluation."""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=None,
        help="Path to hallucination evaluation dataset (default: evaluation/datasets/hallucination/cases.jsonl)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Path to save JSON report (default: evaluation/reports/hallucination_report.json)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of cases to evaluate",
    )
    parser.add_argument(
        "--start",
        type=int,
        default=None,
        help="1-indexed starting case number",
    )
    parser.add_argument(
        "--end",
        type=int,
        default=None,
        help="1-indexed ending case number",
    )
    parser.add_argument(
        "--pass-threshold",
        type=float,
        default=DEFAULT_PASS_THRESHOLD,
        help="Minimum score threshold to pass (default: 0.70)",
    )
    langfuse_group = parser.add_mutually_exclusive_group()
    langfuse_group.add_argument(
        "--langfuse",
        action="store_true",
        help="Publish results to Langfuse.",
    )
    langfuse_group.add_argument(
        "--no-langfuse",
        action="store_true",
        help="Skip Langfuse publishing.",
    )

    args = parser.parse_args()

    default_dataset_dir = PROJECT_ROOT / "evaluation/datasets/hallucination"
    dataset_path = args.dataset or find_default_dataset(default_dataset_dir)

    report = run_hallucination_evaluation(
        dataset_path=dataset_path,
        limit=args.limit,
        start=args.start,
        end=args.end,
        pass_threshold=args.pass_threshold,
    )

    # Print Section 22 summary
    print_hallucination_report(report)

    # Langfuse reporting
    if not args.no_langfuse:
        try:
            LangfuseReporter.from_environment().publish("hallucination", report)
            print("Successfully published hallucination evaluation report to Langfuse.")
        except Exception as exc:
            print(f"[WARNING] Could not publish to Langfuse: {exc}", file=sys.stderr)

    # Save output reports
    rendered = json.dumps(report, indent=2)
    output_path = args.output or (PROJECT_ROOT / "evaluation/reports/hallucination_report.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered + "\n", encoding="utf-8")

    # Also save to evaluation/reports/hallucination/latest.json for consistency with other evaluators
    secondary_path = PROJECT_ROOT / "evaluation/reports/hallucination/latest.json"
    secondary_path.parent.mkdir(parents=True, exist_ok=True)
    secondary_path.write_text(rendered + "\n", encoding="utf-8")

    print(f"\nReport written to: {output_path}")
    print(f"Secondary report written to: {secondary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
