"""Claim-level Hallucination and Unsupported Information Evaluator.

Performs claim-level extraction and context-grounding analysis to detect
hallucinations, unsupported factual claims, and verify appropriate handling
of missing information or false premises.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv

from evaluation.evaluators.response.llm_judge import (
    DEFAULT_JUDGE_MODEL,
    format_context,
    format_expected_answer,
)

load_dotenv()
logger = logging.getLogger(__name__)

DEFAULT_PASS_THRESHOLD = 0.70


class ClaimItem(BaseModel):
    """Claim-level analysis detail for an individual factual statement."""

    claim: str = Field(..., description="The factual claim extracted from the response.")
    supported: bool = Field(
        ...,
        description="Whether the claim is strictly supported by the retrieved context.",
    )
    evidence: Optional[str] = Field(
        default=None,
        description="Direct quote or snippet from context supporting the claim, or null if unsupported.",
    )


class HallucinationJudgeOutput(BaseModel):
    """Structured evaluation output returned by the hallucination evaluator."""

    score: float = Field(
        ...,
        description="Hallucination score (ratio of supported claims to total claims, or 1.0 if appropriate refusal).",
    )
    hallucination_detected: bool = Field(
        ...,
        description="True if one or more factual claims are unsupported by the retrieved context.",
    )
    claims: List[ClaimItem] = Field(
        default_factory=list,
        description="List of individual factual claims and their context-support verdict.",
    )
    unsupported_claims: int = Field(
        default=0,
        description="Count of factual claims unsupported by the retrieved context.",
    )
    unsupported_information_handling: float = Field(
        default=1.0,
        description="Score between 0.0 and 1.0 measuring handling of missing info or false premises.",
    )
    reason: str = Field(
        ...,
        description="Detailed justification and explanation of the evaluation verdict.",
    )

    @field_validator("score", "unsupported_information_handling")
    @classmethod
    def validate_score_range(cls, v: float) -> float:
        if v < 0.0 or v > 1.0:
            raise ValueError(f"Score must be between 0.0 and 1.0, got {v}")
        return round(float(v), 4)


HALLUCINATION_SYSTEM_PROMPT = """You are an expert impartial judge evaluating an AI government document helpdesk chatbot for HALLUCINATION and UNSUPPORTED INFORMATION.

Your task is to perform CLAIM-LEVEL ANALYSIS on the chatbot response:
1. Extract all substantive factual claims made in the chatbot's response.
   - A factual claim is an assertion about government procedures, documents, eligibility, fees, deadlines, timeframes, requirements, or entities.
   - IMPORTANT: Statements acknowledging missing information or expressing uncertainty (e.g. "The provided context does not specify the processing time", "No information is available regarding...", "I cannot verify...") are NOT unsupported factual claims. Do NOT extract them as unsupported claims!
2. Compare each factual claim against the RETRIEVED CONTEXT:
   - STRICT GROUNDING RULE: Evaluate support ONLY against the provided Retrieved Context. DO NOT use outside world knowledge. Even if a claim is factually true in real life, if it is NOT in the retrieved context, it must be marked as supported: false.
   - Paraphrasing and semantic equivalence are allowed (exact verbatim wording is not required).
3. Evaluate UNSUPPORTED INFORMATION HANDLING:
   - Did the chatbot avoid guessing or fabricating missing information?
   - If the user query asked for information absent from the context, did the chatbot clearly state that the information is unavailable?
   - If the user query included a false premise (e.g. a non-existent discount or rule), did the chatbot challenge or avoid accepting that premise?
   - Handling score guide:
     * 1.0: The response is fully grounded, OR it appropriately acknowledged that information was unavailable / refused to guess / challenged false premise.
     * 0.5: The response partially guessed or gave ambiguous ungrounded details.
     * 0.0: The response fabricated unavailable facts, invented numbers/fees/dates, or blindly accepted a false premise as true.
4. Calculate the HALLUCINATION SCORE:
   - If there are factual claims: score = (number of supported claims) / (total factual claims).
   - If there are NO factual claims because the chatbot correctly refused or acknowledged missing info: score = 1.0.
   - If unsupported_claims > 0: hallucination_detected = true, else false.

