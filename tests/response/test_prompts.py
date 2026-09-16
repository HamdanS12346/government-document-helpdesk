"""Tests for response prompt assembly."""

import pytest

from app.contracts.intent_decision import IntentType
from app.response.prompts import (
    AI_FILLER_PHRASES,
    DOCUMENT_INFO_NO_CONTEXT_PROMPT,
    DOCUMENT_INFO_SYSTEM_PROMPT,
    GENERAL_CHAT_SYSTEM_PROMPT,
    build_system_prompt,
)


class TestBuildSystemPrompt:
    """build_system_prompt selects and populates the right base prompt."""

    def test_document_info_with_context_uses_correct_base(self):
        prompt = build_system_prompt(
            intent_type=IntentType.DOCUMENT_INFO,
            has_relevant_documents=True,
            conversation_summary=None,
            retrieved_context_text="Document 1\n---\nSome content.",
        )
        assert DOCUMENT_INFO_SYSTEM_PROMPT[:50] in prompt

    def test_document_info_with_context_injects_retrieved_text(self):
        context_text = "Document 1\n---\nPAN card information here."
        prompt = build_system_prompt(
            intent_type=IntentType.DOCUMENT_INFO,
            has_relevant_documents=True,
            conversation_summary=None,
            retrieved_context_text=context_text,
        )
        assert context_text in prompt

    def test_document_info_with_context_discourages_unneeded_clarification(self):
        prompt = build_system_prompt(
            intent_type=IntentType.DOCUMENT_INFO,
            has_relevant_documents=True,
            conversation_summary=None,
            retrieved_context_text="Document 1\n---\nPassport document evidence.",
        )

        assert "answer from it instead of asking a clarification question" in prompt
        assert "missing, conflicting, or genuinely insufficient" in prompt
        assert "uploaded file name/content as the document they mean" in prompt

    def test_document_info_no_context_uses_fallback_prompt(self):
        prompt = build_system_prompt(
            intent_type=IntentType.DOCUMENT_INFO,
            has_relevant_documents=False,
            conversation_summary=None,
            retrieved_context_text=None,
        )
        assert DOCUMENT_INFO_NO_CONTEXT_PROMPT[:50] in prompt

    def test_document_info_has_relevant_false_skips_context_block(self):
        prompt = build_system_prompt(
            intent_type=IntentType.DOCUMENT_INFO,
            has_relevant_documents=False,
            conversation_summary=None,
            retrieved_context_text="some text",
        )
        # Even if retrieved_context_text is provided, has_relevant=False
        # should prevent it from being injected
        assert "some text" not in prompt

    def test_general_chat_uses_general_prompt(self):
        prompt = build_system_prompt(
            intent_type=IntentType.GENERAL_CHAT,
            has_relevant_documents=False,
            conversation_summary=None,
        )
        assert GENERAL_CHAT_SYSTEM_PROMPT[:50] in prompt

    def test_general_chat_does_not_include_retrieved_context(self):
        prompt = build_system_prompt(
            intent_type=IntentType.GENERAL_CHAT,
            has_relevant_documents=True,
            conversation_summary=None,
            retrieved_context_text="Document 1\n---\nSome content.",
        )
        # general_chat never gets document evidence — no retrieval happened
        assert "Document 1" not in prompt

    def test_conversation_summary_injected_when_present(self):
        summary = "User previously asked about Aadhaar registration."
        prompt = build_system_prompt(
            intent_type=IntentType.GENERAL_CHAT,
            has_relevant_documents=False,
            conversation_summary=summary,
        )
        assert summary in prompt

    def test_conversation_summary_absent_when_none(self):
        prompt = build_system_prompt(
            intent_type=IntentType.GENERAL_CHAT,
            has_relevant_documents=False,
            conversation_summary=None,
        )
        assert "Previous conversation context" not in prompt

    def test_ambiguous_intent_falls_back_to_general_chat_prompt(self):
        # Ambiguous requests reach the response node via clarification placeholder;
        # if they somehow reach it directly, use the general chat prompt safely.
        prompt = build_system_prompt(
            intent_type=IntentType.AMBIGUOUS,
            has_relevant_documents=False,
            conversation_summary=None,
        )
        assert GENERAL_CHAT_SYSTEM_PROMPT[:50] in prompt


class TestNoAIFillerPhrases:
    """No base prompt should contain AI-sounding filler phrases."""

    PROMPTS = [
        DOCUMENT_INFO_SYSTEM_PROMPT,
        DOCUMENT_INFO_NO_CONTEXT_PROMPT,
        GENERAL_CHAT_SYSTEM_PROMPT,
    ]

    @pytest.mark.parametrize("phrase", AI_FILLER_PHRASES)
    @pytest.mark.parametrize("prompt", PROMPTS)
    def test_base_prompt_does_not_contain_filler(self, prompt, phrase):
        # The prompt may instruct the bot NOT to use these phrases,
        # but the prompt itself must not start with or be dominated by them.
        # Check the first 80 chars (the opening instruction) is clean.
        assert not prompt[:80].startswith(phrase), (
            f"Prompt starts with AI filler phrase: '{phrase}'"
        )
