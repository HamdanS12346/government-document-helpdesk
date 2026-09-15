"""Context faithfulness (grounding) evaluator for generated responses."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union
from evaluation.evaluators.response.llm_judge import run_llm_judge

FAITHFULNESS_INSTRUCTIONS = """
Evaluation Objective:
Determine whether the generated response is strictly grounded in and supported by the Retrieved Context.

Questions to consider:
1. Are all substantive claims in the response supported by the retrieved context?
2. Does the response introduce facts, document requirements, fees, dates, or portal URLs that are completely absent from the retrieved context?
3. Does it make unsupported assumptions or extrapolations?
4. Does it hallucinate facts?
5. Does it directly contradict any information in the retrieved context?

Important Principle:
- Faithfulness focuses on GROUNDING, not general plausibility or query relevance.
- A response might sound helpful, but if it mentions requirements (e.g. "two passport photos") that are NOT in the context, it is UNFAITHFUL.
- If all claims are completely supported by the context: score 1.0.
- If most claims are supported with minor ungrounded flourishes: score 0.7 - 0.8.
- If several substantive claims lack context support: score 0.4 - 0.6.
- If the response extensively hallucinates or contradicts the context: score 0.0 - 0.2.
- Note: If no context was provided or context was empty, an honest refusal or admission is faithful (score 1.0), whereas inventing facts is completely unfaithful (score 0.0).
"""


def evaluate_faithfulness(
    query: str,
    generated_response: str,
    context: Union[str, List[Dict[str, Any]], None],
    llm: Optional[Any] = None,
) -> Dict[str, Any]:
    """Evaluate whether the generated response is faithful to the retrieved context.

    Args:
        query: User query.
        generated_response: Generated chatbot response.
        context: Retrieved context chunks that were supplied to the model.
        llm: Injected chat model for testing.

    Returns:
        Dict with keys: criterion, score, reason.
    """
    result = run_llm_judge(
        criterion="faithfulness",
        query=query,
        generated_response=generated_response,
        context=context,
        prompt_instructions=FAITHFULNESS_INSTRUCTIONS,
        llm=llm,
    )
    return {
        "criterion": "faithfulness",
        "score": result.score,
        "reason": result.reason,
    }


__all__ = ["FAITHFULNESS_INSTRUCTIONS", "evaluate_faithfulness"]
