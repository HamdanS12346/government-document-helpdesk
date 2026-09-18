"""Tests for guardrails/response.py — output guardrails.

Tests are grouped by guardrail class. Each class tests:
  - The ALLOW path (clean input passes through unchanged)
  - Each non-ALLOW decision path
  - Edge cases (empty input, None context, etc.)
  - The composite runner (pipeline order, short-circuit on REJECT)
"""

from __future__ import annotations

import pytest

from app.contracts.response import ContextSource, RetrievedContext
from guardrails.response import (
    CitationGroundingGuardrail,
    CitationGroundingResult,
    FactualityHallucinationGuardrail,
    HallucinationCheckResult,
    ResponseGuardrailDecision,
    ResponseGuardrailReport,
    ResponseLengthGuardrail,
    ResponsePIIScanner,
    ResponseScopeGuardrail,
    ResponseScopeResult,
    extract_document_chunks,
    extract_enclosing_statement,
    is_statement_supported_by_chunk,
    run_response_guardrails,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_context(num_sources: int, fallback_applied: bool = False) -> RetrievedContext:
    """Build a minimal RetrievedContext with `num_sources` sources."""
    sources = [
        ContextSource(index=i + 1, chunk_id=f"chunk-{i}", document_name=f"doc-{i}")
        for i in range(num_sources)
    ]
    return RetrievedContext(
        formatted_context="some context text",
        sources=sources,
        total_documents_retrieved=num_sources,
        documents_used=num_sources,
        has_relevant_documents=num_sources > 0 and not fallback_applied,
        fallback_applied=fallback_applied,
    )


def _make_context_with_chunks(chunks_dict: dict[int, str]) -> RetrievedContext:
    """Build a RetrievedContext with full [Document N] formatted context blocks."""
    formatted_blocks = []
    sources = []
    for idx, content in chunks_dict.items():
        formatted_blocks.append(
            f"[Document {idx}]\n"
            f"Document: doc-{idx}\n"
            f"Category: general\n"
            f"Content:\n{content}"
        )
        sources.append(
            ContextSource(index=idx, chunk_id=f"chunk-{idx}", document_name=f"doc-{idx}")
        )
    return RetrievedContext(
        formatted_context="\n\n---\n\n".join(formatted_blocks),
        sources=sources,
        total_documents_retrieved=len(sources),
        documents_used=len(sources),
        has_relevant_documents=len(sources) > 0,
        fallback_applied=False,
    )


# ---------------------------------------------------------------------------
# TestCitationGroundingGuardrail
# ---------------------------------------------------------------------------

class TestCitationGroundingGuardrail:
    """Tests for CitationGroundingGuardrail."""

    guardrail = CitationGroundingGuardrail()

    def test_allow_when_no_citations_in_response(self):
        """Response with no [Document N] references always ALLOWs."""
        ctx = _make_context(2)
        result = self.guardrail.check("Here is some guidance.", ctx)
        assert result.decision == ResponseGuardrailDecision.ALLOW
        assert result.total_citations_found == 0
        assert result.cleaned_text == "Here is some guidance."

    def test_allow_when_all_citations_valid(self):
        """All cited documents exist in sources → ALLOW."""
        ctx = _make_context(3)
        text = "See [Document 1] and [Document 2] for details."
        result = self.guardrail.check(text, ctx)
        assert result.decision == ResponseGuardrailDecision.ALLOW
        assert result.invalid_citation_indices == []

    def test_strip_when_some_citations_invalid(self):
        """A minority of invalid citations → STRIP_INVALID_CITATIONS."""
        ctx = _make_context(2)  # valid: 1, 2
        text = "See [Document 1] and [Document 5] for more."
        result = self.guardrail.check(text, ctx)
        assert result.decision == ResponseGuardrailDecision.STRIP_INVALID_CITATIONS
        assert 5 in result.invalid_citation_indices
        assert "[source unavailable]" in result.cleaned_text
        assert "[Document 1]" in result.cleaned_text  # valid one preserved

    def test_reject_when_majority_of_citations_invalid(self):
        """More than 50% invalid → REJECT with fallback text."""
        ctx = _make_context(1)  # valid: 1 only
        text = "See [Document 1], [Document 2], [Document 3]."
        result = self.guardrail.check(text, ctx)
        assert result.decision == ResponseGuardrailDecision.REJECT
        assert "government portals" in result.cleaned_text

    def test_allow_when_no_context(self):
        """retrieved_context=None (general_chat path) → always ALLOW."""
        result = self.guardrail.check("Hello, how can I help?", None)
        assert result.decision == ResponseGuardrailDecision.ALLOW

    def test_reject_when_context_has_no_sources_but_response_cites(self):
        """Empty sources list but response cites documents → all invalid → REJECT."""
        ctx = _make_context(0)
        text = "According to [Document 1] and [Document 2], you must apply online."
        result = self.guardrail.check(text, ctx)
        assert result.decision == ResponseGuardrailDecision.REJECT

    def test_case_insensitive_citation_pattern(self):
        """Citation pattern matches [document 1] and [DOCUMENT 1]."""
        ctx = _make_context(2)
        text = "Refer to [document 1] for details."
        result = self.guardrail.check(text, ctx)
        assert result.decision == ResponseGuardrailDecision.ALLOW

    def test_allows_exact_boundary_fraction(self):
        """Exactly 50% invalid is STRIP, not REJECT (boundary inclusive)."""
        ctx = _make_context(2)  # valid: 1, 2
        text = "See [Document 1] and [Document 9]."  # 1 of 2 = 50%
        result = self.guardrail.check(text, ctx)
        assert result.decision == ResponseGuardrailDecision.STRIP_INVALID_CITATIONS

    def test_allow_when_citation_statement_supported_by_chunk(self):
        """Citation [Document 1] exists AND its content supports the claim → ALLOW."""
        ctx = _make_context_with_chunks({
            1: "Applicants must submit Form 9 and a medical fitness certificate to renew their driving licence at the RTO.",
        })
        text = "To renew your driving licence, submit Form 9 to the zonal RTO [Document 1]."
        result = self.guardrail.check(text, ctx)
        assert result.decision == ResponseGuardrailDecision.ALLOW
        assert result.supported_citations_found == 1
        assert result.unsupported_citation_indices == []
        assert "[Document 1]" in result.cleaned_text

    def test_reject_when_citation_statement_not_supported_by_chunk(self):
        """Citation [Document 1] exists in sources but chunk content is about an unrelated topic → REJECT."""
        ctx = _make_context_with_chunks({
            1: "To apply for a passport, visit the Passport Seva Kendra with birth certificate and address proof.",
        })
        # Claim is about driving licence, citing passport document
        text = "To renew your driving licence, submit Form 9 to the zonal RTO [Document 1]."
        result = self.guardrail.check(text, ctx)
        assert result.decision == ResponseGuardrailDecision.REJECT
        assert 1 in result.unsupported_citation_indices
        assert 1 in result.invalid_citation_indices
        assert "government portals" in result.cleaned_text

    def test_strip_when_minority_citation_unsupported_by_chunk(self):
        """One citation is supported and one is unsupported (50%) → STRIP_INVALID_CITATIONS."""
        ctx = _make_context_with_chunks({
            1: "To renew your driving licence, submit Form 9 to the RTO office.",
            2: "To apply for a passport, visit the Passport Seva Kendra with proof of birth.",
        })
        # Sentence 1 is supported by Doc 1. Sentence 2 misattributes passport claim to Doc 2.
        text = (
            "To renew your driving licence, submit Form 9 to the RTO [Document 1]. "
            "Your tax assessment will be completed in 7 days [Document 2]."
        )
        result = self.guardrail.check(text, ctx)
        assert result.decision == ResponseGuardrailDecision.STRIP_INVALID_CITATIONS
        assert 2 in result.unsupported_citation_indices
        assert "[Document 1]" in result.cleaned_text
        assert "[source unavailable]" in result.cleaned_text

    def test_multicitation_in_same_sentence_supported(self):
        """Multiple citations in a single sentence supported by their respective chunks → ALLOW."""
        ctx = _make_context_with_chunks({
            1: "Driving licence renewal requires identity verification.",
            2: "Aadhaar card is accepted as valid proof of identity.",
        })
        text = "You can submit your driving licence [Document 1] or Aadhaar card [Document 2] for verification."
        result = self.guardrail.check(text, ctx)
        assert result.decision == ResponseGuardrailDecision.ALLOW
        assert result.supported_citations_found == 2
        assert result.unsupported_citation_indices == []


# ---------------------------------------------------------------------------
# TestCitationAttributionVerification
# ---------------------------------------------------------------------------

class TestCitationAttributionVerification:
    """Unit tests for statement extraction, chunk parsing, and lexical grounding helpers."""

    def test_extract_document_chunks(self):
        raw = (
            "[Document 1]\n"
            "Document: dl-guide\n"
            "Category: transport\n"
            "Content:\n"
            "Driving licence rules and renewal.\n"
            "---\n"
            "[Document 2]\n"
            "Document: pan-guide\n"
            "Category: finance\n"
            "Content:\n"
            "PAN card application instructions.\n"
        )
        chunks = extract_document_chunks(raw)
        assert 1 in chunks
        assert 2 in chunks
        assert "Driving licence rules" in chunks[1]
        assert "PAN card application" in chunks[2]

    def test_extract_enclosing_statement_sentence(self):
        text = "First step is simple. Renew your driving licence at the RTO [Document 1]. Then pay fees."
        match_start = text.index("[Document 1]")
        match_end = match_start + len("[Document 1]")
        statement = extract_enclosing_statement(text, match_start, match_end)
        assert "Renew your driving licence at the RTO" in statement
        assert "First step is simple" not in statement

    def test_extract_enclosing_statement_short_pointer_extends_backwards(self):
        text = "To renew your driving licence, submit Form 9. See [Document 1]."
        match_start = text.index("[Document 1]")
        match_end = match_start + len("[Document 1]")
        statement = extract_enclosing_statement(text, match_start, match_end)
        assert "driving licence" in statement
        assert "submit Form 9" in statement

    def test_is_statement_supported_by_chunk_matches_and_mismatches(self):
        chunk = "Applicants must submit Form 9 along with a medical fitness certificate to renew driving licence."
        supported_claim = "You must submit Form 9 and medical certificate to renew driving licence."
        unsupported_claim = "Apply for passport online through Passport Seva Kendra."

        assert is_statement_supported_by_chunk(supported_claim, chunk) is True
        assert is_statement_supported_by_chunk(unsupported_claim, chunk) is False



# ---------------------------------------------------------------------------
# TestResponsePIIScanner
# ---------------------------------------------------------------------------

class TestResponsePIIScanner:
    """Tests for ResponsePIIScanner."""

    scanner = ResponsePIIScanner()

    def test_allow_clean_text(self):
        """Text with no PII → ALLOW with unchanged text."""
        text = "To apply, visit the official portal and fill out Form 16."
        result = self.scanner.scan(text)
        assert result.decision == ResponseGuardrailDecision.ALLOW
        assert result.redaction_count == 0
        assert result.cleaned_text == text

    def test_redacts_pan_number(self):
        """PAN card number (ABCDE1234F) is redacted."""
        text = "Your PAN number ABCDE1234F has been verified."
        result = self.scanner.scan(text)
        assert result.decision == ResponseGuardrailDecision.REDACT_AND_CONTINUE
        assert "ABCDE1234F" not in result.cleaned_text
        assert "[REDACTED]" in result.cleaned_text
        assert result.redaction_count >= 1

    def test_redacts_aadhaar_number(self):
        """12-digit Aadhaar number is redacted."""
        text = "Aadhaar 1234 5678 9012 is linked to your account."
        result = self.scanner.scan(text)
        assert result.decision == ResponseGuardrailDecision.REDACT_AND_CONTINUE
        assert result.redaction_count >= 1

    def test_redacts_phone_number(self):
        """Indian mobile number is redacted."""
        text = "Please call 9876543210 for assistance."
        result = self.scanner.scan(text)
        assert result.decision == ResponseGuardrailDecision.REDACT_AND_CONTINUE
        assert "9876543210" not in result.cleaned_text

    def test_redacts_email_address(self):
        """Citizen personal email address is redacted."""
        text = "Contact applicant at citizen@example.com for help."
        result = self.scanner.scan(text)
        assert result.decision == ResponseGuardrailDecision.REDACT_AND_CONTINUE
        assert "citizen@example.com" not in result.cleaned_text

    def test_preserves_official_government_email_and_helpline(self):
        """Official government emails and helplines are preserved without redaction."""
        text = (
            "For inquiries, email support@uidai.gov.in or contact the "
            "national helpline 1800-180-1947 or call UIDAI helpline 1947."
        )
        result = self.scanner.scan(text)
        assert result.decision == ResponseGuardrailDecision.ALLOW
        assert "support@uidai.gov.in" in result.cleaned_text
        assert "1800-180-1947" in result.cleaned_text
        assert "1947" in result.cleaned_text

    def test_multiple_pii_types_all_redacted(self):
        """Multiple PII types in one response — all redacted."""
        text = (
            "Your PAN ABCDE1234F and Aadhaar 1234 5678 9012 are needed. "
            "Call 9876543210 or email you@example.com."
        )
        result = self.scanner.scan(text)
        assert result.decision == ResponseGuardrailDecision.REDACT_AND_CONTINUE
        assert result.redaction_count >= 3

    def test_redaction_count_is_accurate(self):
        """redaction_count reflects actual number of substitutions made."""
        text = "PAN ABCDE1234F and FGHIJ5678K are both invalid."
        result = self.scanner.scan(text)
        assert result.redaction_count == 2


# ---------------------------------------------------------------------------
# TestResponseLengthGuardrail
# ---------------------------------------------------------------------------

class TestResponseLengthGuardrail:
    """Tests for ResponseLengthGuardrail."""

    guardrail = ResponseLengthGuardrail(max_chars=100, hard_reject_chars=200)

    def test_allow_under_limit(self):
        """Text under max_chars → ALLOW unchanged."""
        text = "Short response."
        result = self.guardrail.check(text)
        assert result.decision == ResponseGuardrailDecision.ALLOW
        assert result.cleaned_text == text

    def test_allow_at_exact_limit(self):
        """Text exactly at max_chars → ALLOW."""
        text = "A" * 100
        result = self.guardrail.check(text)
        assert result.decision == ResponseGuardrailDecision.ALLOW

    def test_truncate_between_soft_and_hard_limit(self):
        """Text between max_chars and hard_reject_chars → TRUNCATE."""
        # Build text with a sentence boundary before char 100.
        text = ("This is sentence one. " * 5) + ("Extra text " * 5)
        assert len(text) > 100
        assert len(text) <= 200
        result = self.guardrail.check(text)
        assert result.decision == ResponseGuardrailDecision.TRUNCATE
        assert "shortened" in result.cleaned_text
        assert result.final_length < result.original_length

    def test_truncate_appends_suffix(self):
        """Truncated response includes the shortening notice suffix."""
        text = "A" * 50 + ". " + "B" * 100
        result = self.guardrail.check(text)
        assert result.decision == ResponseGuardrailDecision.TRUNCATE
        assert "[Response was shortened." in result.cleaned_text

    def test_reject_above_hard_limit(self):
        """Text above hard_reject_chars → REJECT with safe fallback."""
        text = "A" * 201
        result = self.guardrail.check(text)
        assert result.decision == ResponseGuardrailDecision.REJECT
        assert "concerned department" in result.cleaned_text

    def test_constructor_validates_limits(self):
        """max_chars must be less than hard_reject_chars."""
        with pytest.raises(ValueError):
            ResponseLengthGuardrail(max_chars=500, hard_reject_chars=500)

    def test_truncation_finds_sentence_boundary(self):
        """Truncation cuts at the last sentence boundary, not mid-word."""
        text = "First sentence ends here. " + "X" * 100
        result = ResponseLengthGuardrail(max_chars=30, hard_reject_chars=200).check(text)
        assert result.decision == ResponseGuardrailDecision.TRUNCATE
        # The cut should be after "here." not in the middle of the X block
        assert result.cleaned_text.startswith("First sentence ends here.")


# ---------------------------------------------------------------------------
# TestResponseScopeGuardrail
# ---------------------------------------------------------------------------

class TestResponseScopeGuardrail:
    """Tests for ResponseScopeGuardrail."""

    guardrail = ResponseScopeGuardrail()

    def test_allow_government_response_general_chat(self):
        """On-topic government response in general_chat → ALLOW."""
        text = "To get your Aadhaar card, visit the UIDAI portal and complete e-KYC."
        result = self.guardrail.check(text, intent_type="general_chat")
        assert result.decision == ResponseGuardrailDecision.ALLOW

    def test_replace_off_topic_cricket_response(self):
        """Response about cricket with no government signal → REPLACE_WITH_REDIRECT."""
        text = (
            "The IPL match scorecard shows that cricket has exciting moments. "
            "India won the football and cricket matches this season!"
        )
        result = self.guardrail.check(text, intent_type="general_chat")
        assert result.decision == ResponseGuardrailDecision.REPLACE_WITH_REDIRECT
        assert "government documents" in result.cleaned_text

    def test_allow_single_forbidden_keyword(self):
        """One forbidden keyword alone does not trigger replacement (threshold is 2)."""
        text = "The cricket ground lease requires a municipal permit."
        result = self.guardrail.check(text, intent_type="general_chat")
        # "cricket" is one forbidden match but there is also a government signal (municipal)
        assert result.decision == ResponseGuardrailDecision.ALLOW

    def test_allow_for_document_info_intent(self):
        """document_info intent is always skipped — even fully off-topic text passes."""
        text = "Watch IPL cricket and Bollywood movies on OTT platforms!"
        result = self.guardrail.check(text, intent_type="document_info")
        assert result.decision == ResponseGuardrailDecision.ALLOW

    def test_allow_stock_market_with_government_signal(self):
        """Stock market content with government signal → not replaced."""
        text = "The ministry regulates the sensex and share market trading activities."
        result = self.guardrail.check(text, intent_type="general_chat")
        # sensex/trading are forbidden, but "ministry" is a government signal
        assert result.decision == ResponseGuardrailDecision.ALLOW

    def test_replace_multiple_forbidden_zero_government(self):
        """Multiple forbidden matches, no government signals → REPLACE_WITH_REDIRECT."""
        text = "Check the horoscope and lottery results for the best gambling tips."
        result = self.guardrail.check(text, intent_type="general_chat")
        assert result.decision == ResponseGuardrailDecision.REPLACE_WITH_REDIRECT

    def test_forbidden_matches_list_populated(self):
        """forbidden_matches contains the actual matched strings."""
        text = "Watch Bollywood films and check the recipe for today."
        result = self.guardrail.check(text, intent_type="general_chat")
        assert len(result.forbidden_matches) >= 2


# ---------------------------------------------------------------------------
# TestRunResponseGuardrails — composite pipeline
# ---------------------------------------------------------------------------

class TestRunResponseGuardrails:
    """Tests for the run_response_guardrails composite runner."""

    def test_clean_response_passes_with_no_trigger(self):
        """A clean response triggers nothing — any_triggered is False."""
        ctx = _make_context(2)
        text = "Visit the income tax portal at incometax.gov.in for Form 16 details."
        report = run_response_guardrails(text, ctx, intent_type="document_info")
        assert not report.any_triggered
        assert report.final_text == text

    def test_pii_redaction_is_applied(self):
        """PII in a clean response is redacted and any_triggered is True."""
        ctx = _make_context(1)
        text = "Your Aadhaar 1234 5678 9012 is linked. Visit the portal."
        report = run_response_guardrails(text, ctx, intent_type="document_info")
        assert report.any_triggered
        assert "1234 5678 9012" not in report.final_text
        assert report.pii_result.redaction_count >= 1

    def test_citation_stripping_is_applied(self):
        """Invalid citations are stripped and any_triggered is True."""
        ctx = _make_context(1)  # only Document 1 exists
        text = "See [Document 1] and [Document 99] for details."
        report = run_response_guardrails(text, ctx, intent_type="document_info")
        assert report.any_triggered
        assert "[Document 99]" not in report.final_text
        assert "[source unavailable]" in report.final_text

    def test_citation_reject_short_circuits_pii_scan(self):
        """On REJECT from citation guardrail, fallback text goes through PII scan."""
        ctx = _make_context(0)  # no sources at all
        text = "See [Document 1] and [Document 2]. Your PAN is ABCDE1234F."
        report = run_response_guardrails(text, ctx, intent_type="document_info")
        # Citation guardrail REJECTs → fallback text used
        assert report.citation_result.decision == ResponseGuardrailDecision.REJECT
        # PII scanner runs on fallback text (which has no PII)
        assert report.pii_result.decision == ResponseGuardrailDecision.ALLOW
        # Final text is the safe fallback
        assert "government portals" in report.final_text

    def test_pipeline_order_pii_runs_after_citation(self):
        """PII scanner sees the output of citation guardrail, not original text."""
        ctx = _make_context(1)
        # [Document 9] is invalid; PAN follows in same text
        text = "See [Document 9]. Call 9876543210 for details."
        report = run_response_guardrails(text, ctx, intent_type="document_info")
        assert "[Document 9]" not in report.final_text
        assert "9876543210" not in report.final_text

    def test_any_triggered_true_when_scope_replaces(self):
        """any_triggered is True when scope guardrail fires."""
        report = run_response_guardrails(
            "Watch Bollywood movies and check the lottery results.",
            retrieved_context=None,
            intent_type="general_chat",
        )
        assert report.any_triggered
        assert report.scope_result.decision == ResponseGuardrailDecision.REPLACE_WITH_REDIRECT

    def test_report_fields_all_populated(self):
        """All result fields on the report are populated regardless of decisions."""
        ctx = _make_context(2)
        text = "To apply for a passport, visit the passport portal."
        report = run_response_guardrails(text, ctx, intent_type="document_info")
        assert isinstance(report.citation_result, type(report.citation_result))
        assert isinstance(report.pii_result.redaction_count, int)
        assert isinstance(report.length_result.original_length, int)
        assert isinstance(report.scope_result.forbidden_matches, list)
        assert report.hallucination_result is not None

    def test_composite_runner_does_not_replace_pin_language(self):
        """The response pipeline no longer applies the removed fallback."""
        ctx = _make_context(1)
        text = "To get an e-PAN, use the income tax portal and enter your PIN code if required."
        report = run_response_guardrails(text, ctx, intent_type="document_info")

        assert report.final_text == text
        assert not report.any_triggered


# ---------------------------------------------------------------------------
# TestFactualityHallucinationGuardrail
# ---------------------------------------------------------------------------

class TestFactualityHallucinationGuardrail:
    """Tests for FactualityHallucinationGuardrail (fees, dates & requirements)."""

    guardrail = FactualityHallucinationGuardrail()

    def test_allow_when_fees_and_deadlines_grounded(self):
        """Grounded fees and deadlines pass with ALLOW."""
        ctx = _make_context(1)
        ctx.formatted_context = (
            "Permanent driving license issuance fee is ₹500. "
            "Dispatch timeline is within 30 days after test."
        )
        response = "The fee is ₹500 and the license will be delivered within 30 days."
        result = self.guardrail.check(response, ctx)
        assert result.decision == ResponseGuardrailDecision.ALLOW
        assert len(result.unsupported_entities) == 0
        assert len(result.supported_entities) >= 1

    def test_allow_when_no_entities_present(self):
        """Responses with no numbers or dates pass with ALLOW."""
        ctx = _make_context(1)
        ctx.formatted_context = "Visit the official government portal to apply."
        response = "Please visit the official portal to complete your application."
        result = self.guardrail.check(response, ctx)
        assert result.decision == ResponseGuardrailDecision.ALLOW
        assert result.total_entities_found == 0

    def test_allow_when_context_is_none(self):
        """general_chat without context passes with ALLOW."""
        response = "The general registration charges are ₹100."
        result = self.guardrail.check(response, retrieved_context=None)
        assert result.decision == ResponseGuardrailDecision.ALLOW

    def test_reject_when_fabricated_fee_not_in_context(self):
        """100% fabricated fee replaces response with safe fallback."""
        ctx = _make_context(1)
        ctx.formatted_context = "The nominal fee for passport application is ₹1,500."
        response = "You must pay a processing fee of ₹3,500 to submit your form."
        result = self.guardrail.check(response, ctx)
        assert result.decision == ResponseGuardrailDecision.REPLACE_WITH_FALLBACK
        assert len(result.unsupported_entities) == 1
        assert "3,500" in result.unsupported_entities[0]
        assert "official government portal" in result.cleaned_text

    def test_warn_and_append_when_partial_unsupported_entity(self):
        """Partial hallucination (<= 50%) appends official notice rather than hard reject."""
        ctx = _make_context(1)
        ctx.formatted_context = (
            "The driving license fee is ₹500. Application review is within 15 days."
        )
        # ₹500 is supported, but within 90 days is unsupported (1 of 2 = 50%)
        response = "The fee is ₹500 and processing will take within 90 days."
        result = self.guardrail.check(response, ctx)
        assert result.decision == ResponseGuardrailDecision.WARN_AND_APPEND
        assert len(result.supported_entities) == 1
        assert len(result.unsupported_entities) == 1
        assert "within 90 days" in result.unsupported_entities[0]
        assert "[Official Notice:" in result.cleaned_text
        assert "The fee is ₹500" in result.cleaned_text

    def test_reject_when_fabricated_deadline_and_age(self):
        """Fabricated requirements (> 50%) trigger fallback replacement."""
        ctx = _make_context(1)
        ctx.formatted_context = "Applicant must be minimum age of 18 years."
        response = "You must be minimum age of 28 years and apply within 60 days."
        result = self.guardrail.check(response, ctx)
        assert result.decision == ResponseGuardrailDecision.REPLACE_WITH_FALLBACK
        assert len(result.unsupported_entities) >= 1

    def test_composite_runner_triggers_hallucination_guardrail(self):
        """run_response_guardrails executes hallucination check and reports trigger."""
        ctx = _make_context(1)
        ctx.formatted_context = "Voter card application fee is ₹25."
        response = "The voter registration fee is ₹2,000 [Document 1]."
        report = run_response_guardrails(response, ctx, intent_type="document_info")
        assert report.any_triggered is True
        assert report.hallucination_result is not None
        assert report.hallucination_result.decision == ResponseGuardrailDecision.REPLACE_WITH_FALLBACK
        assert "official government portal" in report.final_text
