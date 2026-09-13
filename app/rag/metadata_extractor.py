"""Metadata extraction subsystem for pre-filtering documents based on category catalog."""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class MetadataFilterDecision(BaseModel):
    """Structured decision for metadata-based retrieval pre-filtering."""

    category: Optional[str] = Field(
        default=None,
        description="Exact category from catalog (e.g. 'identity-documents'), or None if uncertain or multi-topic.",
    )
    document_name: Optional[str] = Field(
        default=None,
        description="Exact subcategory/document_name from catalog (e.g. 'aadhaar-card'), or None if uncertain.",
    )
    is_confident: bool = Field(
        description="True ONLY if the query unequivocally targets this specific document or category with high confidence.",
    )
    reasoning: str = Field(
        default="",
        description="Brief explanation of why the category/document was selected or why filtering was skipped.",
    )


class MetadataExtractor:
    """Extracts high-confidence category and subcategory filters from queries using an LLM and catalog."""

    def __init__(
        self,
        catalog_path: Optional[str] = None,
        llm: Optional[BaseChatModel] = None,
    ):
        self._llm = llm
        self.catalog_path = catalog_path or str(Path(__file__).parent / "metadata_catalog.json")
        self.catalog: Dict[str, List[str]] = self._load_catalog(self.catalog_path)
        self._system_prompt = self._build_system_prompt()

    def _load_catalog(self, path: str) -> Dict[str, List[str]]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.error("Failed to load metadata catalog from %s: %s", path, exc)
            return {}

    def _get_llm(self) -> BaseChatModel:
        if self._llm is None:
            self._llm = ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0.0,
                api_key=os.getenv("OPENAI_API_KEY"),
            )
        return self._llm

    def _build_system_prompt(self) -> str:
        catalog_formatted = json.dumps(self.catalog, indent=2)
        return (
            "You are an expert government document classification system.\n"
            "Your task is to analyze a user's query and decide whether it unambiguously targets a specific "
            "category and/or document (subcategory) from the official catalog.\n\n"
            "### OFFICIAL CATALOG:\n"
            f"{catalog_formatted}\n\n"
            "### STRICT FILTERING RULES:\n"
            "1. Only choose a category or document_name if the query unequivocally focuses on that specific item.\n"
            "2. Set is_confident=True ONLY when you are completely certain that filtering by this category or document will NOT exclude relevant information.\n"
            "3. If the query is broad, generic, ambiguous, multi-topic, or asks about relationships between multiple documents, "
            "set category=None, document_name=None, and is_confident=False. Do NOT guess.\n"
            "4. Both 'category' and 'document_name' MUST strictly match the exact strings in the catalog.\n"
            "5. If you recognize the category with certainty but the query could apply to any document in that category, "
            "populate 'category', leave document_name=None, and set is_confident=True.\n"
        )

    def extract(self, query: str) -> MetadataFilterDecision:
        """Extract metadata filter decision from query."""
        query = (query or "").strip()
        if not query or not self.catalog:
            return MetadataFilterDecision(
                category=None,
                document_name=None,
                is_confident=False,
                reasoning="Empty query or empty catalog.",
            )

        try:
            llm = self._get_llm()
            structured_llm = llm.with_structured_output(MetadataFilterDecision)

            messages = [
                SystemMessage(content=self._system_prompt),
                HumanMessage(content=f"User Query: {query}"),
            ]
            decision: MetadataFilterDecision = structured_llm.invoke(messages)

            # Validate against catalog to prevent hallucinated keys
            if decision.is_confident:
                if decision.category and decision.category not in self.catalog:
                    logger.warning("Extracted category '%s' not found in catalog; discarding filter.", decision.category)
                    decision.category = None
                    decision.is_confident = False

                if decision.document_name:
                    valid_subcategories = []
                    if decision.category:
                        valid_subcategories = self.catalog.get(decision.category, [])
                    else:
                        for subs in self.catalog.values():
                            valid_subcategories.extend(subs)

                    if decision.document_name not in valid_subcategories:
                        logger.warning("Extracted document_name '%s' not found in catalog; discarding document filter.", decision.document_name)
                        decision.document_name = None
                        if not decision.category:
                            decision.is_confident = False

            return decision

        except Exception as exc:
            logger.warning("Metadata extraction failed with error: %s; skipping filter.", exc)
            return MetadataFilterDecision(
                category=None,
                document_name=None,
                is_confident=False,
                reasoning=f"Extraction error: {exc}",
            )

    @staticmethod
    def build_chroma_filter(decision: MetadataFilterDecision) -> Optional[Dict[str, Any]]:
        """Convert decision to Chroma 'where' syntax."""
        if not decision.is_confident:
            return None

        if decision.category and decision.document_name:
            return {
                "$and": [
                    {"category": decision.category},
                    {"document_name": decision.document_name},
                ]
            }
        elif decision.category:
            return {"category": decision.category}
        elif decision.document_name:
            return {"document_name": decision.document_name}
        return None

    @staticmethod
    def build_criteria(decision: MetadataFilterDecision) -> Optional[Dict[str, str]]:
        """Convert decision to simple key-value criteria for BM25 and in-memory search."""
        if not decision.is_confident:
            return None

        criteria = {}
        if decision.category:
            criteria["category"] = decision.category
        if decision.document_name:
            criteria["document_name"] = decision.document_name
        return criteria or None


__all__ = ["MetadataFilterDecision", "MetadataExtractor"]
