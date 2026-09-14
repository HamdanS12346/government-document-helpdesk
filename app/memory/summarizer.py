"""Conversation summarizer for rolling memory compression."""

import logging
import os
from typing import List, Optional
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from app.memory.window_manager import ConversationWindowManager

logger = logging.getLogger(__name__)

SUMMARIZER_SYSTEM_PROMPT = """You are a precise conversation summarizer for an official government document helpdesk.
Your task is to produce an updated, factual, and compact summary of the conversation history.

Rules:
1. Preserve all government document names, schemes, rules, form numbers, required proofs, and citizen eligibility details.
2. Incorporate the new dialogue turns seamlessly into the existing summary.
3. Keep the summary concise, factual, and neutral (under 250 words).
4. Do NOT include conversational filler, greetings, or apologies.
5. Output ONLY the updated summary text.
"""


class ConversationSummarizer:
    """Incrementally summarizes evicted conversation turns using an LLM."""

    def __init__(self, llm: Optional[BaseChatModel] = None):
        self._llm = llm

    def _get_llm(self) -> BaseChatModel:
        if self._llm is None:
            self._llm = ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0.0,
                api_key=os.getenv("OPENAI_API_KEY"),
            )
        return self._llm

    def summarize(
        self,
        messages_to_summarize: List[BaseMessage],
        existing_summary: Optional[str] = None,
    ) -> str:
        """Summarize newly evicted dialogue turns and merge with existing summary."""
        if not messages_to_summarize:
            return (existing_summary or "").strip()

        rendered_dialogue = ConversationWindowManager.render_messages(messages_to_summarize)
        existing_summary_clean = (existing_summary or "").strip()

        prompt_parts = []
        if existing_summary_clean:
            prompt_parts.append(f"### EXISTING SUMMARY:\n{existing_summary_clean}")
        prompt_parts.append(f"### NEW CONVERSATION TURNS TO INCORPORATE:\n{rendered_dialogue}")
        prompt_parts.append("Generate an updated consolidated summary incorporating the above turns.")

        user_prompt = "\n\n".join(prompt_parts)

        try:
            llm = self._get_llm()
            messages = [
                SystemMessage(content=SUMMARIZER_SYSTEM_PROMPT),
                HumanMessage(content=user_prompt),
            ]
            response = llm.invoke(messages)
            content = response.content if hasattr(response, "content") else str(response)
            return str(content).strip()
        except Exception as exc:
            logger.warning("Summarization LLM call failed: %s; using fallback.", exc)
            fallback_note = f" [Previous topics: {len(messages_to_summarize)} turns]"
            return (existing_summary_clean + fallback_note).strip()


__all__ = ["ConversationSummarizer", "SUMMARIZER_SYSTEM_PROMPT"]
