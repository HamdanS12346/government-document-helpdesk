"""Tests for ResponseGenerator."""

from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.contracts.intent_decision import IntentDecision, IntentType
from app.contracts.normalized_input import ImageContent, NormalizedInput, PDFContent
from app.contracts.response import RetrievedContext
from app.response.generator import MAX_HISTORY_MESSAGES, ResponseGenerator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_normalized_input(query: str = "How do I get a PAN card?") -> NormalizedInput:
    return NormalizedInput(
        user_query=query,
        image_content=[],
        pdf_content=[],
        combined_text=query,
    )


def _make_intent(intent_type: IntentType) -> IntentDecision:
    return IntentDecision(
        query="test query",
        intent_type=intent_type,
        confidence_score=0.95,
    )


def _make_retrieved_context(has_relevant: bool = True) -> RetrievedContext:
    return RetrievedContext(
        formatted_context="Document 1\n---\nPAN card details here.",
        sources=[],
        total_documents_retrieved=1,
        documents_used=1,
        has_relevant_documents=has_relevant,
        truncated=False,
        fallback_applied=not has_relevant,
    )


def _make_generator(response_text: str = "Here is what you need to do.") -> ResponseGenerator:
    """Create a ResponseGenerator with a mock LLM."""
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = AIMessage(content=response_text)
    return ResponseGenerator(llm=mock_llm)


# ---------------------------------------------------------------------------
# Core generation tests
# ---------------------------------------------------------------------------

class TestResponseGeneratorDocumentInfo:

    def test_returns_ai_message(self):
        gen = _make_generator()
        result = gen.generate(
            normalized_input=_make_normalized_input(),
            intent_decision=_make_intent(IntentType.DOCUMENT_INFO),
            retrieved_context=_make_retrieved_context(has_relevant=True),
            messages=[],
            conversation_summary=None,
        )
        assert isinstance(result, AIMessage)

    def test_response_content_is_string(self):
        gen = _make_generator("For a PAN card, visit the NSDL portal.")
        result = gen.generate(
            normalized_input=_make_normalized_input(),
            intent_decision=_make_intent(IntentType.DOCUMENT_INFO),
            retrieved_context=_make_retrieved_context(has_relevant=True),
            messages=[],
            conversation_summary=None,
        )
        assert isinstance(result.content, str)
        assert len(result.content) > 0

    def test_llm_is_called_once(self):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = AIMessage(content="response")
        gen = ResponseGenerator(llm=mock_llm)

        gen.generate(
            normalized_input=_make_normalized_input(),
            intent_decision=_make_intent(IntentType.DOCUMENT_INFO),
            retrieved_context=_make_retrieved_context(),
            messages=[],
            conversation_summary=None,
        )
        mock_llm.invoke.assert_called_once()

    def test_no_retrieved_context_uses_fallback_prompt(self):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = AIMessage(content="fallback response")
        gen = ResponseGenerator(llm=mock_llm)

        gen.generate(
            normalized_input=_make_normalized_input(),
            intent_decision=_make_intent(IntentType.DOCUMENT_INFO),
            retrieved_context=_make_retrieved_context(has_relevant=False),
            messages=[],
            conversation_summary=None,
        )
        call_args = mock_llm.invoke.call_args[0][0]
        system_content = call_args[0].content
        # Fallback prompt tells bot no relevant documents were found
        assert "No relevant documents" in system_content

    def test_retrieved_context_text_in_prompt(self):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = AIMessage(content="ok")
        gen = ResponseGenerator(llm=mock_llm)

        context = _make_retrieved_context(has_relevant=True)
        gen.generate(
            normalized_input=_make_normalized_input(),
            intent_decision=_make_intent(IntentType.DOCUMENT_INFO),
            retrieved_context=context,
            messages=[],
            conversation_summary=None,
        )
        call_args = mock_llm.invoke.call_args[0][0]
        system_content = call_args[0].content
        assert context.formatted_context in system_content

    def test_uploaded_this_document_instruction_is_available_with_context(self):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = AIMessage(content="Use the official source listed in Document 1.")
        gen = ResponseGenerator(llm=mock_llm)
        normalized_input = NormalizedInput(
            user_query="how do i get this document?",
            image_content=[],
            pdf_content=[],
            combined_text=(
                "<USER_QUERY>\nhow do i get this document?\n\n"
                "<PDF_CONTENT>\nFilename: Passports_Amendment_Rules_2026_Schedule_IV_OCR.pdf\n"
                "Preview: Passports Amendment Rules 2026 Schedule IV"
            ),
        )

        gen.generate(
            normalized_input=normalized_input,
            intent_decision=_make_intent(IntentType.DOCUMENT_INFO),
            retrieved_context=_make_retrieved_context(has_relevant=True),
            messages=[],
            conversation_summary=None,
        )

        call_args = mock_llm.invoke.call_args[0][0]
        system_content = call_args[0].content
        assert "answer from it instead of asking a clarification question" in system_content
        assert "uploaded file name/content as the document they mean" in system_content


