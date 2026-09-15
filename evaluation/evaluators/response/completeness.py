"""Completeness evaluator for generated responses."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union
from evaluation.evaluators.response.llm_judge import run_llm_judge

COMPLETENESS_INSTRUCTIONS = """
Evaluation Objective:
Determine whether the generated response covers all essential key points expected for the query, based on the Expected Answer key points.

Questions to consider:
1. Are all important expected key points included in the response?
2. Does the response omit critical eligibility criteria, mandatory documents, fees, or procedural steps?
3. If the citizen's query contains multiple parts, are all parts adequately addressed?
4. Is the coverage thorough enough that the citizen gets actionable guidance without missing key conditions?

Important Principle:
- Completeness does NOT mean maximum length or word count. A crisp, concise answer is completely sufficient if all key points are covered.
- If all expected key points are covered: score 1.0.
- If most key points are covered but one minor aspect is missing: score 0.7 - 0.8.
- If roughly half of the key points are missing: score 0.4 - 0.5.
- If the response only provides a partial or superficial answer missing critical points: score 0.1 - 0.3.
- If none of the expected key points are present: score 0.0.
"""


def evaluate_completeness(
    query: str,
    generated_response: str,
    expected_answer: Union[str, Dict[str, Any]],
    context: Union[str, List[Dict[str, Any]], None] = None,
    llm: Optional[Any] = None,
) -> Dict[str, Any]:
    """Evaluate whether the generated response thoroughly covers the expected key points.

    Args:
        query: User query.
        generated_response: Generated chatbot response.
        expected_answer: Expected answer key points or ground truth text.
        context: Optional retrieved context chunks.
        llm: Injected chat model for testing.

    Returns:
        Dict with keys: criterion, score, reason.
    """
    result = run_llm_judge(
        criterion="completeness",
        query=query,
        generated_response=generated_response,
        context=context,
        expected_answer=expected_answer,
        prompt_instructions=COMPLETENESS_INSTRUCTIONS,
        llm=llm,
    )
    return {
        "criterion": "completeness",
        "score": result.score,
        "reason": result.reason,
    }


__all__ = ["COMPLETENESS_INSTRUCTIONS", "evaluate_completeness"]
