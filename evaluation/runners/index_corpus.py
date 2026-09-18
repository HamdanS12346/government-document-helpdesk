#!/usr/bin/env python
"""Verify Chroma collection connectivity and test corpus loading into RetrieverPipeline.

This script connects to Chroma DB (using the configured environment variables),
fetches all stored `RetrievedDocument` chunks, and registers them into the
pipeline to verify corpus integrity.

Note:
    BM25 lexical search uses an in-memory index. `run_retrieval.py` now
    automatically warms and initializes both Chroma and BM25 inside its own
    process before running evaluation cases. This script serves as a standalone
    diagnostic tool to inspect Chroma connectivity and document counts.
"""

import sys
from pathlib import Path

# Load environment variables (e.g., CHROMA_* and OPENAI_API_KEY)
from dotenv import load_dotenv

repo_root = Path(__file__).resolve().parents[2]
load_dotenv(dotenv_path=repo_root / ".env")

# Ensure the project root is on the import path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Local imports – these live in the repository
from app.rag.node import get_default_retriever_pipeline
from app.rag.vector_store import VectorStoreRetriever
from app.contracts.retrieval import RetrievedDocument


def main() -> int:
    """Fetch all documents from the configured Chroma collection and attach them.

    The function:
    1. Instantiates a temporary `VectorStoreRetriever` to connect to Chroma.
    2. Calls `get_all_documents()` to pull the stored chunks.
    3. Builds the default `RetrieverPipeline`.
    4. Calls `pipeline.set_corpus(documents)` so that subsequent runs use the
       populated vector store.
    """
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    # Step 1 – connect to the vector store
    retriever = VectorStoreRetriever()

    # Step 2 – pull every document currently stored in the collection
    documents: list[RetrievedDocument] = retriever.get_all_documents()
    if not documents:
        print("[WARNING] No documents found in the Chroma collection. "
              "Make sure the collection is populated before running this script.")
        return 1

    print(f"[SUCCESS] Retrieved {len(documents)} documents from the Chroma DB.")

    # Step 3 – create the full retrieval pipeline
    pipeline = get_default_retriever_pipeline()

    # Step 4 – register the corpus – both lexical and vector components are updated
    pipeline.set_corpus(documents)
    print("[SUCCESS] Corpus loaded into RetrieverPipeline. Ready for evaluation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
