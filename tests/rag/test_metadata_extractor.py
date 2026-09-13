"""Unit tests for MetadataExtractor and MetadataFilterDecision."""

import json
from unittest.mock import MagicMock
import pytest
from app.rag.metadata_extractor import MetadataExtractor, MetadataFilterDecision


def test_catalog_loading(tmp_path):
    """Catalog loads correctly from valid JSON file and falls back on invalid path."""
    catalog_data = {
        "identity-documents": ["aadhaar-card", "voter-id-epic"],
    }
    catalog_file = tmp_path / "test_catalog.json"
    catalog_file.write_text(json.dumps(catalog_data), encoding="utf-8")

    extractor = MetadataExtractor(catalog_path=str(catalog_file))
    assert extractor.catalog == catalog_data

    # Non-existent file
    empty_extractor = MetadataExtractor(catalog_path=str(tmp_path / "non_existent.json"))
    assert empty_extractor.catalog == {}


def test_empty_or_whitespace_query():
    """Empty or whitespace query immediately returns unconfident decision."""
    extractor = MetadataExtractor()
    decision = extractor.extract("   ")
    assert decision.is_confident is False
    assert decision.category is None
    assert decision.document_name is None


def test_confident_extraction_category_and_document():
    """Valid high-confidence extraction retains both category and subcategory."""
    mock_llm = MagicMock()
    mock_structured = MagicMock()
    mock_llm.with_structured_output.return_value = mock_structured
    mock_structured.invoke.return_value = MetadataFilterDecision(
        category="identity-documents",
        document_name="aadhaar-card",
        is_confident=True,
        reasoning="User explicitly asks for Aadhaar card application procedure.",
    )

    extractor = MetadataExtractor(llm=mock_llm)
    decision = extractor.extract("How do I update my mobile number in Aadhaar card?")

    assert decision.is_confident is True
    assert decision.category == "identity-documents"
    assert decision.document_name == "aadhaar-card"


def test_confident_extraction_category_only():
    """Query targeting an entire category without specific subcategory retains category."""
    mock_llm = MagicMock()
    mock_structured = MagicMock()
    mock_llm.with_structured_output.return_value = mock_structured
    mock_structured.invoke.return_value = MetadataFilterDecision(
        category="caste-documents",
        document_name=None,
        is_confident=True,
        reasoning="General query about caste certification process.",
    )

    extractor = MetadataExtractor(llm=mock_llm)
    decision = extractor.extract("What documents are needed for caste verification?")

    assert decision.is_confident is True
    assert decision.category == "caste-documents"
    assert decision.document_name is None


def test_unconfident_or_ambiguous_query():
    """Ambiguous or multi-document queries return unconfident decision."""
    mock_llm = MagicMock()
    mock_structured = MagicMock()
    mock_llm.with_structured_output.return_value = mock_structured
    mock_structured.invoke.return_value = MetadataFilterDecision(
        category=None,
        document_name=None,
        is_confident=False,
        reasoning="Broad query asking about government service portal fees.",
    )

    extractor = MetadataExtractor(llm=mock_llm)
    decision = extractor.extract("What are the portal payment options?")

    assert decision.is_confident is False
    assert decision.category is None
    assert decision.document_name is None


def test_hallucinated_category_discarded():
    """If LLM hallucinates a category not in the catalog, it is discarded and marked unconfident."""
    mock_llm = MagicMock()
    mock_structured = MagicMock()
    mock_llm.with_structured_output.return_value = mock_structured
    mock_structured.invoke.return_value = MetadataFilterDecision(
        category="invalid-financial-category",
        document_name="pan-card",
        is_confident=True,
        reasoning="Hallucinated category name.",
    )

    extractor = MetadataExtractor(llm=mock_llm)
    decision = extractor.extract("How to link PAN card?")

    # Category discarded because it's not in catalog, and decision marked unconfident
    assert decision.category is None
    assert decision.is_confident is False


def test_hallucinated_document_name_with_valid_category():
    """If document_name is hallucinated but category is valid, document_name is dropped while category is kept."""
    mock_llm = MagicMock()
    mock_structured = MagicMock()
    mock_llm.with_structured_output.return_value = mock_structured
    mock_structured.invoke.return_value = MetadataFilterDecision(
        category="identity-documents",
        document_name="non-existent-subdocument",
        is_confident=True,
        reasoning="Valid category but made up document name.",
    )

    extractor = MetadataExtractor(llm=mock_llm)
    decision = extractor.extract("I need help with my identity document")

    assert decision.category == "identity-documents"
    assert decision.document_name is None
    assert decision.is_confident is True



def test_completely_hallucinated_keys_discarded():
    """If both category and document_name are hallucinated, decision is invalidated."""
    mock_llm = MagicMock()
    mock_structured = MagicMock()
    mock_llm.with_structured_output.return_value = mock_structured
    mock_structured.invoke.return_value = MetadataFilterDecision(
        category="random-category",
        document_name="fake-certificate",
        is_confident=True,
        reasoning="Completely made up keys.",
    )

    extractor = MetadataExtractor(llm=mock_llm)
    decision = extractor.extract("Sample query")

    assert decision.category is None
    assert decision.document_name is None
    assert decision.is_confident is False


def test_llm_exception_fallback():
    """Exceptions during LLM invocation trigger graceful fallback to unconfident decision."""
    mock_llm = MagicMock()
    mock_llm.with_structured_output.side_effect = RuntimeError("OpenAI API connection failed")

    extractor = MetadataExtractor(llm=mock_llm)
    decision = extractor.extract("How do I renew my driving license?")

    assert decision.is_confident is False
    assert decision.category is None
    assert decision.document_name is None
    assert "OpenAI API connection failed" in decision.reasoning


def test_build_chroma_filter():
    """Chroma filter syntax correctly builds $and, single-field, or None based on confidence."""
    # Both category and document_name
    decision_both = MetadataFilterDecision(
        category="vehicle-documents",
        document_name="driving-license",
        is_confident=True,
    )
    filter_both = MetadataExtractor.build_chroma_filter(decision_both)
    assert filter_both == {
        "$and": [
            {"category": "vehicle-documents"},
            {"document_name": "driving-license"},
        ]
    }

    # Category only
    decision_cat = MetadataFilterDecision(
        category="vehicle-documents",
        document_name=None,
        is_confident=True,
    )
    assert MetadataExtractor.build_chroma_filter(decision_cat) == {"category": "vehicle-documents"}

    # Document only
    decision_doc = MetadataFilterDecision(
        category=None,
        document_name="driving-license",
        is_confident=True,
    )
    assert MetadataExtractor.build_chroma_filter(decision_doc) == {"document_name": "driving-license"}

    # Unconfident
    decision_unconf = MetadataFilterDecision(
        category="vehicle-documents",
        document_name="driving-license",
        is_confident=False,
    )
    assert MetadataExtractor.build_chroma_filter(decision_unconf) is None


def test_build_criteria():
    """BM25 criteria dictionary correctly mirrors confident decision."""
    decision_both = MetadataFilterDecision(
        category="vehicle-documents",
        document_name="driving-license",
        is_confident=True,
    )
    criteria = MetadataExtractor.build_criteria(decision_both)
    assert criteria == {
        "category": "vehicle-documents",
        "document_name": "driving-license",
    }

    decision_unconf = MetadataFilterDecision(
        category="vehicle-documents",
        document_name="driving-license",
        is_confident=False,
    )
    assert MetadataExtractor.build_criteria(decision_unconf) is None
