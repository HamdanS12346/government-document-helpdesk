"""Multi-turn conversational query rewriter for the Retriever Node."""

import logging
from typing import List, Optional
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

QUERY_REWRITER_SYSTEM_PROMPT = """You are an expert search query optimizer for a government document helpdesk.
Your task is to rewrite the user's latest query into a single, standalone search query optimized for document retrieval.

Rules:
1. Resolve all pronouns and conversational references ("this", "that document", "it", "the second one", "the scheme") using the recent conversation history or summary.
2. If the user refers to an attached file or image, incorporate key entities, form names, or topics from the attachment previews.
3. Preserve all domain terminology, form numbers (e.g. "ITR-4", "Form 49A"), tax/legal sections (e.g. "44AD", "80C"), and official department names.
4. Do NOT attempt to answer the question or add conversational chatter.
5. If the user's query is already standalone, self-contained, and clear, output it exactly as is.
6. Output ONLY the rewritten standalone query as plain text without quotation marks or explanations.
"""


class QueryRewriter:
    """Rewrites multi-turn conversational queries into standalone retrieval queries."""

    def __init__(self, llm: Optional[BaseChatModel] = None):
        self._llm = llm

    def _get_llm(self) -> BaseChatModel:
        if self._llm is None:
            self._llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0)
        return self._llm

    @staticmethod
    def _format_messages(messages: List[BaseMessage]) -> str:
        """Format message objects into readable role-prefixed turns."""
        formatted_turns = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                formatted_turns.append(f"User: {msg.content}")
            elif isinstance(msg, AIMessage):
                formatted_turns.append(f"Assistant: {msg.content}")
            elif isinstance(msg, SystemMessage):
                formatted_turns.append(f"System: {msg.content}")
            else:
                formatted_turns.append(f"{getattr(msg, 'type', 'Message')}: {msg.content}")
        return "\n".join(formatted_turns)

    def rewrite(
        self,
        user_query: str,
        messages: Optional[List[BaseMessage]] = None,
        conversation_summary: Optional[str] = None,
        attachment_previews: Optional[List[str]] = None,
    ) -> str:
        """Rewrite user_query using multi-turn conversation and attachment context.

        If no conversation history, summary, or attachments are provided (Turn 1),
        the query is returned directly to avoid unnecessary LLM latency.
        """
        user_query = user_query.strip()
        messages = messages or []
        attachment_previews = attachment_previews or []
        conversation_summary = (conversation_summary or "").strip()

        # Turn 1 bypass optimization: No history, summary, or attachment context
        if not messages and not conversation_summary and not attachment_previews:
            return user_query

        # Build context blocks
        context_parts = []

        if conversation_summary:
            context_parts.append(f"Earlier Conversation Summary:\n{conversation_summary}")

        if messages:
            formatted_dialogue = self._format_messages(messages)
            if formatted_dialogue:
                context_parts.append(f"Recent Conversation History:\n{formatted_dialogue}")

        if attachment_previews:
            previews_text = "\n".join(f"- {preview.strip()}" for preview in attachment_previews if preview.strip())
            if previews_text:
                context_parts.append(f"Attachment Previews:\n{previews_text}")

        context_parts.append(f"Current User Query:\n{user_query}")
        user_prompt_content = "\n\n".join(context_parts)

        try:
            llm = self._get_llm()
            prompt_messages = [
                SystemMessage(content=QUERY_REWRITER_SYSTEM_PROMPT),
                HumanMessage(content=user_prompt_content),
            ]
            response = llm.invoke(prompt_messages)
            rewritten = (
                response.content.strip()
                if hasattr(response, "content")
                else str(response).strip()
            )

            # Clean any wrapping quotes
            if rewritten.startswith('"') and rewritten.endswith('"'):
                rewritten = rewritten[1:-1].strip()

            return rewritten or user_query
        except Exception as exc:
            logger.warning("Query rewriter failed with error: %s; falling back to original query.", exc)
            return user_query


__all__ = ["QueryRewriter"]
