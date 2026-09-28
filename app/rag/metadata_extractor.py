"""Metadata extraction subsystem for pre-filtering documents based on category catalog."""

import json
import logging
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional
import httpx
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.config.settings import get_settings

logger = logging.getLogger(__name__)

# The 10 major official government document categories
MAJOR_CATEGORIES = [
    "business-and-registration-documents",
    "food-and-public-distribution-documents",
    "health-related-documents",
    "caste-documents",
    "income-documents",
    "vehicle-documents",
    "travel-immigration-documents",
    "identity-documents",
    "civil-registration-documents",
    "residence-documents",
]

CATEGORY_CRITERIA: Dict[str, str] = {
    "business-and-registration-documents": (
        "Inquiries regarding company formation, Certificate of Incorporation, GST registration certificate, "
        "Udyam registration, MSME certificates, trade licenses, or business registry documents."
    ),
    "food-and-public-distribution-documents": (
        "Inquiries regarding ration cards, Public Distribution System (PDS), food grains, Antyodaya, NFSA, "
        "or fair price shops."
    ),
    "health-related-documents": (
        "Inquiries regarding ABHA health account/card, Ayushman Bharat, Unique Disability ID (UDID) certificate, "
        "Mother and Child Protection (MCP) card, disability or medical healthcare records."
    ),
    "caste-documents": (
        "Inquiries regarding SC caste certificate, ST caste certificate, OBC caste certificate, caste validity, "
        "or social welfare caste verification."
    ),
    "income-documents": (
        "Inquiries regarding PAN card, Income Certificate (e.g. Goa/State revenue), Economically Weaker Section "
        "(EWS) certificate, Income Tax Returns (ITR), or revenue proofs."
    ),
    "vehicle-documents": (
        "Inquiries regarding driving license, learner license/permit, vehicle registration certificate (RC), "
        "motor vehicle ownership transfer, or transport department documents."
    ),
    "travel-immigration-documents": (
        "Inquiries regarding Indian passport (fresh/reissue), Overseas Citizen of India (OCI) documents, "
        "visas for entering India, or consular immigration services."
    ),
    "identity-documents": (
        "Inquiries regarding Aadhaar card (enrolment, update, address change, biometric update, PVC card), "
        "Voter ID (EPIC), or fundamental civic identity cards."
    ),
    "civil-registration-documents": (
        "Inquiries regarding birth certificate, death certificate, stillbirth certificate, marriage certificate, "
        "divorce decree, or legal adoption order / adoption deed."
    ),
    "residence-documents": (
        "Inquiries regarding domicile certificate, residence certificate, residential certificate, or official "
        "proof of local residency in a state/UT."
    ),
    "none": (
        "The query is broad, generic, multi-topic, asks about relationships across categories, "
        "or does not clearly and specifically focus on any of the 10 document categories."
    ),
}