class TestResponseGeneratorGeneralChat:

    def test_general_chat_returns_ai_message(self):
        gen = _make_generator()
        result = gen.generate(
            normalized_input=_make_normalized_input("Hello, what can you help me with?"),
            intent_decision=_make_intent(IntentType.GENERAL_CHAT),
            retrieved_context=None,
            messages=[],
            conversation_summary=None,
        )
        assert isinstance(result, AIMessage)

    def test_general_chat_with_no_retrieved_context(self):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = AIMessage(content="Welcome!")
        gen = ResponseGenerator(llm=mock_llm)

        gen.generate(
            normalized_input=_make_normalized_input("Hello"),
            intent_decision=_make_intent(IntentType.GENERAL_CHAT),
            retrieved_context=None,
            messages=[],
            conversation_summary=None,
        )
        mock_llm.invoke.assert_called_once()


class TestConversationHistory:

    def test_conversation_history_included_in_llm_call(self):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = AIMessage(content="answer")
        gen = ResponseGenerator(llm=mock_llm)

        history = [HumanMessage(content="What is Aadhaar?")]
        gen.generate(
            normalized_input=_make_normalized_input("Tell me more."),
            intent_decision=_make_intent(IntentType.GENERAL_CHAT),
            retrieved_context=None,
            messages=history,
            conversation_summary=None,
        )
        call_args = mock_llm.invoke.call_args[0][0]
        # SystemMessage + HumanMessage(history) + HumanMessage(current)
        assert len(call_args) == 3

    def test_history_trimmed_to_max_messages(self):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = AIMessage(content="answer")
        gen = ResponseGenerator(llm=mock_llm)

        # Create more history than MAX_HISTORY_MESSAGES
        long_history = [
            HumanMessage(content=f"turn {i}") for i in range(MAX_HISTORY_MESSAGES + 4)
        ]
        gen.generate(
            normalized_input=_make_normalized_input("Latest question"),
            intent_decision=_make_intent(IntentType.GENERAL_CHAT),
            retrieved_context=None,
            messages=long_history,
            conversation_summary=None,
        )
        call_args = mock_llm.invoke.call_args[0][0]
        # SystemMessage + MAX_HISTORY_MESSAGES history msgs + current HumanMessage
        assert len(call_args) == MAX_HISTORY_MESSAGES + 2

    def test_conversation_summary_injected_into_system_prompt(self):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = AIMessage(content="answer")
        gen = ResponseGenerator(llm=mock_llm)

        summary = "User previously asked about passport renewal."
        gen.generate(
            normalized_input=_make_normalized_input("Follow-up question"),
            intent_decision=_make_intent(IntentType.GENERAL_CHAT),
            retrieved_context=None,
            messages=[],
            conversation_summary=summary,
        )
        call_args = mock_llm.invoke.call_args[0][0]
        system_content = call_args[0].content
        assert summary in system_content

    def test_no_summary_does_not_inject_context_block(self):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = AIMessage(content="answer")
        gen = ResponseGenerator(llm=mock_llm)

        gen.generate(
            normalized_input=_make_normalized_input("Question"),
            intent_decision=_make_intent(IntentType.GENERAL_CHAT),
            retrieved_context=None,
            messages=[],
            conversation_summary=None,
        )
        call_args = mock_llm.invoke.call_args[0][0]
        system_content = call_args[0].content
        assert "Previous conversation context" not in system_content


