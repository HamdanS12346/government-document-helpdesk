#!/usr/bin/env python
"""Run the Response Node evaluation dataset with LLM-as-a-judge.

Usage:
    python -m evaluation.runners.run_response \
        [--dataset PATH] [--output PATH] [--limit N] [--criteria C1,C2,...] [--no-langfuse]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv

# Ensure project root is on sys.path and load .env
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

from evaluation.case_loader import find_default_dataset, load_cases, validate_case_ids
from evaluation.evaluators.response.evaluator import (
    ALL_CRITERIA,
    evaluate_response_case,
    summarize_response_results,
)
from evaluation.langfuse_reporting import LangfuseReporter

# Main app imports for response generation
from app.contracts.intent_decision import IntentDecision, IntentType
from app.contracts.normalized_input import NormalizedInput
from app.contracts.response import RetrievedContext
from app.response.generator import ResponseGenerator

logger = logging.getLogger(__name__)


def generate_response_for_case(
    case: Dict[str, Any],
    generator: ResponseGenerator,
) -> str:
    """Generate a response using the app's ResponseGenerator grounded on case context."""
    query = case.get("query", "")
    context_chunks = case.get("context", [])

    formatted_texts = [
        c.get("text", "") for c in context_chunks if isinstance(c, dict) and c.get("text")
    ]
    citations = [
        c.get("source_url")
        for c in context_chunks
        if isinstance(c, dict) and c.get("source_url")
    ]

    has_relevant = bool(formatted_texts)
    formatted_context = "\n\n".join(formatted_texts) if has_relevant else None

    norm_input = NormalizedInput(
        user_query=query,
        image_content=[],
        pdf_content=[],
        combined_text="",
    )
    intent_dec = IntentDecision(
        query=query,
        intent_type=IntentType.DOCUMENT_INFO,
        confidence_score=1.0,
    )
    retrieved_ctx = RetrievedContext(
        has_relevant_documents=has_relevant,
        formatted_context=formatted_context,
        citations=citations,
        documents=[],
    )

    ai_message = generator.generate(
        normalized_input=norm_input,
        intent_decision=intent_dec,
        retrieved_context=retrieved_ctx,
        messages=[],
        conversation_summary=None,
    )
    return str(ai_message.content)


def run_dataset(
    dataset_path: Path,
    *,
    limit: Optional[int] = None,
    criteria: Optional[List[str]] = None,
    generator: Optional[ResponseGenerator] = None,
) -> Dict[str, Any]:
    """Execute response evaluation on a dataset of cases.

    Returns a report dictionary containing per-case evaluation and aggregated summary metrics.
    """
    cases = load_cases(dataset_path)
    validate_case_ids(cases)

    if limit is not None and limit > 0:
        cases = cases[:limit]

    active_generator = generator or ResponseGenerator()
    case_results: List[Dict[str, Any]] = []

    print(f"Starting response evaluation for {len(cases)} case(s)...")

    for idx, case in enumerate(cases, 1):
        case_id = case.get("id", f"RESP-{idx:03d}")
        query = case.get("query", "")

        # Check if pre-generated response exists in case, otherwise generate live
        generated_resp = case.get("generated_response")
        if not generated_resp:
            generated_resp = generate_response_for_case(case, active_generator)

        print(f"[{idx}/{len(cases)}] Evaluating {case_id}...")
        case_res = evaluate_response_case(
            case=case,
            generated_response=generated_resp,
            criteria=criteria,
        )
        case_results.append(case_res)

    metrics = summarize_response_results(case_results)
    return {"metrics": metrics, "cases": case_results}


def main() -> int:
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
        help="Path to response evaluation dataset (default: evaluation/datasets/response/cases.jsonl)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Path to save JSON report (default: evaluation/reports/response/latest.json)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of cases to evaluate (useful for testing or cost control)",
    )
    parser.add_argument(
        "--criteria",
        type=str,
        default=None,
        help="Comma-separated subset of criteria to evaluate (e.g., 'correctness,faithfulness')",
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

    selected_criteria = (
        [c.strip() for c in args.criteria.split(",") if c.strip()]
        if args.criteria
        else None
    )

    dataset_path = args.dataset or find_default_dataset(PROJECT_ROOT / "evaluation/datasets/response")
    report = run_dataset(dataset_path, limit=args.limit, criteria=selected_criteria)

    if not args.no_langfuse:
        try:
            LangfuseReporter.from_environment().publish("response", report)
            print("Successfully published response evaluation report to Langfuse.")
        except Exception as exc:
            print(f"[WARNING] Could not publish to Langfuse: {exc}", file=sys.stderr)

    rendered = json.dumps(report, indent=2)
    output_path = args.output or (PROJECT_ROOT / "evaluation/reports/response/latest.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered + "\n", encoding="utf-8")

    print(rendered)
    print(f"\nReport written to: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