# The 27 official government subcategory documents
DOCUMENT_CRITERIA: Dict[str, str] = {
    "certificate-of-incorporation": (
        "Inquiries specifically about Company Certificate of Incorporation, Registrar of Companies (RoC), "
        "Ministry of Corporate Affairs (MCA), company registration deed."
    ),
    "gst-registration-certificate": (
        "Inquiries specifically about Goods and Services Tax (GST) registration, GSTIN certificate, "
        "GST number issuance, or GST portal business registration."
    ),
    "udyam-registration-certificate": (
        "Inquiries specifically about MSME / Udyam registration certificate, Udyog Aadhaar, "
        "small enterprise business registration."
    ),
    "ration-card": (
        "Inquiries specifically about Ration Card (APL/BPL/Antyodaya/NFSA), ration card member addition/deletion, "
        "PDS quota, or fair price shop food distribution."
    ),
    "abha-health-account": (
        "Inquiries specifically about Ayushman Bharat Health Account (ABHA card / ABHA ID number), "
        "digital health account, or national health record ID."
    ),
    "disability-udid-certificate": (
        "Inquiries specifically about Unique Disability ID (UDID card), disability certificate, "
        "Divyangjan identity card, or medical disability percentage."
    ),
    "mother-and-child-protection-card": (
        "Inquiries specifically about Mother and Child Protection (MCP) card, Mamata card, "
        "antenatal care card, or child immunization record card."
    ),
    "sc-caste-certificate": (
        "Inquiries specifically about Scheduled Caste (SC) certificate, SC caste validation, "
        "or SC social welfare verification."
    ),
    "st-caste-certificate": (
        "Inquiries specifically about Scheduled Tribe (ST) certificate, tribal community certificate, "
        "or ST reservation proof."
    ),
    "obc-caste-certificate": (
        "Inquiries specifically about Other Backward Class (OBC) certificate, non-creamy layer (NCL) certificate, "
        "or state/central OBC proof."
    ),
    "pan-card": (
        "Inquiries specifically about Permanent Account Number (PAN card), Form 49A, NSDL/UTIITSL, "
        "PAN correction, reprint, or PAN-Aadhaar linking."
    ),
    "income-certificate-goa": (
        "Inquiries specifically about State or Goa Income Certificate, Mamlatdar/Talathi revenue income certificate, "
        "or local annual family income certificate."
    ),
    "ews-certificate": (
        "Inquiries specifically about Economically Weaker Section (EWS) income and asset certificate "
        "for education or employment reservation."
    ),
    "income-tax-return-and-related-forms": (
        "Inquiries specifically about Income Tax Returns (ITR-1/2/3/4), ITR acknowledgment, Form 16, "
        "Form 26AS, AIS/TIS, or direct tax filing forms."
    ),
    "vehicle-registration-certificate-rc": (
        "Inquiries specifically about Vehicle Registration Certificate (RC), RC book/smart card, "
        "vehicle ownership transfer, RC renewal, or fitness certificate."
    ),
    "driving-license": (
        "Inquiries specifically about Driving License (DL), Learner's License (LL), driving license renewal, "
        "duplicate DL, address update on DL, or RTO driving test."
    ),
    "indian-passport": (
        "Inquiries specifically about Indian Passport (fresh, reissue, renewal, Tatkaal, police verification, "
        "Passport Seva Kendra, or ordinary passport booklet)."
    ),
    "oci-documents": (
        "Inquiries specifically about Overseas Citizen of India (OCI card), OCI registration, OCI miscellaneous "
        "services, or diaspora card."
    ),
    "visa-for-entering-india": (
        "Inquiries specifically about Indian Visa, e-Visa, tourist/business/employment visa for entering India, "
        "FRRO registration, or visa extension."
    ),
    "aadhaar-card": (
        "Inquiries specifically about Aadhaar card enrolment, demographic/biometric update, address change, "
        "mobile number linking, Aadhaar PVC card, or UIDAI services."
    ),
    "voter-id-epic": (
        "Inquiries specifically about Voter ID, Electors Photo Identity Card (EPIC), Form 6/7/8 voter registration, "
        "electoral roll, or NVSP voter card."
    ),
    "adoption-order-adoption-deed": (
        "Inquiries specifically about legal adoption order, court adoption decree, CARA adoption deed, "
        "or child adoption legal certification."
    ),
    "birth-death-stillbirth-certificates": (
        "Inquiries specifically about Birth certificate, Death certificate, or Stillbirth registration certificate, "
        "issued by municipal registrar / CRS."
    ),
    "marriage-certificate-divorce-decree": (
        "Inquiries specifically about Marriage registration certificate, Special Marriage Act, Hindu Marriage Act, "
        "or court Divorce decree."
    ),
    "domicile-certificate": (
        "Inquiries specifically about Domicile certificate, certificate of permanent residence/domicile in a state or UT."
    ),
    "residence-certificate": (
        "Inquiries specifically about Residence certificate issued by state revenue authorities or local administration."
    ),
    "residential-certificate": (
        "Inquiries specifically about Residential certificate, local residence proof certificate."
    ),
    "none": (
        "No specific individual document is explicitly targeted, or the query applies broadly across multiple documents "
        "or the whole category."
    ),
}

# Mapping from document subcategory to its parent major category
DOCUMENT_TO_CATEGORY: Dict[str, str] = {
    "certificate-of-incorporation": "business-and-registration-documents",
    "gst-registration-certificate": "business-and-registration-documents",
    "udyam-registration-certificate": "business-and-registration-documents",
    "ration-card": "food-and-public-distribution-documents",
    "abha-health-account": "health-related-documents",
    "disability-udid-certificate": "health-related-documents",
    "mother-and-child-protection-card": "health-related-documents",
    "sc-caste-certificate": "caste-documents",
    "st-caste-certificate": "caste-documents",
    "obc-caste-certificate": "caste-documents",
    "pan-card": "income-documents",
    "income-certificate-goa": "income-documents",
    "ews-certificate": "income-documents",
    "income-tax-return-and-related-forms": "income-documents",
    "vehicle-registration-certificate-rc": "vehicle-documents",
    "driving-license": "vehicle-documents",
    "indian-passport": "travel-immigration-documents",
    "oci-documents": "travel-immigration-documents",
    "visa-for-entering-india": "travel-immigration-documents",
    "aadhaar-card": "identity-documents",
    "voter-id-epic": "identity-documents",
    "adoption-order-adoption-deed": "civil-registration-documents",
    "birth-death-stillbirth-certificates": "civil-registration-documents",
    "marriage-certificate-divorce-decree": "civil-registration-documents",
    "domicile-certificate": "residence-documents",
    "residence-certificate": "residence-documents",
    "residential-certificate": "residence-documents",
}


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


