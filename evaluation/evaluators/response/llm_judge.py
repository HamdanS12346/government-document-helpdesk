"""Shared LLM-as-a-Judge engine for Response Node evaluation."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

DEFAULT_JUDGE_MODEL = "gpt-4o-mini"

STANDARD_SCORE_SCALE = """
Score Scale:
- 0.0: Complete failure
- 0.2: Mostly fails
- 0.4: Significant problems
- 0.6: Partially satisfies
- 0.8: Mostly satisfies
- 1.0: Fully satisfies
(Intermediate values such as 0.5, 0.7, 0.85, 0.9 may be used when appropriate.)
"""


class JudgeResult(BaseModel):
    """Structured evaluation output returned by the LLM judge."""

    score: float = Field(..., description="Normalized evaluation score between 0.0 and 1.0.")
    reason: str = Field(..., description="Detailed explanation supporting the score.")
    criterion: Optional[str] = Field(default=None, description="Evaluation criterion name.")
    error: Optional[str] = Field(default=None, description="Error message if the evaluation failed.")

    @field_validator("score")
    @classmethod
    def validate_score_range(cls, v: float) -> float:
        if v < 0.0 or v > 1.0:
            raise ValueError(f"Score must be between 0.0 and 1.0, got {v}")
        return round(float(v), 4)


class JudgeEvaluationError(Exception):
    """Raised when the LLM judge encounters an unrecoverable failure."""
    pass


def format_context(context: Union[str, List[Dict[str, Any]], None]) -> str:
    """Format diverse context representations into a uniform string."""
    if not context:
        return "None provided"
    if isinstance(context, str):
        return context.strip() or "None provided"
    if isinstance(context, list):
        formatted_chunks = []
        for i, item in enumerate(context, 1):
            if isinstance(item, dict):
                chunk_id = item.get("chunk_id", f"chunk-{i}")
                url = item.get("source_url", "")
                text = item.get("text", "")
                header = f"[{chunk_id}]" + (f" ({url})" if url else "")
                formatted_chunks.append(f"{header}:\n{text}")
            else:
                formatted_chunks.append(f"[{i}]:\n{str(item)}")
        return "\n\n".join(formatted_chunks)
    return str(context)


def format_expected_answer(expected_answer: Union[str, Dict[str, Any], None]) -> str:
    """Format expected answer or key points into a string."""
    if not expected_answer:
        return "None provided"
    if isinstance(expected_answer, str):
        return expected_answer.strip()
    if isinstance(expected_answer, dict):
        key_points = expected_answer.get("key_points")
        if isinstance(key_points, list):
            return "\n".join(f"- {p}" for p in key_points)
        return json.dumps(expected_answer, indent=2)
    return str(expected_answer)


def run_llm_judge(
    criterion: str,
    query: str,
    generated_response: str,
    context: Union[str, List[Dict[str, Any]], None] = None,
    expected_answer: Union[str, Dict[str, Any], None] = None,
    expected_citations: Optional[List[str]] = None,
    prompt_instructions: str = "",
    model: str = DEFAULT_JUDGE_MODEL,
    llm: Optional[Any] = None,
) -> JudgeResult:
    """Execute the shared LLM-as-a-judge evaluation for a specific criterion.

    Args:
        criterion: The dimension being evaluated (e.g., 'correctness', 'faithfulness').
        query: The citizen's query.
        generated_response: The chatbot's generated response.
        context: The retrieved document context provided to the model.
        expected_answer: Ground truth key points or target answer.
        expected_citations: Ground truth expected source URLs or document IDs.
        prompt_instructions: Criterion-specific instructions for the judge.
        model: OpenAI model name (default: gpt-4o-mini).
        llm: Injected LangChain chat model instance (used for testing).

    Returns:
        JudgeResult containing normalized score and reasoning.

    Raises:
        JudgeEvaluationError: If the judge cannot produce a valid score.
    """
    system_prompt = f"""You are an expert impartial judge evaluating an AI government document helpdesk chatbot.
Your task is to evaluate the chatbot's response strictly on the criterion of: **{criterion.upper()}**.

{prompt_instructions}

{STANDARD_SCORE_SCALE}

Rules:
1. Evaluate ONLY the specified criterion ({criterion}). Do not penalize or reward for other criteria.
2. Return a valid JSON object with exactly two keys:
   - "score": A float between 0.0 and 1.0 according to the scale.
   - "reason": A clear, concise explanation justifying the score.
"""

    user_prompt = f"""### User Query:
{query}

### Retrieved Context:
{format_context(context)}

### Generated Response:
{generated_response}
"""

    if expected_answer is not None:
        user_prompt += f"""
### Expected Answer / Key Points:
{format_expected_answer(expected_answer)}
"""

    if expected_citations is not None:
        user_prompt += f"""
### Expected Citations:
{json.dumps(expected_citations, indent=2)}
"""

    user_prompt += """
Provide your evaluation in the required structured JSON format:
{
  "score": <float between 0.0 and 1.0>,
  "reason": "<justification for the score>"
}
"""

    try:
        active_llm = llm
        if active_llm is None:
            from langchain_openai import ChatOpenAI
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise JudgeEvaluationError("OPENAI_API_KEY is required to run the LLM judge.")
            active_llm = ChatOpenAI(
                model=model,
                temperature=0.0,
                api_key=api_key,
            )

        # Attempt structured output if supported
        raw_output = None
        if hasattr(active_llm, "with_structured_output"):
            try:
                structured_chain = active_llm.with_structured_output(JudgeResult)
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ]
                res = structured_chain.invoke(messages)
                if isinstance(res, JudgeResult):
                    res.criterion = criterion
                    return res
                if isinstance(res, dict) and "score" in res:
                    return JudgeResult(
                        score=res["score"],
                        reason=res.get("reason", ""),
                        criterion=criterion,
                    )
            except Exception as exc:
                logger.debug("Structured output call failed, falling back to prompt invocation: %s", exc)

        # Fallback / standard invoke
        from langchain_core.messages import HumanMessage, SystemMessage
        response = active_llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])

        raw_text = response.content if hasattr(response, "content") else str(response)
        raw_output = raw_text

        parsed = _parse_judge_json(raw_text)
        score = float(parsed["score"])
        reason = str(parsed.get("reason", "")).strip()

        return JudgeResult(score=score, reason=reason, criterion=criterion)

    except Exception as exc:
        err_msg = f"LLM Judge failure on criterion '{criterion}': {exc}"
        logger.error(err_msg)
        raise JudgeEvaluationError(err_msg) from exc


def _parse_judge_json(text: str) -> Dict[str, Any]:
    """Parse JSON from LLM response text, extracting from markdown code blocks if necessary."""
    text = text.strip()
    # Check for markdown code blocks
    code_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if code_match:
        text = code_match.group(1).strip()

    try:
        data = json.loads(text)
        if isinstance(data, dict) and "score" in data:
            return data
    except Exception:
        pass

    # Regex search for {"score": ..., "reason": ...}
    match = re.search(r"\{\s*\"score\"\s*:\s*([0-9.]+)\s*,\s*\"reason\"\s*:\s*\"([^\"]+)\"\s*\}", text)
    if match:
        return {"score": float(match.group(1)), "reason": match.group(2)}

    raise ValueError(f"Could not parse valid judge JSON from response: {text[:200]}")


__all__ = [
    "DEFAULT_JUDGE_MODEL",
    "JudgeEvaluationError",
    "JudgeResult",
    "STANDARD_SCORE_SCALE",
    "format_context",
    "format_expected_answer",
    "run_llm_judge",
]
