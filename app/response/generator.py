"""Response generation logic for the Government Helpdesk chatbot.

Responsibilities:
- Build the correct prompt based on intent type and available context.
- Call the LLM.
- Return the generated AIMessage.

No LangGraph dependency. Fully testable in isolation via LLM injection.
"""

import logging
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.contracts.intent_decision import IntentDecision
from app.contracts.normalized_input import NormalizedInput
from app.contracts.response import RetrievedContext
from app.response.prompts import build_system_prompt

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-4o-mini"

# Maximum number of historical messages to include in the LLM call.
# Prevents context window overflow. Once the memory module is built this
# can be driven by settings instead.
MAX_HISTORY_MESSAGES = 6


class ResponseGenerator:
    """Generate the citizen-facing assistant reply using an LLM.

    Accepts an injected LLM instance for testing — same pattern as
    OpenAIIntentClassifier.
    """

    def __init__(self, model: str = DEFAULT_MODEL, llm: Any | None = None) -> None:
        if llm is None:
            from langchain_openai import ChatOpenAI

            llm = ChatOpenAI(model=model, temperature=0.3)
        self._llm = llm

    def generate(
        self,
        normalized_input: NormalizedInput,
        intent_decision: IntentDecision,
        retrieved_context: RetrievedContext | None,
        messages: list[BaseMessage],
        conversation_summary: str | None,
    ) -> AIMessage:
        """Build the prompt and call the LLM.

        Args:
            normalized_input:    Validated user query and attachment content.
            intent_decision:     Validated intent classification result.
            retrieved_context:   Context from Context Builder (None on general_chat path).
            messages:            Recent conversation history (empty on first turn).
            conversation_summary: Compact prior context (None until memory module is built).

        Returns:
            AIMessage containing the generated response text.

        Raises:
            ValueError: If normalized_input or intent_decision are missing.
        """
        has_relevant = (
            retrieved_context is not None
            and retrieved_context.has_relevant_documents
        )
        retrieved_text: str | None = (
            retrieved_context.formatted_context
            if retrieved_context and has_relevant
            else None
        )

        system_prompt = build_system_prompt(
            intent_type=intent_decision.intent_type,
            has_relevant_documents=has_relevant,
            conversation_summary=conversation_summary,
            retrieved_context_text=retrieved_text,
        )

        # Build the message list:
        # [SystemMessage] + [recent history] + [current HumanMessage]
        llm_messages: list[BaseMessage] = [SystemMessage(content=system_prompt)]

        if messages:
            llm_messages.extend(messages[-MAX_HISTORY_MESSAGES:])

        # Prefer user_query; fall back to combined_text when the query is empty
        # but the citizen sent attachments (the attachment text is in combined_text).
        query_text = normalized_input.user_query.strip() or normalized_input.combined_text
        llm_messages.append(HumanMessage(content=query_text))

        logger.debug(
            "ResponseGenerator.generate: intent=%s, has_relevant=%s, "
            "history=%d, prompt_messages=%d",
            intent_decision.intent_type,
            has_relevant,
            len(messages),
            len(llm_messages),
        )

        result = self._llm.invoke(llm_messages)

        # Normalise — some LLM wrappers return a BaseMessage subclass directly,
        # others return a raw string.
        if isinstance(result, AIMessage):
            return result
        content = result.content if hasattr(result, "content") else str(result)
        return AIMessage(content=content)


__all__ = ["DEFAULT_MODEL", "MAX_HISTORY_MESSAGES", "ResponseGenerator"]
