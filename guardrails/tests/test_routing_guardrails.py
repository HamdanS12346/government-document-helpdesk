"""Tests for Graph Routing & Clarification Node (Critical Bypass) Guardrails.

Covers:
  - Credential Solicitation Guardrail (blocking requests for OTP, PIN, Password, CVV, Card #)
  - Security warning / advice detection (permitting "Never share your OTP", etc.)
  - Clarification exit edge rewiring in build_full_graph (CLARIFICATION_NODE -> RESPONSE_GUARDRAIL_NODE -> END)
  - Clarification output sanitization (PII redaction and credential fallback on clarification turn)
  - Clarification repetitive question detection and fallback replacement
  - Route loop hardening (safe parsing of corrupt clarification_round_count)
"""

from __future__ import annotations

from typing import Any
import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.clarification.generator import ClarificationGenerator
from app.clarification.node import (
    MAX_CLARIFICATION_ROUNDS,
    _REPETITIVE_QUESTION_FALLBACK,
    ask_for_clarification,
    clarification_node,
)
from app.clarification.schemas import ClarificationInput, ClarificationResult
from app.contracts.intent_decision import IntentDecision, IntentType
from app.contracts.normalized_input import NormalizedInput
from app.graph.graph import (
    CLARIFICATION_NODE,
    RESPONSE_GUARDRAIL_NODE,
    RESPONSE_NODE,
    RETRIEVER_NODE,
    build_full_graph,
    invoke_full_graph,
)
from app.graph.routing import route_after_intent, route_after_intent_full
from app.input_processing.schemas import InputProcessingResult
from guardrails.response import (
    ClarificationCredentialGuardrail,
    CredentialSolicitationGuardrail,
    CredentialSolicitationResult,
    ResponseGuardrailDecision,
    run_response_guardrails,
)


# ---------------------------------------------------------------------------
# Test Helpers & Mock Classes
# ---------------------------------------------------------------------------

class FakeClassifier:
    def __init__(self, intent_type: IntentType = IntentType.AMBIGUOUS):
        self.intent_type = intent_type

    def classify(self, query: str) -> IntentDecision:
        return IntentDecision(
            intent_type=self.intent_type,
            confidence_score=0.95,
            query=query,
            reasoning="mock classification",
        )


class MockClarificationGenerator(ClarificationGenerator):
    def __init__(self, question: str = "Which document are you applying for?"):
        self.question = question
        self.called = False

    def generate(self, input_data: ClarificationInput) -> ClarificationResult:
        self.called = True
        return ClarificationResult(
            reason_code="missing_document_type",
            missing_dimensions=["document_type"],
            question=self.question,
        )


def _normalized_input(query: str = "help me with my application") -> NormalizedInput:
    return NormalizedInput(
        user_query=query,
        image_content=[],
        pdf_content=[],
        combined_text=query,
    )


def _make_input_result(text: str = "help me with my application") -> InputProcessingResult:
    return InputProcessingResult(
        success=True,
        normalized_input=_normalized_input(text),
    )


# ---------------------------------------------------------------------------
# 1. Credential Solicitation Guardrail Tests
# ---------------------------------------------------------------------------

class TestCredentialSolicitationGuardrail:
    """Verify that CredentialSolicitationGuardrail blocks credential harvesting while allowing warnings."""

    guardrail = CredentialSolicitationGuardrail()

    def test_alias_is_identical(self):
        """ClarificationCredentialGuardrail is an alias to CredentialSolicitationGuardrail."""
        assert ClarificationCredentialGuardrail is CredentialSolicitationGuardrail

    def test_clean_response_allowed(self):
        """Normal helpful citizen text passes with ALLOW."""
        result = self.guardrail.check("Please specify if you are applying for a fresh passport or renewal.")
        assert result.decision == ResponseGuardrailDecision.ALLOW
        assert result.detected_solicitations == []
        assert "fresh passport" in result.cleaned_text

    @pytest.mark.parametrize(
        "solicitation_phrase",
        [
            "Please enter your OTP to proceed with verification.",
            "Share your 6-digit one-time password received on your phone.",
            "Provide your UPI PIN to check application status.",
            "What is your ATM PIN for fee processing?",
            "Enter your net banking password to confirm identity.",
            "Please share your CVV code on the back of your card.",
            "Provide your 16-digit debit card number and PIN.",
            "Input your passcode or mPin to continue.",
        ],
    )
    def test_solicitations_detected_and_replaced(self, solicitation_phrase: str):
        """Direct requests for sensitive citizen credentials are replaced with fallback."""
        result = self.guardrail.check(solicitation_phrase)
        assert result.decision == ResponseGuardrailDecision.REPLACE_WITH_FALLBACK
        assert len(result.detected_solicitations) >= 1
        assert "never ask for your passwords, OTPs, or financial credentials" in result.cleaned_text

    @pytest.mark.parametrize(
        "security_warning",
        [
            "Never share your OTP with anyone over the phone or chat.",
            "Do not share your password or UPI PIN with unauthorized persons.",
            "The department will never ask for your ATM PIN or CVV.",
            "Caution: Beware of fraudulent calls asking you to enter your OTP.",
        ],
    )
    def test_security_warnings_allowed(self, security_warning: str):
        """Educational and scam-warning statements are NOT flagged as solicitations."""
        result = self.guardrail.check(security_warning)
        assert result.decision == ResponseGuardrailDecision.ALLOW
        assert result.cleaned_text == security_warning

    def test_mixed_warning_and_solicitation_is_blocked(self):
        """If a text contains a warning but also solicits credentials in another sentence, block it."""
        text = "Beware of fraudsters. However, please share your OTP here to verify your account."
        result = self.guardrail.check(text)
        assert result.decision == ResponseGuardrailDecision.REPLACE_WITH_FALLBACK
        assert len(result.detected_solicitations) >= 1

    def test_empty_input_allowed(self):
        """Empty or whitespace text passes safely."""
        result = self.guardrail.check("")
        assert result.decision == ResponseGuardrailDecision.ALLOW
        assert result.cleaned_text == ""

    def test_fail_closed_on_unexpected_error(self, monkeypatch):
        """Guardrail fails closed with REPLACE_WITH_FALLBACK on exception."""
        def _raise_error(*args, **kwargs):
            raise RuntimeError("Unexpected internal crash")

        monkeypatch.setattr(self.guardrail, "_check", _raise_error)
        result = self.guardrail.check("Valid text")
        assert result.decision == ResponseGuardrailDecision.REPLACE_WITH_FALLBACK
        assert "error_fail_closed" in result.detected_solicitations


