"""Evaluator for the Clarification & Ambiguity Node.

Scores clarification results across:
1. Reason Code Accuracy: Whether the diagnosed reason matches the expected category.
2. Missing Dimension Accuracy: Precision/Recall/F1 of identified missing information slots.
3. Question Quality: Interrogative structure, non-emptiness, and inclusion of targeted clarification cues.
"""

from __future__ import annotations

from typing import Any, Dict, List, Set


def evaluate_clarification_case(
    case: Dict[str, Any],
    result: Any,
) -> Dict[str, Any]:
    """Evaluate a single clarification result against expected case ground truth."""

    case_id = case.get("id", "UNKNOWN")
    expected_reason = str(case.get("expected_reason_code", "")).strip().lower()
    expected_dims: Set[str] = {
        str(d).strip().lower() for d in case.get("expected_missing_dimensions", [])
    }
    expected_cues: List[str] = case.get("expected_question_cues", [])

    # Extract result properties whether Pydantic model or dict
    if hasattr(result, "reason_code"):
        actual_reason = str(getattr(result, "reason_code", "")).strip().lower()
    elif isinstance(result, dict) and "reason_code" in result:
        actual_reason = str(result["reason_code"]).strip().lower()
    else:
        actual_reason = ""

    if hasattr(result, "missing_dimensions"):
        raw_dims = getattr(result, "missing_dimensions", []) or []
    elif isinstance(result, dict) and "missing_dimensions" in result:
        raw_dims = result.get("missing_dimensions", []) or []
    else:
        raw_dims = []
    actual_dims: Set[str] = {str(d).strip().lower() for d in raw_dims}

    if hasattr(result, "question"):
        actual_question = str(getattr(result, "question", "")).strip()
    elif isinstance(result, dict) and "question" in result:
        actual_question = str(result.get("question", "")).strip()
    elif isinstance(result, dict) and "message" in result:
        actual_question = str(result.get("message", "")).strip()
    else:
        actual_question = ""

    # 1. Reason Code Match
    # Strip enum prefixes like 'clarificationreasoncode.' if present
    clean_actual_reason = actual_reason.split(".")[-1]
    clean_expected_reason = expected_reason.split(".")[-1]
    reason_code_matched = bool(clean_actual_reason and clean_actual_reason == clean_expected_reason)

    # 2. Missing Dimensions Overlap (F1)
    if not expected_dims and not actual_dims:
        dim_precision = 1.0
        dim_recall = 1.0
        dim_f1 = 1.0
    elif not expected_dims or not actual_dims:
        dim_precision = 0.0
        dim_recall = 0.0
        dim_f1 = 0.0
    else:
        # Allow partial substring matching for dimension labels (e.g. "document_type" vs "document")
        matched_expected = set()
        matched_actual = set()
        for exp in expected_dims:
            for act in actual_dims:
                if exp in act or act in exp:
                    matched_expected.add(exp)
                    matched_actual.add(act)
        dim_precision = len(matched_actual) / len(actual_dims)
        dim_recall = len(matched_expected) / len(expected_dims)
        dim_f1 = (
            (2 * dim_precision * dim_recall) / (dim_precision + dim_recall)
            if (dim_precision + dim_recall) > 0
            else 0.0
        )

    # 3. Question Quality
    non_empty = bool(actual_question)
    is_interrogative = False
    cue_score = 0.0
    matched_cues: List[str] = []

    if non_empty:
        lowered_q = actual_question.lower()
        is_interrogative = lowered_q.endswith("?") or any(
            lowered_q.startswith(w) or f" {w} " in lowered_q
            for w in ["could", "can", "please", "what", "which", "where", "how", "specify", "tell"]
        )

        matched_cues = [c for c in expected_cues if c.lower() in lowered_q]
        target_cue_count = max(1, min(len(expected_cues), 2))
        cue_score = min(1.0, len(matched_cues) / target_cue_count)

    question_score = (
        (0.40 * (1.0 if is_interrogative else 0.0)) + (0.60 * cue_score)
        if non_empty
        else 0.0
    )

    # Composite Score
    # 45% reason code, 25% dimension F1, 30% question quality
    composite_score = (
        (0.45 * (1.0 if reason_code_matched else 0.0))
        + (0.25 * dim_f1)
        + (0.30 * question_score)
    )

    passed = bool(reason_code_matched and non_empty and composite_score >= 0.65)

    return {
        "id": case_id,
        "title": case.get("title", ""),
        "expected_reason_code": clean_expected_reason,
        "actual_reason_code": clean_actual_reason,
        "reason_code_matched": reason_code_matched,
        "expected_dimensions": sorted(expected_dims),
        "actual_dimensions": sorted(actual_dims),
        "dimension_f1": round(dim_f1, 4),
        "question": actual_question,
        "matched_cues": matched_cues,
        "question_score": round(question_score, 4),
        "composite_score": round(composite_score, 4),
        "passed": passed,
    }


def summarize_clarification_results(
    results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Aggregate metrics across a suite of evaluated clarification test cases."""

    total_cases = len(results)
    if total_cases == 0:
        return {
            "total_cases": 0,
            "passed_cases": 0,
            "pass_rate": 0.0,
            "reason_code_accuracy": 0.0,
            "average_dimension_f1": 0.0,
            "average_question_score": 0.0,
            "average_composite_score": 0.0,
            "per_reason_code": {},
        }

    passed_count = sum(1 for r in results if r.get("passed"))
    reason_matches = sum(1 for r in results if r.get("reason_code_matched"))
    avg_dim_f1 = sum(r.get("dimension_f1", 0.0) for r in results) / total_cases
    avg_q_score = sum(r.get("question_score", 0.0) for r in results) / total_cases
    avg_comp_score = sum(r.get("composite_score", 0.0) for r in results) / total_cases

    # Breakdown per reason code
    categories: Dict[str, Dict[str, int]] = {}
    for r in results:
        code = r.get("expected_reason_code", "unknown")
        if code not in categories:
            categories[code] = {"total": 0, "passed": 0}
        categories[code]["total"] += 1
        if r.get("passed"):
            categories[code]["passed"] += 1

    per_reason_metrics = {
        code: {
            "total": data["total"],
            "passed": data["passed"],
            "pass_rate": round(data["passed"] / data["total"], 4) if data["total"] > 0 else 0.0,
        }
        for code, data in categories.items()
    }

    return {
        "total_cases": total_cases,
        "passed_cases": passed_count,
        "pass_rate": round(passed_count / total_cases, 4),
        "reason_code_accuracy": round(reason_matches / total_cases, 4),
        "average_dimension_f1": round(avg_dim_f1, 4),
        "average_question_score": round(avg_q_score, 4),
        "average_composite_score": round(avg_comp_score, 4),
        "per_reason_code": per_reason_metrics,
    }
