"""Dense Semantic Search adapter for the Retriever Node using ChromaDB and OpenAI text-embedding-3-small."""

import logging
import os
from typing import Any, Dict, List, Optional
import numpy as np
from app.contracts.retrieval import RetrievedDocument
from app.observability import start_observation

logger = logging.getLogger(__name__)


class VectorStoreRetriever:
    """Semantic vector search retriever over RetrievedDocument chunks using Chroma and text-embedding-3-small."""

    def __init__(
        self,
        documents: Optional[List[RetrievedDocument]] = None,
        embeddings_model: Optional[Any] = None,
        collection_name: Optional[str] = None,
        chroma_client: Optional[Any] = None,
    ):
        self.collection_name = collection_name or os.getenv("CHROMA_COLLECTION_NAME", "documents-info")
        self._embeddings_model = embeddings_model
        self._chroma_client = chroma_client
        self._collection: Optional[Any] = None
        self._documents: List[RetrievedDocument] = []
        self._fallback_embeddings: Optional[np.ndarray] = None

        if documents:
            self.index(documents)

    def _get_embeddings_model(self) -> Any:
        """Lazy initialize OpenAIEmbeddings with text-embedding-3-small."""
        if self._embeddings_model is None:
            from langchain_openai import OpenAIEmbeddings

            api_key = os.getenv("OPENAI_API_KEY")
            self._embeddings_model = OpenAIEmbeddings(
                model="text-embedding-3-small",
                api_key=api_key,
            )
        return self._embeddings_model

    def _get_chroma_client(self) -> Optional[Any]:
        """Initialize Chroma CloudClient or in-process Client."""
        if self._chroma_client is not None:
            return self._chroma_client
        try:
            import chromadb

            tenant = os.getenv("CHROMA_TENANT")
            database = os.getenv("CHROMA_DATABASE")
            api_key = os.getenv("CHROMA_API_KEY")

            if tenant and database and api_key:
                logger.info("Connecting to Chroma Cloud (tenant=%s, db=%s)", tenant, database)
                if hasattr(chromadb, "CloudClient"):
                    self._chroma_client = chromadb.CloudClient(
                        tenant=tenant,
                        database=database,
                        api_key=api_key,
                    )
                else:
                    self._chroma_client = chromadb.HttpClient(
                        headers={"x-chroma-token": api_key}
                    )
            else:
                logger.info("Using in-process Chroma Client")
                self._chroma_client = chromadb.Client()

            return self._chroma_client
        except Exception as exc:
            logger.warning(
                "Could not initialize Chroma client (%s); using in-memory vector fallback.",
                exc,
            )
            return None

    def _get_collection(self) -> Optional[Any]:
        if self._collection is not None:
            return self._collection
        client = self._get_chroma_client()
        if client is None:
            return None
        try:
            self._collection = client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            return self._collection
        except Exception as exc:
            logger.warning(
                "Failed to get_or_create_collection '%s': %s",
                self.collection_name,
                exc,
            )
            return None

    def warm_resources(self, *, refresh_count: bool = False) -> bool:
        """Initialize reusable dense retrieval resources before user requests."""
        try:
            self._get_embeddings_model()
            self._get_collection()
            return True
        except Exception as exc:
            logger.warning("Dense retrieval warm-up failed: %s", exc)
            return False

    def index(self, documents: List[RetrievedDocument]) -> None:
        """Index documents into Chroma using text-embedding-3-small embeddings."""
        from guardrails.retrieval import DocumentIngestionGuard

        sanitized_docs, stats = DocumentIngestionGuard().validate_and_sanitize_corpus(list(documents))
        self._documents = sanitized_docs
        if not self._documents:
            return

        try:
            emb_model = self._get_embeddings_model()
            collection = self._get_collection()

            doc_texts = [doc.text_content for doc in self._documents]
            doc_ids = [doc.id for doc in self._documents]
            metadatas = [doc.metadata.model_dump() for doc in self._documents]

            # Generate embeddings via text-embedding-3-small
            embeddings = emb_model.embed_documents(doc_texts)

            if collection is not None:
                collection.upsert(
                    ids=doc_ids,
                    documents=doc_texts,
                    metadatas=metadatas,
                    embeddings=embeddings,
                )
            else:
                # Fallback to local cosine indexing
                raw = np.array(embeddings, dtype=np.float32)
                norms = np.linalg.norm(raw, axis=1, keepdims=True)
                norms[norms == 0] = 1.0
                self._fallback_embeddings = raw / norms

        except Exception as exc:
            logger.warning(
                "Indexing in Chroma with text-embedding-3-small encountered: %s",
                exc,
            )

    def search(
        self,
        query: str,
        top_k: int = 25,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[RetrievedDocument]:
        """Retrieve top_k documents via dense semantic similarity with optional metadata filtering."""
        if not query.strip():
            return []

        try:
            with start_observation(
                "dense_embedding",
                input={"query_length": len(query)},
            ) as embedding_observation:
                emb_model = self._get_embeddings_model()
                query_embedding = emb_model.embed_query(query)
                embedding_observation.update(
                    output={"embedding_dimensions": len(query_embedding)}
                )

            collection = self._get_collection()
            if collection is not None:
                n_res = max(1, top_k)
                query_kwargs: Dict[str, Any] = {
                    "query_embeddings": [query_embedding],
                    "n_results": n_res,
                    "include": ["documents", "metadatas", "distances"],
                }
                if where:
                    query_kwargs["where"] = where

                with start_observation(
                    "dense_chroma_query",
                    input={
                        "top_k": top_k,
                        "n_results": n_res,
                        "filter_applied": where is not None,
                    },
                ) as chroma_observation:
                    results = collection.query(**query_kwargs)
                    chroma_observation.update(
                        output={
                            "result_count": self._chroma_result_count(results),
                            "fallback_needed": self._is_empty_chroma_result(results),
                        }
                    )

                # Zero-recall circuit breaker: if filtered search produced 0 hits, retry unconstrained
                if where and self._is_empty_chroma_result(results):
                    logger.info("Filtered vector search returned 0 results; falling back to unconstrained search.")
                    query_kwargs.pop("where", None)
                    with start_observation(
                        "dense_chroma_fallback_query",
                        input={"top_k": top_k, "n_results": n_res},
                    ) as fallback_observation:
                        results = collection.query(**query_kwargs)
                        fallback_observation.update(
                            output={"result_count": self._chroma_result_count(results)}
                        )

                with start_observation(
                    "dense_result_conversion",
                    input={"raw_result_count": self._chroma_result_count(results)},
                ) as conversion_observation:
                    retrieved = self._documents_from_chroma_results(results)
                    conversion_observation.update(
                        output={"document_count": len(retrieved)}
                    )
                return retrieved

            # In-memory cosine similarity fallback
            if self._fallback_embeddings is not None and self._documents:
                with start_observation(
                    "dense_in_memory_search",
                    input={
                        "top_k": top_k,
                        "document_count": len(self._documents),
                        "filter_applied": where is not None,
                    },
                ) as fallback_observation:
                    documents = self._search_in_memory(query_embedding, top_k, where)
                    fallback_observation.update(
                        output={"document_count": len(documents)}
                    )
                    return documents

        except Exception as exc:
            logger.warning("Vector search encountered error: %s", exc)
            return []

        return []

    @staticmethod
    def _matches_in_memory_where(doc: RetrievedDocument, where: Optional[Dict[str, Any]]) -> bool:
        if not where:
            return True
        meta = doc.metadata.model_dump()
        if "$and" in where:
            return all(meta.get(k) == v for condition in where["$and"] for k, v in condition.items())
        return all(meta.get(k) == v for k, v in where.items())

    @staticmethod
    def _is_empty_chroma_result(results: Any) -> bool:
        return not results or not results.get("ids") or not results["ids"][0]

    @staticmethod
    def _chroma_result_count(results: Any) -> int:
        if not results or not results.get("ids") or not results["ids"]:
            return 0
        return len(results["ids"][0] or [])

    def _documents_from_chroma_results(self, results: Any) -> List[RetrievedDocument]:
        retrieved: List[RetrievedDocument] = []
        if self._is_empty_chroma_result(results):
            return retrieved

        ids = results["ids"][0]
        texts = results["documents"][0] if results.get("documents") else []
        metas = results["metadatas"][0] if results.get("metadatas") else []
        distances = results["distances"][0] if results.get("distances") else []

        for idx in range(len(ids)):
            doc_id = ids[idx]
            text = (
                texts[idx]
                if idx < len(texts) and texts[idx]
                else self._find_text_by_id(doc_id)
            )
            meta = (
                metas[idx]
                if idx < len(metas) and metas[idx]
                else self._find_meta_by_id(doc_id)
            )
            dist = distances[idx] if idx < len(distances) else 0.0
            score = max(0.0, 1.0 - float(dist))

            retrieved.append(
                RetrievedDocument(
                    id=doc_id,
                    text_content=text,
                    metadata=meta,
                    score=score,
                )
            )
        return retrieved

    def _search_in_memory(
        self,
        query_embedding: List[float],
        top_k: int,
        where: Optional[Dict[str, Any]],
    ) -> List[RetrievedDocument]:
        q_emb = np.array(query_embedding, dtype=np.float32)
        q_norm = np.linalg.norm(q_emb)
        if q_norm > 0:
            q_emb = q_emb / q_norm
        sims = np.dot(self._fallback_embeddings, q_emb)
        sorted_indices = np.argsort(sims)[::-1]

        matching_indices = []
        for idx in sorted_indices:
            doc = self._documents[idx]
            if self._matches_in_memory_where(doc, where):
                matching_indices.append(idx)

        if where and not matching_indices:
            matching_indices = list(sorted_indices)

        return [
            self._documents[idx].model_copy(update={"score": float(sims[idx])})
            for idx in matching_indices[:top_k]
        ]

    def get_all_documents(self, limit: Optional[int] = None) -> List[RetrievedDocument]:
        """Fetch all documents directly from Chroma Cloud with pagination to respect quota limits."""
        collection = self._get_collection()
        if collection is None:
            return self._documents

        try:
            total_count = collection.count() if hasattr(collection, "count") else 0
            if total_count == 0:
                return self._documents

            target_total = min(limit, total_count) if limit else total_count
            batch_size = 300  # Chroma Cloud enforces max 300 per Get request
            docs = []

            for offset in range(0, target_total, batch_size):
                current_limit = min(batch_size, target_total - offset)
                batch = collection.get(
                    limit=current_limit,
                    offset=offset,
                    include=["documents", "metadatas"],
                )
                if not batch or not batch.get("ids"):
                    break
                for doc_id, text, meta in zip(batch["ids"], batch.get("documents", []), batch.get("metadatas", [])):
                    docs.append(
                        RetrievedDocument(
                            id=doc_id,
                            text_content=text or "",
                            metadata=meta or {},
                        )
                    )
            return docs
        except Exception as exc:
            logger.warning("Failed to fetch documents from Chroma: %s", exc)
            return self._documents

    def _find_text_by_id(self, doc_id: str) -> str:
        for doc in self._documents:
            if doc.id == doc_id:
                return doc.text_content
        return ""

    def _find_meta_by_id(self, doc_id: str) -> dict:
        for doc in self._documents:
            if doc.id == doc_id:
                return doc.metadata.model_dump()
        return {}


__all__ = ["VectorStoreRetriever"]