# ---------------------------------------------------------------------------
# 2. Graph Wiring & Clarification Critical Bypass Tests
# ---------------------------------------------------------------------------

class TestGraphWiringAndClarificationBypass:
    """Verify build_full_graph rewiring and post-clarification guardrail execution."""

    def test_full_graph_clarification_edge_routes_to_response_guardrail(self):
        """Verify graph topology: CLARIFICATION_NODE -> RESPONSE_GUARDRAIL_NODE."""
        classifier = FakeClassifier(IntentType.AMBIGUOUS)
        graph = build_full_graph(classifier=classifier)

        # Inspect compiled graph edges
        edges = graph.get_graph().edges
        clarification_targets = [
            edge.target for edge in edges if edge.source == CLARIFICATION_NODE
        ]
        assert RESPONSE_GUARDRAIL_NODE in clarification_targets
        assert "end" not in clarification_targets

    def test_clarification_pii_leakage_is_sanitized_in_full_graph(self):
        """Clarification generator echoing PII (e.g. phone/Aadhaar) is redacted by response_guardrail_node."""
        classifier = FakeClassifier(IntentType.AMBIGUOUS)
        # Mock generator returning text with an Indian phone number and PAN
        leaky_generator = MockClarificationGenerator(
            "Did you mean the application submitted by 9876543210 with PAN ABCDE1234F?"
        )

        def leaky_clarification(state: dict[str, Any]) -> dict[str, Any]:
            return ask_for_clarification(state, leaky_generator)

        result = invoke_full_graph(
            _make_input_result(),
            classifier=classifier,
            clarification=leaky_clarification,
        )

        assert leaky_generator.called
        assert len(result["messages"]) == 1
        output_content = result["messages"][0].content
        # Phone and PAN must be redacted
        assert "9876543210" not in output_content
        assert "ABCDE1234F" not in output_content
        assert "[REDACTED" in output_content

        # Observability flags recorded
        guardrail_flags = result.get("guardrail_flags", {})
        assert guardrail_flags.get("any_triggered") is True
        assert guardrail_flags.get("pii_redaction_count", 0) >= 2

    def test_clarification_credential_solicitation_is_intercepted_in_full_graph(self):
        """Clarification generator asking for OTP is intercepted and replaced with fallback."""
        classifier = FakeClassifier(IntentType.AMBIGUOUS)
        soliciting_generator = MockClarificationGenerator(
            "To verify your identity, please share your 6-digit OTP."
        )

        def soliciting_clarification(state: dict[str, Any]) -> dict[str, Any]:
            return ask_for_clarification(state, soliciting_generator)

        result = invoke_full_graph(
            _make_input_result(),
            classifier=classifier,
            clarification=soliciting_clarification,
        )

        assert soliciting_generator.called
        assert len(result["messages"]) == 1
        output_content = result["messages"][0].content
        assert "share your 6-digit OTP" not in output_content
        assert "never ask for your passwords, OTPs, or financial credentials" in output_content

        guardrail_flags = result.get("guardrail_flags", {})
        assert guardrail_flags.get("any_triggered") is True
        assert guardrail_flags.get("credential_decision") == ResponseGuardrailDecision.REPLACE_WITH_FALLBACK


