"""Tests for clarification generator providers."""

import pytest

from app.clarification.generator import OpenAIClarificationGenerator
from app.clarification.prompts import CLARIFICATION_SYSTEM_PROMPT
from app.clarification.schemas import ClarificationInput
from app.contracts.intent_decision import IntentType


class FakeStructuredLLM:
    def __init__(self, result):
        self.result = result
        self.messages = None
        self.schema = None

    def with_structured_output(self, schema):
        self.schema = schema
        return self

    def invoke(self, messages):
        self.messages = messages
        return self.result


def test_openai_generator_validates_structured_provider_output() -> None:
    llm = FakeStructuredLLM(
        {
            "question": "Which state are you applying in?",
            "reason_code": "missing_location",
            "missing_dimensions": ["location"],
        }
    )
    generator = OpenAIClarificationGenerator(llm=llm)
    input_data = ClarificationInput(
        intent_type=IntentType.AMBIGUOUS,
        classification_query="Help me apply for a certificate",
    )

    result = generator.generate(input_data)

    assert result.question == "Which state are you applying in?"
    assert result.reason_code == "missing_location"
    assert llm.messages[0] == ("system", CLARIFICATION_SYSTEM_PROMPT)
    assert "Classifier Query:\nHelp me apply" in llm.messages[1][1]


def test_openai_generator_rejects_invalid_provider_output() -> None:
    generator = OpenAIClarificationGenerator(
        llm=FakeStructuredLLM(
            {
                "question": "",
                "reason_code": "unsupported",
                "missing_dimensions": [],
            }
        )
    )
    input_data = ClarificationInput(
        intent_type=IntentType.AMBIGUOUS,
        classification_query="Need help",
    )

    with pytest.raises(ValueError, match="invalid clarification result"):
        generator.generate(input_data)