Return a valid JSON object matching this schema:
{
  "score": <float between 0.0 and 1.0>,
  "hallucination_detected": <boolean>,
  "claims": [
    {
      "claim": "<extracted claim>",
      "supported": <boolean>,
      "evidence": "<context quote or null>"
    }
  ],
  "unsupported_claims": <integer count of unsupported claims>,
  "unsupported_information_handling": <float between 0.0 and 1.0>,
  "reason": "<clear concise explanation>"
}
"""


def _parse_hallucination_json(text: str) -> Dict[str, Any]:
    """Parse JSON from LLM response text, extracting markdown blocks if needed."""
    text = text.strip()
    code_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if code_match:
        text = code_match.group(1).strip()

    try:
        data = json.loads(text)
        if isinstance(data, dict) and "score" in data:
            return data
    except Exception:
        pass

    # Regex search fallback
    match = re.search(
        r"\{\s*\"score\"\s*:\s*([0-9.]+)\s*,\s*\"hallucination_detected\"\s*:\s*(true|false)",
        text,
        re.IGNORECASE,
    )
    if match:
        try:
            # Try to grab the entire outer json object
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1:
                return json.loads(text[start : end + 1])
        except Exception:
            pass

    raise ValueError(f"Could not parse valid hallucination judge JSON from response: {text[:250]}")


def run_hallucination_judge(
    query: str,
    generated_response: str,
    retrieved_context: Union[str, List[Dict[str, Any]], List[str], None],
    expected_behavior: str = "supported",
    expected_key_points: Optional[List[str]] = None,
    model: str = DEFAULT_JUDGE_MODEL,
    llm: Optional[Any] = None,
) -> HallucinationJudgeOutput:
    """Execute LLM claim-level analysis for hallucination evaluation.

    Args:
        query: Citizen's query.
        generated_response: Chatbot's generated reply.
        retrieved_context: Retrieved documents or text provided to the chatbot.
        expected_behavior: Expected behavior mode ('supported', 'should_not_guess', 'challenge_premise').
        expected_key_points: Optional list of expected key points.
        model: Model name for LLM judge (default: gpt-4o-mini).
        llm: Injected chat model instance for testing.

    Returns:
        HallucinationJudgeOutput containing claim breakdown and scores.
    """
    user_prompt = f"""### User Query:
{query}

### Retrieved Context:
{format_context(retrieved_context)}

### Chatbot Response:
{generated_response}

### Expected Behavior:
{expected_behavior}
"""

    if expected_key_points:
        user_prompt += f"""
### Expected Key Points:
{format_expected_answer({'key_points': expected_key_points})}
"""

    user_prompt += """