# ---------------------------------------------------------------------------
# 3. Clarification Repetition Guardrail Tests
# ---------------------------------------------------------------------------

class TestClarificationRepetitionGuardrail:
    """Verify repetitive clarification question detection and fallback escalation."""

    def test_non_repeated_question_passes_unchanged(self):
        """Unique question is not altered."""
        gen = MockClarificationGenerator("Which state are you applying from?")
        state = {
            "intent_decision": IntentDecision(
                intent_type=IntentType.AMBIGUOUS,
                confidence_score=0.9,
                query="certificate",
                reasoning="test",
            ),
            "messages": [HumanMessage(content="I want a certificate")],
            "clarification_round_count": 0,
        }
        res = ask_for_clarification(state, gen)
        assert res["messages"][0].content == "Which state are you applying from?"

    def test_exact_repeated_question_replaced_with_fallback(self):
        """Repeated question identical to previous assistant turn is replaced."""
        gen = MockClarificationGenerator("Which state are you applying from?")
        state = {
            "intent_decision": IntentDecision(
                intent_type=IntentType.AMBIGUOUS,
                confidence_score=0.9,
                query="certificate",
                reasoning="test",
            ),
            "messages": [
                HumanMessage(content="I need help"),
                AIMessage(content="Which state are you applying from?"),
                HumanMessage(content="Yes please"),
            ],
            "clarification_round_count": 1,
        }
        res = ask_for_clarification(state, gen)
        assert res["messages"][0].content == _REPETITIVE_QUESTION_FALLBACK

    def test_near_identical_repeated_question_replaced_with_fallback(self):
        """Repeated question with minor punctuation/casing differences is replaced."""
        gen = MockClarificationGenerator("which state are you applying from???")
        state = {
            "intent_decision": IntentDecision(
                intent_type=IntentType.AMBIGUOUS,
                confidence_score=0.9,
                query="certificate",
                reasoning="test",
            ),
            "messages": [
                {"role": "assistant", "content": "Which state are you applying from?"},
                {"role": "user", "content": "Tell me"},
            ],
            "clarification_round_count": 1,
        }
        res = ask_for_clarification(state, gen)
        assert res["messages"][0].content == _REPETITIVE_QUESTION_FALLBACK

    def test_human_messages_not_mistaken_for_assistant_repetition(self):
        """If user repeats a question phrasing, it is not flagged as assistant repetition."""
        gen = MockClarificationGenerator("Which state are you applying from?")
        state = {
            "intent_decision": IntentDecision(
                intent_type=IntentType.AMBIGUOUS,
                confidence_score=0.9,
                query="certificate",
                reasoning="test",
            ),
            "messages": [
                HumanMessage(content="Which state are you applying from?"),
            ],
            "clarification_round_count": 0,
        }
        res = ask_for_clarification(state, gen)
        assert res["messages"][0].content == "Which state are you applying from?"


# ---------------------------------------------------------------------------
# 4. Routing Loop Hardening Tests
# ---------------------------------------------------------------------------

class TestRoutingLoopHardening:
    """Verify safe parsing and deterministic cap on clarification loops."""

    @pytest.mark.parametrize(
        "corrupt_val, expected_node",
        [
            (None, CLARIFICATION_NODE),
            ("invalid", CLARIFICATION_NODE),
            (-1, CLARIFICATION_NODE),
            ("0", CLARIFICATION_NODE),
            (2, CLARIFICATION_NODE),
            (3, RETRIEVER_NODE),
            ("3", RETRIEVER_NODE),
            (5, RETRIEVER_NODE),
            (100, RETRIEVER_NODE),
        ],
    )
    def test_route_after_intent_full_safe_handling(self, corrupt_val: Any, expected_node: str):
        """route_after_intent_full handles corrupt types and caps at MAX_CLARIFICATION_ROUNDS."""
        state = {
            "intent_decision": IntentDecision(
                intent_type=IntentType.AMBIGUOUS,
                confidence_score=0.9,
                query="status",
                reasoning="test",
            ),
            "clarification_round_count": corrupt_val,
        }
        node = route_after_intent_full(state)
        assert node == expected_node

    @pytest.mark.parametrize(
        "corrupt_val, expected_node",
        [
            (None, CLARIFICATION_NODE),
            ("invalid", CLARIFICATION_NODE),
            (2, CLARIFICATION_NODE),
            (3, RETRIEVER_NODE),
            (10, RETRIEVER_NODE),
        ],
    )
    def test_route_after_intent_legacy_safe_handling(self, corrupt_val: Any, expected_node: str):
        """route_after_intent legacy also handles corrupt types safely."""
        state = {
            "intent_decision": IntentDecision(
                intent_type=IntentType.AMBIGUOUS,
                confidence_score=0.9,
                query="status",
                reasoning="test",
            ),
            "clarification_round_count": corrupt_val,
        }
        node = route_after_intent(state)
        assert node == expected_node
