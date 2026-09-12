"""Interfaces for intent classification providers."""

from typing import Protocol

from app.contracts.intent_decision import IntentDecision


class IntentClassifier(Protocol):
    """Provider interface used by the intent classifier node."""

    def classify(self, query: str) -> IntentDecision:
        """Classify a constructed query into a validated intent decision."""
