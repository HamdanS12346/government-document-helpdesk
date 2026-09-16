"""LangGraph node orchestration for clarification."""

import logging
from typing import Any

from langchain_community.callbacks import get_openai_callback
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

    previous_round_count = int(state.get("clarification_round_count", 0) or 0)
    input_data = ClarificationInput(
        intent_type=decision.intent_type,
        classification_query=decision.query,
        messages=state.get("messages", []),
        conversation_summary=state.get("conversation_summary"),
        clarification_round_count=previous_round_count,
    )

    with start_observation(
        "clarification",
        as_type="generation",
        model="gpt-4o-mini",
        input=build_clarification_input_metadata(
            decision,
            messages=input_data.messages,
            conversation_summary=input_data.conversation_summary,
            clarification_round_count=input_data.clarification_round_count,
            max_clarification_rounds=MAX_CLARIFICATION_ROUNDS,
        ),
    ) as observation:
        with get_openai_callback() as cb:
            raw_gen = generator.generate(input_data)
        result = ClarificationResult.model_validate(raw_gen)
        message = AIMessage(content=result.question)
        output_data = build_clarification_output_metadata(
            clarification_required=True,
            reason_code=str(result.reason_code),
            missing_dimensions=result.missing_dimensions,
            question=result.question,
        )
        if cb.total_tokens > 0:
            output_data["token_usage"] = {
                "input_tokens": cb.prompt_tokens,
                "output_tokens": cb.completion_tokens,
                "total_tokens": cb.total_tokens,
            }
        _safe_update_observation(
            observation,
            output=output_data,
            usage_details={
                "input": cb.prompt_tokens,
                "output": cb.completion_tokens,
                "total": cb.total_tokens,
            },
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
