"""Run the Intent Classifier evaluation dataset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.contracts.intent_decision import IntentDecision  # noqa: E402
from app.contracts.normalized_input import NormalizedInput  # noqa: E402
from app.intent.classifier import OpenAIIntentClassifier  # noqa: E402
from app.intent.node import classify_intent  # noqa: E402
from evaluation.case_loader import find_default_dataset, load_cases, validate_case_ids  # noqa: E402
from evaluation.evaluators.intent.evaluator import (  # noqa: E402
    evaluate_intent_case,
    summarize_intent_results,
)
from evaluation.langfuse_reporting import LangfuseReporter  # noqa: E402


class OfflineIntentClassifier:
    """Deterministic baseline for local evaluation without an API call."""

    _document_terms = {
        "passport", "visa", "oci", "certificate", "document", "application",
        "government", "benefit", "identity", "residence", "tax", "disability",
    }
    _information_terms = {
        "what", "which", "how", "who", "where", "when", "why", "can", "cost",
        "fee", "eligible", "required", "documents", "procedure", "apply", "status",
    }

    def classify(self, query: str) -> IntentDecision:
        lowered = query.lower()
        words = set(lowered.replace("?", " ").split())
        has_document = bool(words & self._document_terms)
        has_information_request = bool(words & self._information_terms)
        if has_document and has_information_request and len(words) > 3:
            intent = "document_info"
        elif has_document or len(words) <= 4:
            intent = "ambiguous"
        else:
            intent = "general_chat"
        return IntentDecision(query=query, intent_type=intent, confidence_score=0.5)


def run_dataset(dataset_path: Path, *, offline: bool) -> dict[str, Any]:
    cases = load_cases(dataset_path)
    validate_case_ids(cases)
    classifier = OfflineIntentClassifier() if offline else OpenAIIntentClassifier()
    results = []
    for case in cases:
        state = {
            "normalized_input": NormalizedInput(
                user_query=str(case["input"]),
                image_content=[],
                pdf_content=[],
                combined_text=f"<USER_QUERY>\n{case['input']}",
            ),
            "messages": [],
            "conversation_summary": "",
        }
        decision = classify_intent(state, classifier)
        results.append(evaluate_intent_case(case, decision["intent_decision"].intent_type.value))
    return {"metrics": summarize_intent_results(results), "cases": results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Use a deterministic baseline instead of making OpenAI API calls.",
    )
    parser.add_argument(
        "--langfuse",
        action="store_true",
        help="Publish aggregate and per-case scores to Langfuse.",
    )
    args = parser.parse_args()
    dataset = args.dataset or find_default_dataset(PROJECT_ROOT / "evaluation/datasets/intent")
    report = run_dataset(dataset, offline=args.offline)
    if args.langfuse:
        LangfuseReporter.from_environment().publish("intent_offline" if args.offline else "intent", report)
    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
