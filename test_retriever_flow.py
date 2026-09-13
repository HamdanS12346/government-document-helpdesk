"""Retriever Flow Demonstration and Test Script.

Tests the full pipeline on the query: 'Procedure to apply for adhaar card'
using the live Chroma Cloud knowledge base ('documents-info') and OpenAI 'text-embedding-3-small',
with hardcoded messages and normalized input.

Stage-by-Stage Output:
1. Query Rewriting (Context Optimization)
2. Dense Semantic Search (Chroma Cloud + text-embedding-3-small) (Top 5)
3. BM25 Lexical Search (Ranked over Chroma Cloud Corpus) (Top 5)
4. Reciprocal Rank Fusion (RRF) (Top 5)
5. Cohere Cross-Encoder Rerank (Top 5)
"""

import os
import sys
from typing import List
from dotenv import load_dotenv

load_dotenv()

from langchain_core.messages import AIMessage, HumanMessage
from app.contracts.intent_decision import IntentDecision
from app.contracts.normalized_input import ImageContent, NormalizedInput
from app.contracts.retrieval import ChunkMetadata, RetrievedDocument
from app.rag.hybrid_fusion import reciprocal_rank_fusion
from app.rag.lexical_search import BM25LexicalSearcher
from app.rag.query_rewriter import QueryRewriter
from app.rag.reranker import CohereReranker
from app.rag.vector_store import VectorStoreRetriever


# ==============================================================================
# Formatting Helper
# ==============================================================================

def display_ranked_documents(stage_name: str, docs: List[RetrievedDocument], score_label: str):
    print("=" * 85)
    print(f"  {stage_name} (Top {len(docs)})")
    print("=" * 85)
    if not docs:
        print("  (No documents retrieved)")
        print()
        return

    for rank, doc in enumerate(docs, start=1):
        score_str = f"{doc.score:.4f}" if doc.score is not None else "N/A"
        print(f"  [{rank}] Chunk ID: {doc.id}")
        print(f"      Document Title : {doc.metadata.document_name} [{doc.metadata.category}]")
        print(f"      Source URL     : {doc.metadata.source_url}")
        print(f"      {score_label:<15}: {score_str}")
        first_line = doc.text_content.strip().split("\n")[0]
        snippet = first_line[:110] + ("..." if len(first_line) > 110 else "")
        print(f"      Snippet        : \"{snippet}\"")
        print("-" * 85)
    print()


# ==============================================================================
# Main Execution Flow
# ==============================================================================

