"""Metrics for Intent Classifier evaluation."""

from __future__ import annotations

from collections import Counter
from typing import Any

from app.contracts.intent_decision import IntentType


INTENTS = [intent.value for intent in IntentType]


def evaluate_intent_case(case: dict[str, Any], actual_intent: str) -> dict[str, Any]:
    """Compare one predicted intent with manually labelled ground truth."""

    expected_intent = case["expected_intent"]
    return {
        "id": case["id"],
        "input": case["input"],
        "expected_intent": expected_intent,
        "actual_intent": actual_intent,
        "passed": expected_intent == actual_intent,
    }


def summarize_intent_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate accuracy, per-class precision/recall/F1, and confusion matrix."""

    if not results:
        raise ValueError("Cannot summarize an empty evaluation")

    confusion = {expected: {actual: 0 for actual in INTENTS} for expected in INTENTS}
    for result in results:
        expected = result["expected_intent"]
        actual = result["actual_intent"]
        if expected not in confusion:
            raise ValueError(f"Unsupported expected intent: {expected}")
        if actual not in INTENTS:
            raise ValueError(f"Unsupported predicted intent: {actual}")
        confusion[expected][actual] += 1

    per_class: dict[str, dict[str, float]] = {}
    for intent in INTENTS:
        true_positive = confusion[intent][intent]
        false_positive = sum(confusion[other][intent] for other in INTENTS if other != intent)
        false_negative = sum(confusion[intent][other] for other in INTENTS if other != intent)
        precision = _ratio(true_positive, true_positive + false_positive)
        recall = _ratio(true_positive, true_positive + false_negative)
        f1 = _ratio(2 * precision * recall, precision + recall)
        per_class[intent] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": sum(confusion[intent].values()),
        }

    total = len(results)
    return {
        "total_cases": total,
        "accuracy": sum(result["passed"] for result in results) / total,
        "macro_precision": sum(item["precision"] for item in per_class.values()) / len(INTENTS),
        "macro_recall": sum(item["recall"] for item in per_class.values()) / len(INTENTS),
        "macro_f1": sum(item["f1"] for item in per_class.values()) / len(INTENTS),
        "per_class": per_class,
        "confusion_matrix": confusion,
    }


def _ratio(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0
