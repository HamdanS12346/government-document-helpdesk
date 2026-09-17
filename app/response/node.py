"""LangGraph node implementation for the Response Node.

STATE CONTRACT
--------------
Reads from state:
  state["normalized_input"]      — NormalizedInput  (required)
  state["intent_decision"]       — IntentDecision   (required)
  state["retrieved_context"]     — RetrievedContext (optional — present on document_info path)
  state["messages"]              — list[BaseMessage](optional — empty on first turn)
  state["conversation_summary"]  — str              (optional — None until memory module built)

Writes to state:
  state["messages"]  — appends one AIMessage containing the generated response.

DESIGN RESPONSIBILITY
---------------------
This file is intentionally thin. Its only job is to:
  1. Extract and validate the required state fields.
  2. Delegate all generation logic to ResponseGenerator (generator.py).
  3. Return the correct state update dict for LangGraph.

No prompt text, no business logic, no LLM calls live here.
"""

import logging
from typing import Any

from langchain_community.callbacks import get_openai_callback
from langchain_core.messages import BaseMessage

from app.contracts.intent_decision import IntentDecision
from app.contracts.normalized_input import NormalizedInput
from app.contracts.response import RetrievedContext
from app.observability import start_observation
from app.response.generator import ResponseGenerator

logger = logging.getLogger(__name__)

# Lazy default generator — created on first use, not at import time.
# This avoids requiring OPENAI_API_KEY just to import the module.
_default_generator: ResponseGenerator | None = None


def _get_default_generator() -> ResponseGenerator:
    global _default_generator
    if _default_generator is None:
        _default_generator = ResponseGenerator()
    return _default_generator


def response_node(
    state: dict[str, Any],
    generator: ResponseGenerator | None = None,
) -> dict[str, Any]:
    """LangGraph node: generates the final citizen-facing response.

    Reads the required state fields, delegates generation to ResponseGenerator,
    and appends the produced AIMessage to state["messages"].

    Args:
        state:     Shared LangGraph state dictionary.
        generator: Optional custom ResponseGenerator for testing. Uses the
                   module-level default if None.

    Returns:
        {"messages": <existing messages> + [AIMessage]}

    Raises:
        ValueError: If normalized_input or intent_decision are absent from state.
    """
    active_generator = generator or _get_default_generator()

    # --- Required fields ---
    normalized_input = state.get("normalized_input")
    if normalized_input is None:
        raise ValueError(
            "response_node: state['normalized_input'] is required but missing"
        )
    if not isinstance(normalized_input, NormalizedInput):
        normalized_input = NormalizedInput.model_validate(normalized_input)

    intent_decision = state.get("intent_decision")
    if intent_decision is None:
        raise ValueError(
            "response_node: state['intent_decision'] is required but missing"
        )
    if not isinstance(intent_decision, IntentDecision):
        intent_decision = IntentDecision.model_validate(intent_decision)

    # --- Optional fields ---
    raw_retrieved_context = state.get("retrieved_context")
    retrieved_context: RetrievedContext | None = None
    if raw_retrieved_context is not None:
        if isinstance(raw_retrieved_context, RetrievedContext):
            retrieved_context = raw_retrieved_context
        else:
            retrieved_context = RetrievedContext.model_validate(raw_retrieved_context)

    messages: list[BaseMessage] = list(state.get("messages") or [])
    conversation_summary: str | None = state.get("conversation_summary")

    logger.debug(
        "response_node: intent=%s, has_retrieved_context=%s, history_messages=%d",
        intent_decision.intent_type,
        retrieved_context is not None,
        len(messages),
    )

    # --- Generate the response ---
    with start_observation(
        "response",
        as_type="generation",
        model="gpt-4o-mini",
        input={
            "intent_type": str(intent_decision.intent_type),
            "has_retrieved_context": retrieved_context is not None,
            "history_message_count": len(messages),
        },
    ) as observation:
        with get_openai_callback() as cb:
            ai_message = active_generator.generate(
                normalized_input=normalized_input,
                intent_decision=intent_decision,
                retrieved_context=retrieved_context,
                messages=messages,
                conversation_summary=conversation_summary,
            )
        output_data: dict[str, Any] = {
            "response_chars": len(str(ai_message.content)),
        }
        if cb.total_tokens > 0:
            output_data["token_usage"] = {
                "input_tokens": cb.prompt_tokens,
                "output_tokens": cb.completion_tokens,
                "total_tokens": cb.total_tokens,
            }
        observation.update(
            output=output_data,
            usage_details={
                "input": cb.prompt_tokens,
                "output": cb.completion_tokens,
                "total": cb.total_tokens,
            },
        )

    logger.info(
        "response_node: complete — intent=%s, response_chars=%d",
        intent_decision.intent_type,
        len(str(ai_message.content)),
    )

    # Return messages with the new AIMessage appended.
    # NOTE: Once the memory module adds the add_messages reducer to state["messages"],
    # returning just {"messages": [ai_message]} will be sufficient. For now, we
    # explicitly preserve existing messages to avoid replacement.
    return {"messages": messages + [ai_message]}