class TestEmptyQueryFallback:

    def test_empty_query_falls_back_to_combined_text(self):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = AIMessage(content="answer")
        gen = ResponseGenerator(llm=mock_llm)

        combined = "Extracted text from uploaded PDF"
        ni = NormalizedInput(
            user_query="",  # empty — citizen sent only a file
            image_content=[],
            pdf_content=[],
            combined_text=combined,
        )
        gen.generate(
            normalized_input=ni,
            intent_decision=_make_intent(IntentType.DOCUMENT_INFO),
            retrieved_context=_make_retrieved_context(),
            messages=[],
            conversation_summary=None,
        )
        call_args = mock_llm.invoke.call_args[0][0]
        # Last message is the HumanMessage with the query
        human_msg = call_args[-1]
        assert human_msg.content == combined

    def test_non_empty_query_with_uploaded_image_uses_combined_text(self):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = AIMessage(content="answer")
        gen = ResponseGenerator(llm=mock_llm)

        combined = (
            "<USER_QUERY>\nwhats this document\n\n"
            "<IMAGE_CONTENT>\nFilename: income_pan.png\nPreview: PAN application OCR text"
        )
        ni = NormalizedInput(
            user_query="whats this document",
            image_content=[
                ImageContent(
                    image_name="income_pan.png",
                    extracted_text="PAN application OCR text",
                    preview="PAN application OCR text",
                )
            ],
            pdf_content=[],
            combined_text=combined,
        )

        gen.generate(
            normalized_input=ni,
            intent_decision=_make_intent(IntentType.DOCUMENT_INFO),
            retrieved_context=_make_retrieved_context(),
            messages=[],
            conversation_summary=None,
        )

        call_args = mock_llm.invoke.call_args[0][0]
        human_msg = call_args[-1]
        assert human_msg.content == combined

    def test_non_empty_query_with_uploaded_pdf_uses_combined_text(self):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = AIMessage(content="answer")
        gen = ResponseGenerator(llm=mock_llm)

        combined = (
            "<USER_QUERY>\nwhats this document\n\n"
            "<PDF_CONTENT>\nFilename: income_pan.pdf\nPreview: PAN application PDF text"
        )
        ni = NormalizedInput(
            user_query="whats this document",
            image_content=[],
            pdf_content=[
                PDFContent(
                    pdf_name="income_pan.pdf",
                    extracted_text="PAN application PDF text",
                    preview="PAN application PDF text",
                )
            ],
            combined_text=combined,
        )

        gen.generate(
            normalized_input=ni,
            intent_decision=_make_intent(IntentType.DOCUMENT_INFO),
            retrieved_context=_make_retrieved_context(),
            messages=[],
            conversation_summary=None,
        )

        call_args = mock_llm.invoke.call_args[0][0]
        human_msg = call_args[-1]
        assert human_msg.content == combined

    def test_non_empty_query_without_attachments_still_uses_user_query(self):
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = AIMessage(content="answer")
        gen = ResponseGenerator(llm=mock_llm)

        ni = NormalizedInput(
            user_query="How do I get a PAN card?",
            image_content=[],
            pdf_content=[],
            combined_text="<USER_QUERY>\nHow do I get a PAN card?",
        )

        gen.generate(
            normalized_input=ni,
            intent_decision=_make_intent(IntentType.DOCUMENT_INFO),
            retrieved_context=_make_retrieved_context(),
            messages=[],
            conversation_summary=None,
        )

        call_args = mock_llm.invoke.call_args[0][0]
        human_msg = call_args[-1]
        assert human_msg.content == "How do I get a PAN card?"