def main():
    print("\n" + "#" * 85)
    print("  RETRIEVER NODE LIVE TEST (Chroma Cloud + text-embedding-3-small + Cohere)")
    print("#" * 85 + "\n")

    # 1. Initialize Semantic Vector Retriever connecting directly to Chroma Cloud
    collection_name = os.getenv("CHROMA_COLLECTION_NAME", "documents-info")
    print(f"Connecting to Chroma Cloud collection: '{collection_name}'...")

    vector_retriever = VectorStoreRetriever(collection_name=collection_name)

    # Fetch corpus from Chroma Cloud to build the BM25 Lexical Index
    print("Fetching document corpus from Chroma Cloud for BM25 lexical indexing...")
    corpus = vector_retriever.get_all_documents()
    print(f"Successfully loaded {len(corpus)} document chunks directly from Chroma Cloud.\n")

    if not corpus:
        print("ERROR: No documents found in Chroma Cloud collection. Please check your credentials or collection.")
        return

    # Initialize BM25 Lexical Searcher over the loaded Chroma corpus
    lexical_searcher = BM25LexicalSearcher(documents=corpus)

    # 2. Hardcoded State Context as requested
    target_query = "Procedure to apply for adhaar card"

    hardcoded_messages = [
        HumanMessage(content="Hello, I want to understand what primary identity cards are issued in India."),
        AIMessage(
            content=(
                "In India, the primary identity documents include the Aadhaar card issued by UIDAI, "
                "the PAN card for income tax, and the Passport for overseas travel. Each serves as proof "
                "of identity and residence."
            )
        ),
    ]

    hardcoded_normalized_input = NormalizedInput(
        user_query=target_query,
        image_content=[
            ImageContent(
                image_name="aadhaar_enrolment_form_front.jpg",
                extracted_text="UIDAI Aadhaar Enrolment / Update Form. Mandatory fields: Full Name, Address, POI, POA.",
                preview="UIDAI Aadhaar Enrolment Form",
            )
        ],
        pdf_content=[],
        combined_text=(
            "User Query:\nProcedure to apply for adhaar card\n\n"
            "Attached Image: aadhaar_enrolment_form_front.jpg\n"
            "Preview: UIDAI Aadhaar Enrolment Form"
        ),
    )

    hardcoded_intent = IntentDecision(
        query=target_query,
        intent_type="document_info",
        confidence_score=0.98,
    )

    conversation_summary = "User inquired about primary Indian identity cards (Aadhaar, PAN, Passport)."

    state = {
        "normalized_input": hardcoded_normalized_input,
        "intent_decision": hardcoded_intent,
        "messages": hardcoded_messages,
        "conversation_summary": conversation_summary,
    }

    print("-" * 85)
    print(f"  TARGET QUERY         : \"{state['normalized_input'].user_query}\"")
    print(f"  INTENT DECISION      : {state['intent_decision'].intent_type} (confidence: {state['intent_decision'].confidence_score})")
    print(f"  CONVERSATION HISTORY : {len(state['messages'])} dialogue turns present")
    print(f"  CONVERSATION SUMMARY : \"{state['conversation_summary']}\"")
    print(f"  ATTACHED MODALITY    : Image '{state['normalized_input'].image_content[0].image_name}' (Preview: '{state['normalized_input'].image_content[0].preview}')")
    print("-" * 85 + "\n")

    # --------------------------------------------------------------------------
    # STAGE 1: Query Rewriting
    # --------------------------------------------------------------------------
    print("=" * 85)
    print("  STAGE 1: Query Rewriting (Context Optimization)")
    print("=" * 85)

    rewriter = QueryRewriter()
    previews = [f"Image {img.image_name}: {img.preview}" for img in hardcoded_normalized_input.image_content]

    rewritten_query = rewriter.rewrite(
        user_query=target_query,
        messages=hardcoded_messages,
        conversation_summary=conversation_summary,
        attachment_previews=previews,
    )

    print(f"  Original Query  : \"{target_query}\"")
    print(f"  Rewritten Query : \"{rewritten_query}\"")
    print("-" * 85 + "\n")

    # --------------------------------------------------------------------------
    # STAGE 2: Dense Semantic Search (Chroma Cloud + text-embedding-3-small) (Top 5)
    # --------------------------------------------------------------------------
    dense_top_5 = vector_retriever.search(query=rewritten_query, top_k=5)
    display_ranked_documents(
        "STAGE 2: Dense Semantic Search (Chroma Cloud + text-embedding-3-small)",
        dense_top_5,
        "Cosine Similarity",
    )

    # --------------------------------------------------------------------------
    # STAGE 3: BM25 Lexical Search (Ranked over Chroma Cloud Corpus) (Top 5)
    # --------------------------------------------------------------------------
    lexical_top_5 = lexical_searcher.search(query=rewritten_query, top_k=5)
    display_ranked_documents(
        "STAGE 3: BM25 Lexical Search (over Chroma Corpus)",
        lexical_top_5,
        "BM25 Score",
    )

    # --------------------------------------------------------------------------
    # STAGE 4: Reciprocal Rank Fusion (RRF) (Top 5)
    # --------------------------------------------------------------------------
    rrf_top_5 = reciprocal_rank_fusion(
        dense_results=dense_top_5,
        lexical_results=lexical_top_5,
        k=60,
        top_n=5,
    )
    display_ranked_documents(
        "STAGE 4: Reciprocal Rank Fusion (RRF) Results",
        rrf_top_5,
        "RRF Score",
    )

    # --------------------------------------------------------------------------
    # STAGE 5: Cohere Cross-Encoder Rerank (Top 5)
    # --------------------------------------------------------------------------
    reranker = CohereReranker()
    final_top_5, applied_fallback = reranker.rerank(
        query=rewritten_query,
        documents=rrf_top_5,
        top_n=5,
    )

    status_str = "FALLBACK USED (RRF Rank Order Preserved)" if applied_fallback else "LIVE COHERE CROSS-ENCODER"
    print(f">> Cohere Reranker Status: {status_str}")
    display_ranked_documents(
        "STAGE 5: Final Reranked Documents",
        final_top_5,
        "Final Score",
    )

    print("#" * 85)
    print("  TEST SUMMARY")
    print(f"  - Input Query              : \"{target_query}\"")
    print(f"  - Rewritten Query          : \"{rewritten_query}\"")
    print(f"  - Chroma Cloud Collection  : \"{collection_name}\" ({len(corpus)} total chunks)")
    print(f"  - Top 1 Document Selected  : \"{final_top_5[0].metadata.document_name}\" ({final_top_5[0].id})")
    print("#" * 85 + "\n")


if __name__ == "__main__":
    main()
