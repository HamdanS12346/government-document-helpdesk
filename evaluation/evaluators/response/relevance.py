"""Query relevance evaluator for generated responses."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union
from evaluation.evaluators.response.llm_judge import run_llm_judge

RELEVANCE_INSTRUCTIONS = """
Evaluation Objective:
Determine whether the generated response directly and effectively addresses the user's query.

Questions to consider:
1. Does the response directly answer the specific question asked by the citizen?
2. Does it stay focused on the user's request, or does it wander off-topic?
3. Does it misunderstand the user's core intent?
4. Does it frontload irrelevant history, generic preamble, or excessive tangential details?

Important Principle:
- Relevance evaluates whether the response answers the specific question that was asked.
- An answer can be completely factual and grounded, but still poor in relevance if it dodges or misunderstands the prompt.
- If the response directly and clearly addresses the question: score 0.9 - 1.0.
- If it answers the question but contains excessive tangential or filler information: score 0.6 - 0.8.
- If it only partially addresses the prompt or focuses on the wrong aspect: score 0.3 - 0.5.
- If it completely ignores or misunderstands the user's question: score 0.0 - 0.2.
"""


def evaluate_relevance(
    query: str,
    generated_response: str,
    context: Union[str, List[Dict[str, Any]], None] = None,
    llm: Optional[Any] = None,
) -> Dict[str, Any]:
    """Evaluate whether the generated response is relevant to the user query.

    Args:
        query: User query.
        generated_response: Generated chatbot response.
        context: Optional retrieved context chunks.
        llm: Injected chat model for testing.

    Returns:
        Dict with keys: criterion, score, reason.
    """
    result = run_llm_judge(
        criterion="relevance",
        query=query,
        generated_response=generated_response,
        context=context,
        prompt_instructions=RELEVANCE_INSTRUCTIONS,
        llm=llm,
    )
    return {
        "criterion": "relevance",
        "score": result.score,
        "reason": result.reason,
    }


__all__ = ["RELEVANCE_INSTRUCTIONS", "evaluate_relevance"]