Provide your evaluation in the required JSON format:
{
  "score": <float between 0.0 and 1.0>,
  "hallucination_detected": <true or false>,
  "claims": [
    {
      "claim": "<statement>",
      "supported": <true or false>,
      "evidence": "<context quote or null>"
    }
  ],
  "unsupported_claims": <int>,
  "unsupported_information_handling": <float between 0.0 and 1.0>,
  "reason": "<explanation>"
}
"""

    try:
        active_llm = llm
        if active_llm is None:
            from langchain_openai import ChatOpenAI

            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise RuntimeError("OPENAI_API_KEY is required to run the Hallucination Judge.")
            active_llm = ChatOpenAI(
                model=model,
                temperature=0.0,
                api_key=api_key,
            )

        # Attempt structured output if supported
        if hasattr(active_llm, "with_structured_output"):
            try:
                structured_chain = active_llm.with_structured_output(HallucinationJudgeOutput)
                messages = [
                    {"role": "system", "content": HALLUCINATION_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ]
                res = structured_chain.invoke(messages)
                if isinstance(res, HallucinationJudgeOutput):
                    return res
                if isinstance(res, dict) and "score" in res:
                    return HallucinationJudgeOutput(**res)
            except Exception as exc:
                logger.debug("Structured output call failed, falling back: %s", exc)

        # Fallback standard invoke
        from langchain_core.messages import HumanMessage, SystemMessage

        response = active_llm.invoke(
            [
                SystemMessage(content=HALLUCINATION_SYSTEM_PROMPT),
                HumanMessage(content=user_prompt),
            ]
        )
        raw_text = response.content if hasattr(response, "content") else str(response)
        parsed = _parse_hallucination_json(raw_text)

        # Ensure claims items conform to ClaimItem
        raw_claims = parsed.get("claims", [])
        clean_claims: List[ClaimItem] = []
        for c in raw_claims:
            if isinstance(c, dict):
                clean_claims.append(
                    ClaimItem(
                        claim=str(c.get("claim", "")),
                        supported=bool(c.get("supported", False)),
                        evidence=c.get("evidence"),
                    )
                )

        unsupported_count = parsed.get(
            "unsupported_claims",
            sum(1 for c in clean_claims if not c.supported),
        )

        return HallucinationJudgeOutput(
            score=float(parsed["score"]),
            hallucination_detected=bool(parsed.get("hallucination_detected", unsupported_count > 0)),
            claims=clean_claims,
            unsupported_claims=int(unsupported_count),
            unsupported_information_handling=float(
                parsed.get("unsupported_information_handling", 1.0)
            ),
            reason=str(parsed.get("reason", "")).strip(),
        )

    except Exception as exc:
        err_msg = f"Hallucination Judge failure: {exc}"
        logger.error(err_msg)
        raise RuntimeError(err_msg) from exc


def evaluate_hallucination_case(
    case: Dict[str, Any],
    generated_response: str,
    retrieved_context: Union[str, List[Dict[str, Any]], List[str], None] = None,
    llm: Optional[Any] = None,
    pass_threshold: float = DEFAULT_PASS_THRESHOLD,
) -> Dict[str, Any]:
    """Evaluate a single test case for hallucination and unsupported information.

    Args:
        case: Case dictionary from cases.jsonl.
        generated_response: The chatbot's generated reply.
        retrieved_context: Optional context override (defaults to case['context'] if present).
        llm: Injected chat model instance.
        pass_threshold: Minimum score required for case to pass.

    Returns:
        Structured evaluation result dict.
    """
    query = case.get("query", "")
    context = retrieved_context if retrieved_context is not None else case.get("context")
    expected_behavior = case.get("expected_behavior", "supported")
    expected_key_points = case.get("expected_key_points", [])

    judge_output = run_hallucination_judge(
        query=query,
        generated_response=generated_response,
        retrieved_context=context,
        expected_behavior=expected_behavior,
        expected_key_points=expected_key_points,
        llm=llm,
    )

    total_claims = len(judge_output.claims)
    supported_claims = sum(1 for c in judge_output.claims if c.supported)

    # A case passes if score meets threshold and no hallucinations are detected
    passed = (
        (judge_output.score >= pass_threshold)
        and (not judge_output.hallucination_detected)
        and (judge_output.unsupported_information_handling >= pass_threshold)
    )

    return {
        "id": case.get("id", "UNKNOWN"),
        "query": query,
        "generated_response": generated_response,
        "score": judge_output.score,
        "hallucination_detected": judge_output.hallucination_detected,
        "claims": [c.model_dump() for c in judge_output.claims],
        "supported_claims": supported_claims,
        "unsupported_claims": judge_output.unsupported_claims,
        "total_claims": total_claims,
        "unsupported_information_handling": judge_output.unsupported_information_handling,
        "reason": judge_output.reason,
        "passed": passed,
        "expected_behavior": expected_behavior,
        "metadata": case.get("metadata", {}),
    }


def summarize_hallucination_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate individual case results into overall metrics matching Section 21 of plan.

    Args:
        results: List of case evaluation result dictionaries.

    Returns:
        Dictionary containing aggregate hallucination metrics.
    """
    total_cases = len(results)
    if total_cases == 0:
        return {
            "total_cases": 0,
            "average_hallucination_score": 0.0,
            "hallucination_rate": 0.0,
            "unsupported_claim_rate": 0.0,
            "unsupported_information_handling": 0.0,
            "cases_with_hallucinations": 0,
            "cases_correctly_handling_missing_information": 0,
            "passed_cases": 0,
            "failed_cases": 0,
        }

    total_claims = sum(r.get("total_claims", 0) for r in results)
    total_unsupported_claims = sum(r.get("unsupported_claims", 0) for r in results)
    cases_with_hallucinations = sum(1 for r in results if r.get("hallucination_detected", False))
    cases_handling_missing = sum(
        1 for r in results if r.get("unsupported_information_handling", 0.0) >= 0.8
    )
    passed_cases = sum(1 for r in results if r.get("passed", False))

    avg_score = sum(r.get("score", 0.0) for r in results) / total_cases
    avg_handling = sum(r.get("unsupported_information_handling", 0.0) for r in results) / total_cases

    hallucination_rate = cases_with_hallucinations / total_cases
    unsupported_claim_rate = (
        (total_unsupported_claims / total_claims) if total_claims > 0 else 0.0
    )

    return {
        "total_cases": total_cases,
        "average_hallucination_score": round(avg_score, 4),
        "hallucination_rate": round(hallucination_rate, 4),
        "unsupported_claim_rate": round(unsupported_claim_rate, 4),
        "unsupported_information_handling": round(avg_handling, 4),
        "cases_with_hallucinations": cases_with_hallucinations,
        "cases_correctly_handling_missing_information": cases_handling_missing,
        "passed_cases": passed_cases,
        "failed_cases": total_cases - passed_cases,
    }


__all__ = [
    "ClaimItem",
    "HallucinationJudgeOutput",
    "run_hallucination_judge",
    "evaluate_hallucination_case",
    "summarize_hallucination_results",
    "DEFAULT_PASS_THRESHOLD",
]
