"""LangGraph node adapter for response guardrails.

Sits between RESPONSE_NODE and END in build_full_graph.
Reads the last AIMessage from state["messages"], runs all four response
guardrails via run_response_guardrails(), and writes back the cleaned
message only when a guardrail triggered.

Returns an empty dict when nothing triggers — no state changes on clean responses.
"""

from __future__ import annotations

import logging
from typing import Any

from guardrails.response import run_response_guardrails
from app.observability import start_observation

logger = logging.getLogger(__name__)


def response_guardrail_node(state: dict[str, Any]) -> dict[str, Any]:
    """Run output guardrails on the most recent AIMessage in state.

    Reads:
        state["messages"]          — list of LangChain BaseMessage objects.
        state["retrieved_context"] — RetrievedContext | None.
        state["intent_decision"]   — IntentDecision | None.

    Writes (only when a guardrail triggers):
        state["messages"]          — last message replaced with cleaned version.
        state["guardrail_flags"]   — dict of per-guardrail decisions for observability.

    Returns:
        Empty dict if nothing triggered (no state mutation).
        Partial state update dict if any guardrail was triggered.
    """
    messages = list(state.get("messages") or [])
    if not messages:
        return {}

    last_message = messages[-1]
    response_text = str(getattr(last_message, "content", ""))
    if not response_text:
        return {}

    retrieved_context = state.get("retrieved_context")
    intent_type = str(
        getattr(state.get("intent_decision"), "intent_type", "general_chat")
    )

    with start_observation(
        "response_guardrail",
        input={
            "response_length": len(response_text),
            "intent_type": intent_type,
            "has_retrieved_context": retrieved_context is not None,
        },
    ) as observation:
        report = run_response_guardrails(
            response_text=response_text,
            retrieved_context=retrieved_context,
            intent_type=intent_type,
        )

        guardrail_flags = {
            "citation_decision": report.citation_result.decision,
            "hallucination_decision": (
                report.hallucination_result.decision
                if report.hallucination_result
                else "allow"
            ),
            "pii_redaction_count": report.pii_result.redaction_count,
            "length_decision": report.length_result.decision,
            "scope_decision": report.scope_result.decision,
            "any_triggered": report.any_triggered,
        }

        observation.update(
            output={
                **guardrail_flags,
                "final_length": len(report.final_text),
            }
        )

    if not report.any_triggered:
        return {}

    # Replace only the last message — leave the rest of the message history intact.
    try:
        cleaned_message = last_message.model_copy(
            update={"content": report.final_text}
        )
    except AttributeError:
        # Fallback for non-Pydantic message objects (should not occur in production).
        logger.warning(
            "response_guardrail_node: last message does not support model_copy — "
            "skipping message replacement."
        )
        return {"guardrail_flags": guardrail_flags}

    return {
        "messages": messages[:-1] + [cleaned_message],
        "guardrail_flags": guardrail_flags,
    }


__all__ = ["response_guardrail_node"]
