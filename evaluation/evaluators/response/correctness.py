"""Factual correctness evaluator for generated responses."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union
from evaluation.evaluators.response.llm_judge import run_llm_judge

CORRECTNESS_INSTRUCTIONS = """
Evaluation Objective:
Determine whether the generated response provides factually correct information according to the Expected Answer (key points) and the supplied Retrieved Context.

Questions to consider:
1. Does the answer correctly answer the question?
2. Are the factual claims accurate and aligned with the expected key points?
3. Does it contradict the expected key points or supporting context?
4. Does it contain important factual errors, incorrect numbers, wrong procedures, or misleading statements?

Important Principle:
- Correctness evaluates factual accuracy against ground truth.
- Do NOT lower the score merely because the answer is concise or verbose if the stated facts are accurate.
- If the response includes accurate facts that agree with the key points, give a high score (0.8 - 1.0).
- If it makes minor factual inaccuracies, give a partial score (0.4 - 0.6).
- If it makes critical factual errors or directly contradicts ground truth, give a low score (0.0 - 0.2).
"""


def evaluate_correctness(
    query: str,
    generated_response: str,
    expected_answer: Union[str, Dict[str, Any]],
    context: Union[str, List[Dict[str, Any]], None] = None,
    llm: Optional[Any] = None,
) -> Dict[str, Any]:
    """Evaluate whether the generated response is factually correct.

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
        criterion="correctness",
        query=query,
        generated_response=generated_response,
        context=context,
        expected_answer=expected_answer,
        prompt_instructions=CORRECTNESS_INSTRUCTIONS,
        llm=llm,
    )
    return {
        "criterion": "correctness",
        "score": result.score,
        "reason": result.reason,
    }


__all__ = ["CORRECTNESS_INSTRUCTIONS", "evaluate_correctness"]
