"""LangGraph node orchestration for clarification."""

import logging
import re
from typing import Any

from langchain_core.messages import AIMessage

from app.clarification.generator import (
    ClarificationGenerator,
    OpenAIClarificationGenerator,
)
from app.clarification.schemas import ClarificationInput, ClarificationResult
from app.contracts.intent_decision import IntentDecision, IntentType
from app.graph.state import State
from app.observability import start_observation
from app.observability.metadata import (
    build_clarification_input_metadata,
    build_clarification_output_metadata,
)


MAX_CLARIFICATION_ROUNDS = 3
logger = logging.getLogger(__name__)

_REPETITIVE_QUESTION_FALLBACK = (
    "I want to make sure I get you the right information. "
    "Could you please specify which government department, document, or scheme you are referring to?"
)


def _safe_round_count(raw_count: Any) -> int:
    """Safely parse clarification_round_count against non-int/negative/corrupt inputs."""
    if raw_count is None:
        return 0
    try:
        val = int(raw_count)
        return max(0, val)
    except (ValueError, TypeError):
        return 0


def _normalize_for_repetition(text: str) -> str:
    cleaned = re.sub(r"[^\w\s]", "", text.lower())
    return " ".join(cleaned.split())


def _extract_recent_assistant_questions(messages: list[Any]) -> list[str]:
    recent: list[str] = []
    if not messages:
        return recent
    for msg in messages:
        content = ""
        is_assistant = False
        if isinstance(msg, AIMessage):
            is_assistant = True
            content = str(msg.content)
        elif hasattr(msg, "content"):
            content = str(msg.content)
            role = getattr(msg, "type", None) or getattr(msg, "role", None)
            if role in ("ai", "assistant"):
                is_assistant = True
        elif isinstance(msg, dict):
            content = str(msg.get("content", ""))
            role = str(msg.get("role", "")).lower()
            if role in ("ai", "assistant"):
                is_assistant = True

        if is_assistant and content.strip():
            recent.append(content)
    return recent


def _is_repetitive_question(candidate: str, recent_questions: list[str]) -> bool:
    norm_candidate = _normalize_for_repetition(candidate)
    if not norm_candidate:
        return False

    candidate_tokens = set(norm_candidate.split())

    for prev in recent_questions:
        norm_prev = _normalize_for_repetition(prev)
        if not norm_prev:
            continue
        if norm_candidate == norm_prev:
            return True

        # Check Jaccard similarity for near-identical questions
        prev_tokens = set(norm_prev.split())
        if candidate_tokens and prev_tokens:
            intersection = candidate_tokens.intersection(prev_tokens)
            union = candidate_tokens.union(prev_tokens)
            if len(intersection) / len(union) >= 0.85:
                return True

    return False


def ask_for_clarification(
    state: State,
    generator: ClarificationGenerator,
) -> dict[str, Any]:
    """Generate one clarification question and return its state update."""

    raw_decision = state.get("intent_decision")
    if raw_decision is None:
        raise ValueError("intent_decision is required for clarification")

    decision = IntentDecision.model_validate(raw_decision)
    if decision.intent_type != IntentType.AMBIGUOUS:
        raise ValueError("clarification requires ambiguous intent")

    previous_round_count = _safe_round_count(state.get("clarification_round_count"))
    input_data = ClarificationInput(
        intent_type=decision.intent_type,
        classification_query=decision.query,
        messages=state.get("messages", []),
        conversation_summary=state.get("conversation_summary"),
        clarification_round_count=previous_round_count,
    )

    with start_observation(
        "clarification",
        input=build_clarification_input_metadata(
            decision,
            messages=input_data.messages,
            conversation_summary=input_data.conversation_summary,
            clarification_round_count=input_data.clarification_round_count,
            max_clarification_rounds=MAX_CLARIFICATION_ROUNDS,
        ),
    ) as observation:
        result = ClarificationResult.model_validate(generator.generate(input_data))
        question_text = result.question

        recent_questions = _extract_recent_assistant_questions(input_data.messages)
        if _is_repetitive_question(question_text, recent_questions):
            logger.warning(
                "ClarificationNode: generated repetitive question '%s', replacing with fallback.",
                question_text,
            )
            question_text = _REPETITIVE_QUESTION_FALLBACK

        message = AIMessage(content=question_text)
        _safe_update_observation(
            observation,
            output=build_clarification_output_metadata(
                clarification_required=True,
                reason_code=str(result.reason_code),
                missing_dimensions=result.missing_dimensions,
                question=question_text,
            ),
        )

    return {
        "messages": [message],
        "clarification_round_count": previous_round_count + 1,
    }


_default_generator: ClarificationGenerator | None = None


def get_default_clarification_generator() -> ClarificationGenerator:
    """Return the default clarification generator for graph wiring."""

    global _default_generator
    if _default_generator is None:
        _default_generator = OpenAIClarificationGenerator()
    return _default_generator


def set_default_clarification_generator(generator: ClarificationGenerator) -> None:
    """Override the default clarification generator."""

    global _default_generator
    _default_generator = generator


def clarification_node(state: State) -> dict[str, Any]:
    """LangGraph node function for clarification."""

    return ask_for_clarification(state, get_default_clarification_generator())


def _safe_update_observation(observation: Any, **kwargs: Any) -> None:
    try:
        observation.update(**kwargs)
    except Exception as exc:
        logger.warning("Failed to update clarification observation: %s", exc)


__all__ = [
    "ask_for_clarification",
    "clarification_node",
    "get_default_clarification_generator",
    "MAX_CLARIFICATION_ROUNDS",
    "set_default_clarification_generator",
]