class JevMetadataExtractor:
    """TypeSafe JEV Decisions API client for metadata pre-filtering across categories and subcategories."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout_seconds: float = 2.5,
        confidence_threshold: float = 0.70,
    ):
        settings = get_settings()
        self.api_key = api_key or settings.openrouter_api_key or os.getenv("OPENROUTER_API_KEY")
        self.model = model or settings.jev_model_name
        self.base_url = base_url or settings.openrouter_base_url
        self.timeout_seconds = timeout_seconds
        self.confidence_threshold = confidence_threshold

    def extract(self, query: str) -> MetadataFilterDecision:
        """Evaluate the query against the 10 major categories and 27 document types in a single JEV Decisions call."""
        start_time = time.perf_counter()
        query_text = (query or "").strip()
        if not query_text:
            return MetadataFilterDecision(
                category=None,
                document_name=None,
                is_confident=False,
                reasoning="Empty query.",
            )

        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY is not configured for JevMetadataExtractor")

        payload = {
            "model": self.model,
            "state": f"User Query: {query_text}",
            "questions": {
                "category": {
                    "type": "choice",
                    "instructions": (
                        "Classify the citizen inquiry into exactly one of the 10 official government document categories, "
                        "or select 'none' if the query does not clearly focus on one specific category."
                    ),
                    "criteria": CATEGORY_CRITERIA,
                },
                "document_name": {
                    "type": "choice",
                    "instructions": (
                        "Select the specific government document targeted by the query, "
                        "or select 'none' if broad, multi-topic, or not specifically named."
                    ),
                    "criteria": DOCUMENT_CRITERIA,
                },
            },
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        print("\n" + "#" * 80, flush=True)
        print(">>> [JEV METADATA CATEGORY & DOCUMENT FILTER INVOCATION] <<<", flush=True)
        print("#" * 80, flush=True)
        print("\n1. [QUERY SUPPLIED AS STATE TO JEV]:", flush=True)
        print("-" * 80, flush=True)
        print(f"User Query: {query_text}", flush=True)
        print("-" * 80, flush=True)
        print("\n2. [FULL JSON SCHEMA & HTTP REQUEST BODY SENT TO OPENROUTER JEV API]:", flush=True)
        print("-" * 80, flush=True)
        print(json.dumps(payload, indent=2), flush=True)
        print("-" * 80, flush=True)
        print("#" * 80 + "\n", flush=True)

        with httpx.Client(timeout=self.timeout_seconds) as client:
            resp = client.post(
                "https://openrouter.ai/api/alpha/decisions",
                json=payload,
                headers=headers,
            )

        if resp.status_code != 200:
            raise RuntimeError(f"OpenRouter JEV API returned status {resp.status_code}: {resp.text}")

        data = resp.json()
        raw_text = getattr(resp, "text", json.dumps(data))
        answers = data.get("answers", {})

        cat_answer = answers.get("category", {})
        cat_choice = cat_answer.get("choice", "none")
        cat_confidence = float(cat_answer.get("confidence", 0.0))

        doc_answer = answers.get("document_name", {})
        doc_choice = doc_answer.get("choice", "none")
        doc_confidence = float(doc_answer.get("confidence", 0.0))

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Evaluate category confidence
        is_cat_confident = (
            cat_choice != "none"
            and cat_choice in MAJOR_CATEGORIES
            and cat_confidence >= self.confidence_threshold
        )
        matched_category = cat_choice if is_cat_confident else None

        # Evaluate document confidence
        is_doc_confident = (
            doc_choice != "none"
            and doc_choice in DOCUMENT_TO_CATEGORY
            and doc_confidence >= self.confidence_threshold
        )

        matched_document = None
        if is_doc_confident:
            doc_category = DOCUMENT_TO_CATEGORY.get(doc_choice)
            # If category matched or was consistent, confirm document
            if matched_category is None:
                # Infer category from document
                matched_category = doc_category
                is_cat_confident = True
                matched_document = doc_choice
            elif matched_category == doc_category:
                matched_document = doc_choice
            else:
                # Category and document mismatch; keep confident category only
                logger.warning(
                    "[JevMetadataExtractor] Category '%s' and document '%s' (belongs to '%s') mismatched; dropping document filter.",
                    matched_category,
                    doc_choice,
                    doc_category,
                )
                matched_document = None

        is_confident = is_cat_confident or (matched_document is not None)

        print("\n" + "=" * 80, flush=True)
        print(">>> [JEV METADATA CATEGORY & DOCUMENT FILTER OUTPUT & PREDICTION] <<<", flush=True)
        print("-" * 80, flush=True)
        print(f"- RAW API RESPONSE JSON: {raw_text}", flush=True)
        print(f"- PREDICTED CATEGORY:    '{cat_choice}' (confidence: {cat_confidence:.2f})", flush=True)
        print(f"- PREDICTED DOCUMENT:    '{doc_choice}' (confidence: {doc_confidence:.2f})", flush=True)
        print(f"- FILTER CONFIDENT:      {is_confident}", flush=True)
        print(f"- APPLIED CATEGORY:      {matched_category}", flush=True)
        print(f"- APPLIED DOCUMENT:      {matched_document}", flush=True)
        print(f"- PREDICTION LATENCY:    {elapsed_ms:.1f}ms", flush=True)
        print("=" * 80 + "\n", flush=True)

        logger.info(
            "[JevMetadataExtractor] Category='%s' (conf=%.2f), Document='%s' (conf=%.2f) in %.1fms",
            matched_category,
            cat_confidence,
            matched_document,
            doc_confidence,
            elapsed_ms,
        )

        return MetadataFilterDecision(
            category=matched_category,
            document_name=matched_document,
            is_confident=is_confident,
            reasoning=(
                f"JEV classified category='{matched_category}' (score: {cat_confidence:.2f}) "
                f"and document='{matched_document}' (score: {doc_confidence:.2f}) in {elapsed_ms:.1f}ms"
            ),
        )


class MetadataExtractor:
    """Extracts high-confidence category and subcategory filters from queries using JEV or LLM."""

    def __init__(
        self,
        catalog_path: Optional[str] = None,
        llm: Optional[BaseChatModel] = None,
        use_jev: bool = True,
        openrouter_api_key: Optional[str] = None,
        jev_extractor: Optional[JevMetadataExtractor] = None,
    ):
        self._llm = llm
        self.catalog_path = catalog_path or str(Path(__file__).parent / "metadata_catalog.json")
        self.catalog: Dict[str, List[str]] = self._load_catalog(self.catalog_path)
        self._system_prompt = self._build_system_prompt()
        self.use_jev = use_jev

        # Initialize JEV extractor if enabled and no custom LLM was explicitly injected
        if jev_extractor is not None:
            self.jev_extractor: Optional[JevMetadataExtractor] = jev_extractor
        elif self.use_jev and self._llm is None:
            try:
                self.jev_extractor = JevMetadataExtractor(api_key=openrouter_api_key)
            except Exception as exc:
                logger.debug("JevMetadataExtractor initialization skipped: %s", exc)
                self.jev_extractor = None
        else:
            self.jev_extractor = None

    @property
    def model(self) -> str:
        """Return the active model name for observability logging."""
        if self._llm is None and self.use_jev and self.jev_extractor and self.jev_extractor.api_key:
            return getattr(self.jev_extractor, "model", "~typesafe/jev-latest")
        return "gpt-4o-mini"

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
        """Extract metadata filter decision from query, prioritizing JEV for both category and document."""
        query = (query or "").strip()
        if not query or not self.catalog:
            return MetadataFilterDecision(
                category=None,
                document_name=None,
                is_confident=False,
                reasoning="Empty query or empty catalog.",
            )

        # If a custom LLM is provided (e.g. in mock unit tests), bypass JEV directly
        if self._llm is not None or not self.use_jev or self.jev_extractor is None or not self.jev_extractor.api_key:
            return self._extract_with_llm(query)

        # Run JEV for categories and documents with automatic fallback
        try:
            return self.jev_extractor.extract(query)
        except Exception as exc:
            print(
                f"\n\033[93mWARNING:  [JevMetadataExtractor]\033[0m Call failed ({exc}). Falling back to OpenAI LLM.\n",
                flush=True,
            )
            logger.warning("[JevMetadataExtractor] Call failed (%s). Falling back to OpenAI LLM.", exc)
            return self._extract_with_llm(query)

    def _extract_with_llm(self, query: str) -> MetadataFilterDecision:
        """Fallback metadata extraction using OpenAI LLM."""
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
            logger.warning("Metadata extraction fallback failed with error: %s; skipping filter.", exc)
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


__all__ = [
    "CATEGORY_CRITERIA",
    "DOCUMENT_CRITERIA",
    "DOCUMENT_TO_CATEGORY",
    "JevMetadataExtractor",
    "MAJOR_CATEGORIES",
    "MetadataExtractor",
    "MetadataFilterDecision",
]
