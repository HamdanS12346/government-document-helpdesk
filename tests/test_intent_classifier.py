from pydantic import ValidationError
import pytest

from app.contracts.intent_decision import IntentDecision
from app.contracts.normalized_input import ImageContent, NormalizedInput, PDFContent
from app.intent.classifier import OpenAIIntentClassifier
from app.intent.node import classify_intent
from app.intent.query_builder import build_classification_query


class FakeClassifier:
    def __init__(self, decision: IntentDecision):
        self.decision = decision
        self.query = None

    def classify(self, query: str) -> IntentDecision:
        self.query = query
        return self.decision


class FakeStructuredLLM:
    def __init__(self, result):
        self.result = result
        self.messages = None

    def with_structured_output(self, _schema):
        return self

    def invoke(self, messages):
        self.messages = messages
        return self.result


def test_intent_decision_validates_supported_values_and_confidence():
    decision = IntentDecision(
        query="Hello",
        intent_type="general_chat",
        confidence_score=0.8,
    )

    assert decision.intent_type == "general_chat"

    with pytest.raises(ValidationError):
        IntentDecision(query="Hello", intent_type="unsupported", confidence_score=0.8)
    with pytest.raises(ValidationError):
        IntentDecision(query="Hello", intent_type="general_chat", confidence_score=1.1)


def test_openai_classifier_validates_structured_provider_output():
    llm = FakeStructuredLLM(
        {
            "query": "classification input",
            "intent_type": "document_info",
            "confidence_score": 0.91,
        }
    )
    classifier = OpenAIIntentClassifier(llm=llm)

    decision = classifier.classify("classification input")

    assert decision.intent_type == "document_info"
    assert decision.confidence_score == 0.91
    assert llm.messages[1] == ("human", "classification input")


def test_openai_classifier_rejects_invalid_provider_output():
    classifier = OpenAIIntentClassifier(
        llm=FakeStructuredLLM(
            {
                "query": "classification input",
                "intent_type": "unsupported",
                "confidence_score": 0.5,
            }
        )
    )

    with pytest.raises(ValueError, match="invalid intent decision"):
        classifier.classify("classification input")


def test_openai_classifier_rejects_blank_query():
    classifier = OpenAIIntentClassifier(llm=FakeStructuredLLM({}))

    with pytest.raises(ValueError, match="query must not be empty"):
        classifier.classify("  ")


def test_query_builder_uses_input_previews_and_conversation_context():
    normalized_input = NormalizedInput(
        user_query="Can I use this document?",
        image_content=[
            ImageContent(
                image_name="identity-card.jpg",
                extracted_text="Identity card text",
                preview="identity card preview",
            )
        ],
        pdf_content=[
            PDFContent(
                pdf_name="requirements.pdf",
                extracted_text="Application requirements text",
                preview="application requirements preview",
            )
        ],
        combined_text="The user is applying for a passport.",
    )
    messages = [{"role": "human", "content": f"turn {index}"} for index in range(12)]

    query = build_classification_query(
        normalized_input,
        messages=messages,
        conversation_summary="Earlier discussion about passport eligibility.",
    )

    assert "Can I use this document?" in query
    assert "identity card preview" in query
    assert "application requirements preview" in query
    assert "The user is applying for a passport." not in query
    assert "human: turn 2" in query
    assert "human: turn 11" in query
    assert "human: turn 1\n" not in query
    assert "Earlier discussion about passport eligibility." in query


def test_query_builder_uses_attachment_previews_without_full_extracted_text():
    normalized_input = NormalizedInput(
        user_query="What is the deadline?",
        image_content=[
            ImageContent(
                image_name="notice.png",
                extracted_text="private full image extraction",
                preview="deadline notice preview",
            )
        ],
        pdf_content=[
            PDFContent(
                pdf_name="form.pdf",
                extracted_text="private full PDF extraction",
                preview="form deadline preview",
            )
        ],
        combined_text=(
            "private full image extraction\nprivate full PDF extraction"
        ),
    )

    query = build_classification_query(normalized_input)

    assert "notice.png: deadline notice preview" in query
    assert "form.pdf: form deadline preview" in query
    assert "private full image extraction" not in query
    assert "private full PDF extraction" not in query


def test_node_returns_validated_decision_with_constructed_query_only():
    normalized_input = NormalizedInput(
        user_query="What documents do I need?",
        image_content=[],
        pdf_content=[],
        combined_text="",
    )
    classifier = FakeClassifier(
        IntentDecision(
            query="provider query",
            intent_type="document_info",
            confidence_score=0.95,
        )
    )

    result = classify_intent(
        {
            "normalized_input": normalized_input,
            "messages": [],
            "conversation_summary": "",
        },
        classifier,
    )

    assert list(result) == ["intent_decision"]
    assert result["intent_decision"].query == classifier.query
    assert result["intent_decision"].intent_type == "document_info"


def test_node_requires_normalized_input():
    classifier = FakeClassifier(
        IntentDecision(query="query", intent_type="ambiguous", confidence_score=0.5)
    )

    with pytest.raises(ValueError, match="normalized_input is required"):
        classify_intent({}, classifier)
