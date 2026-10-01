"""Run the Clarification & Ambiguity Node evaluation dataset.

Supports:
- Offline mode: Deterministic rule-based clarification generator ($0 cost, 0 external API calls).
- Online mode: Production Clarification Node / OpenAI Clarification Generator with Langfuse tracing.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.clarification.generator import ClarificationGenerator, OpenAIClarificationGenerator  # noqa: E402
from app.clarification.node import ask_for_clarification  # noqa: E402
from app.clarification.schemas import (  # noqa: E402
    ClarificationInput,
    ClarificationReasonCode,
    ClarificationResult,
)
from app.contracts.intent_decision import IntentDecision, IntentType  # noqa: E402
from evaluation.case_loader import find_default_dataset, load_cases, validate_case_ids  # noqa: E402
from evaluation.evaluators.clarification.evaluator import (  # noqa: E402
    evaluate_clarification_case,
    summarize_clarification_results,
)
from evaluation.langfuse_reporting import LangfuseReporter  # noqa: E402

logger = logging.getLogger(__name__)


class OfflineClarificationGenerator:
    """Deterministic offline generator diagnosing ambiguity and producing targeted clarification questions."""

    def generate(self, input_data: ClarificationInput) -> ClarificationResult:
        query = (input_data.classification_query or "").strip()
        lowered = query.lower()

        # Check for attachment reference keywords without upload
        attachment_cues = ["attached", "attachment", "this document", "this certificate", "this form", "seal on this", "section 3 of"]
        if any(cue in lowered for cue in attachment_cues) and "passport" not in lowered and "pan" not in lowered and "aadhaar" not in lowered:
            return ClarificationResult(
                question="Could you please upload or share the text of the document you are referring to so I can assist you?",
                reason_code=ClarificationReasonCode.MISSING_ATTACHMENT_REFERENCE,
                missing_dimensions=["attachment_reference"],
            )

        # Check for state/location-dependent revenue certificates
        location_certs = ["residence certificate", "income certificate", "domicile", "tehsildar"]
        if any(cue in lowered for cue in location_certs):
            return ClarificationResult(
                question="Which state or district are you applying from? State rules and revenue authorities vary by location.",
                reason_code=ClarificationReasonCode.MISSING_LOCATION,
                missing_dimensions=["location"],
            )

        # Check for document named with no question or action
        doc_names = ["aadhaar card", "passport booklet", "pan card", "driving license"]
        is_just_doc = any(d in lowered for d in doc_names) and (
            len(query.split()) <= 4
            or any(p in lowered for p in ["regarding", "have my", "i have"])
            or lowered.endswith(".")
        )
        if is_just_doc:
            return ClarificationResult(
                question="What specific assistance do you need with this document (e.g. fresh application, renewal, correction, or status check)?",
                reason_code=ClarificationReasonCode.MISSING_SERVICE_OR_TASK,
                missing_dimensions=["service_or_task"],
            )

        # Check for applicant context / eligibility conditions
        applicant_cues = ["tatkaal", "discount", "exemption", "qualify", "senior citizen", "minor"]
        if any(cue in lowered for cue in applicant_cues):
            return ClarificationResult(
                question="Could you specify which document or scheme you are applying for and your applicant category (such as adult, minor, or senior citizen)?",
                reason_code=ClarificationReasonCode.MISSING_APPLICANT_CONTEXT,
                missing_dimensions=["applicant_context", "document_type"],
            )

        # Check for vague requests about fees, submission, or validity without document name
        doc_type_cues = ["fee", "submit", "valid", "renewal", "online", "apply for this", "portal"]
        if any(cue in lowered for cue in doc_type_cues):
            return ClarificationResult(
                question="Could you please specify which government document or application you are referring to (such as a passport, driving license, or PAN card)?",
                reason_code=ClarificationReasonCode.MISSING_DOCUMENT_TYPE,
                missing_dimensions=["document_type"],
            )

        # General unclear / opaque requests
        return ClarificationResult(
            question="Could you please provide more details on which government document or service you need help with?",
            reason_code=ClarificationReasonCode.UNCLEAR_REQUEST,
            missing_dimensions=["unclear_request"],
        )


def run_clarification_evaluation(
    dataset_path: Path,
    *,
    offline: bool = False,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    """Execute evaluation cases through the Clarification Node."""

    cases = load_cases(dataset_path)
    validate_case_ids(cases)

    if limit is not None and limit > 0:
        cases = cases[:limit]

    generator: ClarificationGenerator = (
        OfflineClarificationGenerator() if offline else OpenAIClarificationGenerator()
    )

    evaluated_cases: List[Dict[str, Any]] = []

    for case in cases:
        raw_input = case["input"]
        if isinstance(raw_input, str):
            query = raw_input
            messages: list[Any] = []
            summary = None
            round_count = 0
        else:
            query = raw_input.get("query", "")
            messages = raw_input.get("messages", [])
            summary = raw_input.get("conversation_summary")
            round_count = raw_input.get("clarification_round_count", 0)

        # Build State update matching production LangGraph state
        decision = IntentDecision(
            query=query,
            intent_type=IntentType.AMBIGUOUS,
            confidence_score=0.45,
        )
        state = {
            "intent_decision": decision,
            "messages": messages,
            "conversation_summary": summary,
            "clarification_round_count": round_count,
        }

        try:
            # Execute through the production ask_for_clarification node
            output = ask_for_clarification(state, generator)
            assistant_messages = output.get("messages", [])
            question_text = (
                assistant_messages[-1].content
                if assistant_messages
                else ""
            )

            # Reconstruct result object
            if hasattr(generator, "generate"):
                clar_input = ClarificationInput(
                    intent_type=IntentType.AMBIGUOUS,
                    classification_query=query,
                    messages=messages,
                    conversation_summary=summary,
                    clarification_round_count=round_count,
                )
                direct_res = generator.generate(clar_input)
                eval_payload = {
                    "question": question_text or direct_res.question,
                    "reason_code": str(direct_res.reason_code),
                    "missing_dimensions": direct_res.missing_dimensions,
                }
            else:
                eval_payload = {"question": question_text}

        except Exception as exc:
            logger.exception("Clarification execution failed for case %s: %s", case["id"], exc)
            eval_payload = {
                "question": "",
                "reason_code": "error",
                "missing_dimensions": [],
                "error": str(exc),
            }

        case_eval = evaluate_clarification_case(case, eval_payload)
        evaluated_cases.append(case_eval)

    summary = summarize_clarification_results(evaluated_cases)

    # Print human-readable report
    print("\n" + "=" * 60, flush=True)
    print("Clarification & Ambiguity Evaluation Summary", flush=True)
    print("=" * 60, flush=True)
    print(f"Mode:                     {'Offline (Deterministic)' if offline else 'Online (OpenAI gpt-4o-mini)'}")
    print(f"Total Cases:              {summary['total_cases']}")
    print(f"Cases Passed:             {summary['passed_cases']} ({summary['pass_rate']:.1%})")
    print(f"Reason Code Accuracy:     {summary['reason_code_accuracy']:.1%}")
    print(f"Average Dimension F1:     {summary['average_dimension_f1']:.4f}")
    print(f"Average Question Score:   {summary['average_question_score']:.4f}")
    print(f"Average Composite Score:  {summary['average_composite_score']:.4f}")
    print("-" * 60)
    print("Per-Reason Code Breakdown:")
    for code, stats in summary.get("per_reason_code", {}).items():
        print(f"  - {code:<28} Passed: {stats['passed']}/{stats['total']} ({stats['pass_rate']:.1%})")
    print("=" * 60 + "\n", flush=True)

    return {
        "metrics": summary,
        "cases": evaluated_cases,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset",
        type=Path,
        default=None,
        help="Path to evaluation cases JSON/JSONL file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Path to write JSON evaluation report.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Run deterministic offline evaluation without external LLM API calls ($0.00 cost).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional limit on number of cases to evaluate.",
    )
    langfuse_group = parser.add_mutually_exclusive_group()
    langfuse_group.add_argument(
        "--langfuse",
        action="store_true",
        help="Publish results to Langfuse (the default).",
    )
    langfuse_group.add_argument(
        "--no-langfuse",
        action="store_true",
        help="Skip Langfuse publishing.",
    )

    args = parser.parse_args()

    dataset_path = args.dataset or (
        PROJECT_ROOT / "evaluation/datasets/clarification/cases.json"
    )
    report = run_clarification_evaluation(
        dataset_path,
        offline=args.offline,
        limit=args.limit,
    )

    if not args.no_langfuse:
        run_name = "clarification_offline" if args.offline else "clarification"
        LangfuseReporter.from_environment().publish(run_name, report)

    rendered = json.dumps(report, indent=2)
    output_path = args.output or (
        PROJECT_ROOT / "evaluation/reports/clarification/latest.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered + "\n", encoding="utf-8")
    print(f"Report saved to: {output_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
