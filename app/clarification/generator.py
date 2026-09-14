"""Interfaces and OpenAI provider for clarification generation."""

from typing import Any, Protocol

from app.clarification.prompts import (
    CLARIFICATION_SYSTEM_PROMPT,
    build_clarification_prompt_input,
)
from app.clarification.schemas import ClarificationInput, ClarificationResult


DEFAULT_MODEL = "gpt-4o-mini"


class ClarificationGenerator(Protocol):
    """Provider interface used by the Clarification Node."""

    def generate(self, input_data: ClarificationInput) -> ClarificationResult:
        """Generate a validated clarification result."""


class OpenAIClarificationGenerator:
    """Generate clarification questions with an OpenAI chat model."""

    def __init__(self, model: str = DEFAULT_MODEL, llm: Any | None = None):
        if llm is None:
            from langchain_openai import ChatOpenAI

            llm = ChatOpenAI(model=model, temperature=0)
        self._structured_llm = llm.with_structured_output(ClarificationResult)

    def generate(self, input_data: ClarificationInput) -> ClarificationResult:
        """Return a validated clarification result for the supplied input."""

        prompt_input = build_clarification_prompt_input(input_data)
        result = self._structured_llm.invoke(
            [
                ("system", CLARIFICATION_SYSTEM_PROMPT),
                ("human", prompt_input),
            ]
        )

        try:
            return ClarificationResult.model_validate(result)
        except Exception as exc:
            raise ValueError("generator returned an invalid clarification result") from exc


__all__ = [
    "ClarificationGenerator",
    "DEFAULT_MODEL",
    "OpenAIClarificationGenerator",
]
