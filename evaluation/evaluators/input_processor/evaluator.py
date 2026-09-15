"""Metrics for Input Processor evaluation."""

from __future__ import annotations

from typing import Any


def evaluate_input_case(
    case: dict[str, Any],
    *,
    actual_valid: bool,
    actual_modality: list[str],
) -> dict[str, Any]:
    """Compare one Input Processor result with its manually labelled case."""

    expected = case["expected"]
    expected_modality = list(expected.get("modality", []))
    valid_match = actual_valid == bool(expected["valid"])
    modality_match = actual_modality == expected_modality
    return {
        "id": case["id"],
        "expected_valid": bool(expected["valid"]),
        "actual_valid": actual_valid,
        "expected_modality": expected_modality,
        "actual_modality": actual_modality,
        "valid_match": valid_match,
        "modality_match": modality_match,
        "passed": valid_match and modality_match,
    }


def summarize_input_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate separate validation and modality accuracy metrics."""

    total = len(results)
    if not total:
        raise ValueError("Cannot summarize an empty evaluation")
    valid_correct = sum(result["valid_match"] for result in results)
    modality_correct = sum(result["modality_match"] for result in results)
    return {
        "total_cases": total,
        "valid_accuracy": valid_correct / total,
        "modality_accuracy": modality_correct / total,
        "passed_cases": sum(result["passed"] for result in results),
        "failed_cases": total - sum(result["passed"] for result in results),
    }
