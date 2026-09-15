"""Case-level response evaluation and summary metrics calculation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from evaluation.evaluators.response.citation import evaluate_citation
from evaluation.evaluators.response.completeness import evaluate_completeness
from evaluation.evaluators.response.correctness import evaluate_correctness
from evaluation.evaluators.response.faithfulness import evaluate_faithfulness
from evaluation.evaluators.response.relevance import evaluate_relevance
from evaluation.evaluators.response.safety import evaluate_safety

ALL_CRITERIA = (
    "correctness",
    "faithfulness",
    "relevance",
    "completeness",
    "citation",
    "safety",
)

DEFAULT_PASS_THRESHOLD = 0.70


def evaluate_response_case(
    case: Dict[str, Any],
    generated_response: str,
    llm: Optional[Any] = None,
    criteria: Optional[List[str]] = None,
    pass_threshold: float = DEFAULT_PASS_THRESHOLD,
) -> Dict[str, Any]:
    """Evaluate a single test case across all response quality dimensions.

    Args:
        case: Dictionary containing query, context, expected_answer, expected_citations.
        generated_response: The chatbot's generated reply.
        llm: Injected chat model instance for the judge.
        criteria: Optional subset of criteria to evaluate (defaults to all 6).
        pass_threshold: Minimum overall score for the case to be considered passing.

    Returns:
        Dict containing per-criterion scores, reasoning, composite score, and pass status.
    """
    selected_criteria = list(criteria or ALL_CRITERIA)

    query = case.get("query", "")
    context = case.get("context")
    expected_answer = case.get("expected_answer")
    expected_citations = case.get("expected_citations")

    scores: Dict[str, float] = {}
    reasons: Dict[str, str] = {}

    for crit in selected_criteria:
        if crit == "correctness":
            res = evaluate_correctness(query, generated_response, expected_answer, context, llm=llm)
        elif crit == "faithfulness":
            res = evaluate_faithfulness(query, generated_response, context, llm=llm)
        elif crit == "relevance":
            res = evaluate_relevance(query, generated_response, context, llm=llm)
        elif crit == "completeness":
            res = evaluate_completeness(query, generated_response, expected_answer, context, llm=llm)
        elif crit == "citation":
            res = evaluate_citation(query, generated_response, context, expected_citations, llm=llm)
        elif crit == "safety":
            res = evaluate_safety(query, generated_response, context, expected_answer, llm=llm)
        else:
            continue

        scores[crit] = res["score"]
        reasons[crit] = res["reason"]

    valid_scores = [scores[c] for c in selected_criteria if c in scores]
    avg_score = sum(valid_scores) / len(valid_scores) if valid_scores else 0.0

    # Safety requirement: if safety is evaluated and fails (<0.6), case fails regardless of average
    safety_ok = scores.get("safety", 1.0) >= 0.6
    passed = (avg_score >= pass_threshold) and safety_ok

    return {
        "id": case.get("id", "UNKNOWN"),
        "query": query,
        "generated_response": generated_response,
        "scores": scores,
        "reasons": reasons,
        "average_score": round(avg_score, 4),
        "passed": passed,
    }


def summarize_response_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate individual case results into overall metrics.

    Args:
        results: List of case results produced by evaluate_response_case.

    Returns:
        Summary dictionary with average scores per criterion and overall pass statistics.
    """
    if not results:
        return {
            "total_cases": 0,
            "overall_score": 0.0,
            "pass_rate": 0.0,
            "passed_cases": 0,
            "failed_cases": 0,
        }

    total = len(results)
    passed_cases = sum(1 for r in results if r.get("passed", False))

    metrics: Dict[str, Any] = {
        "total_cases": total,
        "passed_cases": passed_cases,
        "failed_cases": total - passed_cases,
        "pass_rate": round(passed_cases / total, 4),
    }

    # Aggregate each criterion's average score
    for crit in ALL_CRITERIA:
        crit_values = [
            r["scores"][crit]
            for r in results
            if "scores" in r and crit in r["scores"]
        ]
        if crit_values:
            metrics[f"average_{crit}"] = round(sum(crit_values) / len(crit_values), 4)

    # Calculate overall average across all cases
    avg_scores = [r.get("average_score", 0.0) for r in results]
    metrics["overall_score"] = round(sum(avg_scores) / total, 4) if avg_scores else 0.0

    return metrics


__all__ = [
    "ALL_CRITERIA",
    "DEFAULT_PASS_THRESHOLD",
    "evaluate_response_case",
    "summarize_response_results",
]
