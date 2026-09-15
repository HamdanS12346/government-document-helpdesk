"""Core context building engine for the Context Builder node.

This module provides the ContextBuilder class, responsible for:
1. Normalizing raw documents from the Retriever into shared contract models.
2. Deduplicating overlapping chunks (by ID and by content hash).
3. Sorting and filtering by relevance score.
4. Enforcing a character-based context budget to prevent LLM context-window overflow.
5. Extracting structured citation metadata (ContextSource list).
6. Generating the final RetrievedContext object for the Response node.

Design principle: this module contains pure transformation logic with no I/O or LLM
calls. All LangGraph wiring is in node.py. All text rendering is in formatter.py.
"""

import hashlib
import logging
from typing import Any, List, Optional, Set

from pydantic import BaseModel

from app.contracts.retrieval import (
    ChunkMetadata,
    RetrievedDocument,
    RetrievalOutput,
)
from app.contracts.response import (
    ContextSource,
    RetrievedContext,
)
from app.rag.context_builder.formatter import DocumentFormatter

# Module-level logger — allows operators to set log level per module via logging config.
logger = logging.getLogger(__name__)


def normalize_retrieved_documents(raw_docs: Any) -> List[RetrievedDocument]:
    """Convert raw retriever outputs into a uniform list of RetrievedDocument instances.

    WHY THIS EXISTS:
    The Retriever node can be implemented by different team members using different
    retrieval backends (LangChain, raw ChromaDB, custom wrappers, mock fixtures).
    Each may return documents in a slightly different shape:

      • Native RetrievedDocument Pydantic models — ideal case, from a well-integrated retriever.
      • Plain Python dicts — common when the retriever uses JSON serialization or a
        raw ChromaDB/FAISS response dict.
      • LangChain Document objects — with .page_content and .metadata attributes,
        used when the retriever is built on top of a LangChain vector store.
      • A RetrievalOutput diagnostic container — wraps the list of documents along
        with query metadata (original query, rewritten query, fallback flag).

    Rather than requiring every retriever to produce the exact same Python object
    (which would be brittle and would break cross-team integration), this function
    acts as a defensive normalization layer. It accepts any of the above formats
    and always produces a clean List[RetrievedDocument] that downstream logic
    can depend on unconditionally.

    PROCESSING ORDER:
      1. If the input is a container (RetrievalOutput or a dict with a "documents" key),
         unwrap it to get the inner list.
      2. Guard against non-list/tuple inputs. We check only for list and tuple — NOT
         the broader Sequence ABC — because strings are also Sequence instances, and
         iterating a string character-by-character as documents would cause cryptic
         downstream failures.
      3. For each item in the list:
           a. If it is already a RetrievedDocument → pass through directly.
           b. If it is a dict → construct via explicit key lookup with fallbacks.
           c. Otherwise → use getattr duck-typing (handles LangChain Document etc.).
      4. Skip None items silently.

    Args:
        raw_docs: Any retriever output — RetrievedDocument list, dicts, LangChain
                  Documents, RetrievalOutput container, or None.

    Returns:
        A uniform list of RetrievedDocument instances. Returns [] if input is
        None, empty, or of an unsupported type.
    """
    if raw_docs is None:
        return []

    # ── Step 1: Unwrap container objects ─────────────────────────────────────
    # RetrievalOutput is a Pydantic diagnostic wrapper that carries the document
    # list plus query metadata. A plain dict with a "documents" key is a
    # JSON-serialized version of the same wrapper. In both cases, we extract the
    # inner document list and process it identically to a bare list input.
    if hasattr(raw_docs, "documents") and isinstance(raw_docs.documents, (list, tuple)):
        raw_docs = raw_docs.documents
    elif (
        isinstance(raw_docs, dict)
        and "documents" in raw_docs
        and isinstance(raw_docs["documents"], (list, tuple))
    ):
        raw_docs = raw_docs["documents"]

    # ── Step 2: Guard against non-list/tuple types ───────────────────────────
    # We use (list, tuple) explicitly instead of the Sequence ABC because strings
    # are valid Sequence instances — passing a string would iterate characters, not
    # documents. This explicit check is the safer defensive boundary.
    if not isinstance(raw_docs, (list, tuple)):
        logger.warning(
            "normalize_retrieved_documents: received unsupported type '%s'. Returning [].",
            type(raw_docs).__name__,
        )
        return []

    normalized: List[RetrievedDocument] = []
    for idx, doc in enumerate(raw_docs):
        if doc is None:
            continue

        # ── Case 1: Already a RetrievedDocument ──────────────────────────────
        # Most common in a well-integrated system where the Retriever already
        # uses the shared contract. No transformation needed — pass through directly.
        if isinstance(doc, RetrievedDocument):
            normalized.append(doc)
            continue

        # ── Case 2: Plain dict ────────────────────────────────────────────────
        # Dicts may use "text_content", "content", or "page_content" as the text
        # key, depending on which backend produced them. We try all three in order
        # of preference: our own schema first, then LangChain conventions.
        if isinstance(doc, dict):
            chunk_id = str(doc.get("id") or f"doc-chunk-{idx + 1:04d}")
            text_content = str(
                doc.get("text_content")
                or doc.get("content")
                or doc.get("page_content")
                or ""
            )
            raw_meta = doc.get("metadata") or {}
            if not isinstance(raw_meta, dict):
                raw_meta = {}
            score = doc.get("score")
            try:
                score = float(score) if score is not None else None
            except (ValueError, TypeError):
                score = None

            metadata = ChunkMetadata(**raw_meta)
            normalized.append(
                RetrievedDocument(
                    id=chunk_id,
                    text_content=text_content,
                    metadata=metadata,
                    score=score,
                )
            )
            continue

        # ── Case 3: Object with attributes (LangChain Document, custom model) ─
        # LangChain Documents use .page_content for text and .metadata for a dict.
        # We use getattr with fallback chains to handle attribute name variations.
        chunk_id = getattr(doc, "id", None) or f"doc-chunk-{idx + 1:04d}"
        text_content = (
            getattr(doc, "text_content", None)
            or getattr(doc, "content", None)
            or getattr(doc, "page_content", None)
            or ""
        )
        raw_meta = getattr(doc, "metadata", None)

        # Metadata can itself be a dict, a Pydantic model, or an arbitrary object.
        # We normalize each case into a ChunkMetadata instance.
        # ChunkMetadata requires document_id, category, and document_name.
        if isinstance(raw_meta, dict):
            metadata = ChunkMetadata(**raw_meta)
        elif isinstance(raw_meta, BaseModel):
            # Pydantic model — dump to dict first so we can pass kwargs cleanly.
            metadata = ChunkMetadata(**raw_meta.model_dump())
        elif raw_meta is not None:
            # Arbitrary object — extract ChunkMetadata fields via getattr.
            metadata = ChunkMetadata(
                document_id=getattr(raw_meta, "document_id", "unknown"),
                category=getattr(raw_meta, "category", "unknown"),
                document_name=getattr(raw_meta, "document_name", "unknown"),
                source_url=getattr(raw_meta, "source_url", None),
                source_type=getattr(raw_meta, "source_type", None),
            )
        else:
            metadata = ChunkMetadata(
                document_id="unknown",
                category="unknown",
                document_name="unknown",
            )

        score = getattr(doc, "score", None)
        try:
            score = float(score) if score is not None else None
        except (ValueError, TypeError):
            score = None

        normalized.append(
            RetrievedDocument(
                id=str(chunk_id),
                text_content=str(text_content),
                metadata=metadata,
                score=score,
            )
        )

    logger.debug(
        "normalize_retrieved_documents: converted %d item(s) to RetrievedDocument.",
        len(normalized),
    )
    return normalized


class ContextBuilder:
    """Orchestrates retrieval normalization, deduplication, bounding, and formatting.

    This class implements the full context-building pipeline:
      normalize → deduplicate → filter/sort → budget → format → cite

    It is stateless between calls — all configuration is fixed at construction time
    and build_context() is a pure transformation with no side effects.
    """

    def __init__(
        self,
        max_context_chars: int = 16000,
        min_relevance_score: Optional[float] = None,
        deduplicate: bool = True,
        sort_by_score: bool = True,
        formatter: Optional[DocumentFormatter] = None,
        empty_fallback_message: str = "No relevant government documents were found for this query.",
    ):
        """Initialize the ContextBuilder engine.

        WHY EACH PARAMETER:

        max_context_chars (default 16,000):
            Limits how many characters of document text are placed into the LLM prompt.
            At approximately 4 characters per token for English text, 16,000 characters
            is roughly 4,000 tokens. This leaves room for the system prompt, conversation
            history, and the model's generated response within a typical 8K–16K token
            context window.
            Reduce this value if you need to accommodate longer conversation histories
            or a larger system prompt in the same context window.

        min_relevance_score (default None — threshold disabled):
            When set, chunks with a relevance score strictly below this threshold are
            discarded before context assembly. This prevents low-quality or tangential
            passages from consuming the context budget. A typical starting threshold for
            cosine similarity scores is 0.70. Leave as None when using a reranker that
            already guarantees top-k quality, or during development when you want to
            inspect all retrieved chunks regardless of score.

        deduplicate (default True):
            Hybrid search (dense vector retrieval + BM25 keyword retrieval) commonly
            returns the same text chunk from two different retrieval paths with
            different or identical IDs. Including duplicates wastes context budget
            and can cause the LLM to over-weight repeated evidence. Deduplication
            is almost always the right choice.

        sort_by_score (default True):
            Research on LLM attention patterns documents a phenomenon called the
            "lost in the middle" problem: language models tend to underweight evidence
            that appears in the middle of a long context, focusing more on content
            near the beginning and end. Sorting the highest-scoring chunks to the
            beginning of the formatted context maximizes the probability that the
            most relevant evidence is used in the response.

        formatter (default None → DocumentFormatter()):
            Allows injecting a custom formatter for testing or for producing a
            different citation style (e.g., XML-tagged for Claude, JSON for
            function-calling models). The default DocumentFormatter uses a
            Markdown-style layout that works well with GPT-4 class models.

        empty_fallback_message:
            The message placed in formatted_context when no valid documents are
            available after all pipeline stages. The Response Node will receive
            this string as its context. It should be clear and human-readable so
            that the LLM can inform the user accordingly.

        Args:
            max_context_chars: Maximum total characters allowed in formatted_context.
            min_relevance_score: Optional minimum score for chunk inclusion.
            deduplicate: Whether to remove duplicate chunks by ID and content hash.
            sort_by_score: Whether to sort chunks descending by relevance score.
            formatter: Optional custom DocumentFormatter instance.
            empty_fallback_message: Fallback text when no documents are available.
        """
        self.max_context_chars = max_context_chars
        self.min_relevance_score = min_relevance_score
        self.deduplicate = deduplicate
        self.sort_by_score = sort_by_score
        self.empty_fallback_message = empty_fallback_message
        self.formatter = formatter or DocumentFormatter(
            default_empty_message=empty_fallback_message
        )

    def deduplicate_documents(
        self,
        docs: List[RetrievedDocument],
    ) -> List[RetrievedDocument]:
        """Remove duplicate chunks using a two-layer deduplication strategy.

        WHY TWO LAYERS:
        Hybrid search pipelines can introduce duplicates in two distinct ways:

          Layer 1 — ID-based dedup:
            The same chunk (same ID) can be returned by both the dense vector
            retriever and the BM25 keyword retriever in a hybrid search setup.
            Checking IDs catches this case in O(1) per document.

          Layer 2 — Content hash dedup:
            A document corpus may have the same text indexed under different IDs
            (e.g., a re-indexed corpus, or a chunk that appears in multiple
            sections with different metadata). ID-based dedup would miss these.
            We compute an MD5 hash of the normalized text content to catch
            content-identical chunks regardless of their ID.

        WHY MD5 AND NOT SHA-256:
        MD5 is faster and produces shorter hashes than SHA-256. Since we are using
        it purely for deduplication collision-resistance (not security), MD5 is the
        appropriate choice. The probability of a false-positive collision in a
        typical retrieval result set (5–20 chunks) is negligible.

        WHY WHITESPACE NORMALIZATION BEFORE HASHING:
        Minor formatting differences between retrieval backends (e.g., different
        numbers of spaces, line endings) should not cause two identical passages to
        be treated as distinct. We collapse all whitespace to single spaces before
        hashing, making the comparison robust to such variations.

        ORDERING GUARANTEE:
        The first occurrence in the input list is always preserved. Since the
        input list will subsequently be sorted by score (in filter_and_sort),
        the preserved duplicate will be the one with the highest score.

        Args:
            docs: List of normalized document chunks, possibly containing duplicates.

        Returns:
            Deduplicated list preserving only the first occurrence of each unique chunk.
        """
        seen_ids: Set[str] = set()
        seen_hashes: Set[str] = set()
        unique_docs: List[RetrievedDocument] = []

        for doc in docs:
            # Layer 1: Check chunk ID uniqueness
            if doc.id and doc.id in seen_ids:
                logger.debug("Deduplication: skipping duplicate ID '%s'.", doc.id)
                continue

            # Layer 2: Check content uniqueness via normalized MD5 hash.
            # ".split()" on a string splits on any whitespace (spaces, tabs, newlines)
            # and " ".join() reassembles with single spaces — a simple normalization.
            content_norm = " ".join((doc.text_content or "").split())
            content_hash = hashlib.md5(content_norm.encode("utf-8")).hexdigest()  # nosec (not crypto)
            if content_hash in seen_hashes:
                logger.debug(
                    "Deduplication: skipping content-duplicate for chunk ID '%s'.", doc.id
                )
                continue

            if doc.id:
                seen_ids.add(doc.id)
            seen_hashes.add(content_hash)
            unique_docs.append(doc)

        logger.debug(
            "deduplicate_documents: %d → %d chunks (%d duplicate(s) removed).",
            len(docs),
            len(unique_docs),
            len(docs) - len(unique_docs),
        )
        return unique_docs

    def filter_and_sort(
        self,
        docs: List[RetrievedDocument],
    ) -> List[RetrievedDocument]:
        """Filter out low-relevance chunks and sort by descending score.

        WHY FILTER BEFORE SORT:
        Filtering first reduces the list size before sorting, which is more efficient.
        More importantly, it guarantees that chunks below the quality threshold cannot
        appear at the top of the sorted list if score values happen to be close to the
        threshold boundary.

        WHY SORT DESCENDING BY SCORE ("best first"):
        This directly addresses the "lost in the middle" problem in LLM attention.
        The LLM is most likely to use evidence it encounters at the beginning of
        a long context. By placing the highest-scoring (most relevant) chunks first,
        we maximize the probability that the best evidence drives the response.

        WHY UNSCORED CHUNKS SORT LAST:
        Chunks without a relevance score (score=None) come from retrievers that do
        not produce a confidence value. They may be relevant or they may not be.
        Placing them after all scored chunks ensures that evidence with a quantified
        relevance score always takes priority over unquantified evidence.

        NOTE ON SCORE THRESHOLD BOUNDARY:
        The filter uses a strict less-than comparison (doc.score < threshold), which
        means a chunk with score exactly equal to min_relevance_score is INCLUDED.
        This is intentional — the threshold is a minimum acceptable score, not an
        exclusive lower bound.

        Args:
            docs: List of document chunks to filter and sort.

        Returns:
            Filtered and sorted document chunks, most relevant first.
        """
        filtered_docs: List[RetrievedDocument] = []
        skipped_count = 0

        # Step 1: Apply minimum relevance score threshold if configured
        for doc in docs:
            if self.min_relevance_score is not None and doc.score is not None:
                if doc.score < self.min_relevance_score:
                    logger.debug(
                        "filter_and_sort: dropping chunk '%s' (score=%.4f < threshold=%.4f).",
                        doc.id,
                        doc.score,
                        self.min_relevance_score,
                    )
                    skipped_count += 1
                    continue
            filtered_docs.append(doc)

        # Step 2: Sort descending by relevance score if sorting is enabled.
        # float("-inf") as the sort key for None-scored chunks places them at the end.
        if self.sort_by_score:
            def sort_key(d: RetrievedDocument) -> float:
                return d.score if d.score is not None else float("-inf")

            filtered_docs.sort(key=sort_key, reverse=True)

        logger.debug(
            "filter_and_sort: %d in → %d passed filter, %d dropped by threshold.",
            len(docs),
            len(filtered_docs),
            skipped_count,
        )
        return filtered_docs

    def build_context(self, raw_documents: Any) -> RetrievedContext:
        """Transform raw retrieval outputs into a bounded, formatted RetrievedContext.

        THIS IS THE MAIN PIPELINE. It orchestrates all six stages:

          1. NORMALIZE   — convert any input format to List[RetrievedDocument]
          2. EMPTY CHECK — if nothing to process, return a fallback context immediately
          3. DEDUPLICATE — remove chunks that share an ID or have identical text
          4. FILTER+SORT — drop chunks below the score threshold, sort best-first
          5. BUDGET      — walk through candidates, include whole chunks until the
                          character limit is reached
          6. FORMAT+CITE — render included chunks as a prompt-ready string and build
                          the parallel ContextSource citation list

        WHY WHOLE-CHUNK BOUNDING (not mid-chunk truncation within the main loop):
        We include complete chunks or skip them entirely. Cutting a chunk mid-sentence
        would produce partial evidence that could mislead the LLM into making
        incomplete or incorrect citations. The only exception is the edge case where
        the very first chunk alone exceeds the entire budget — in that case we slice
        the formatted text to the character limit and return early, because returning
        an empty context would be worse than a slightly truncated first chunk.

        WHY STRUCTURED CITATION METADATA (the ContextSource list):
        Each chunk included in formatted_context is paired with a ContextSource object
        that records its [Document X] index, chunk ID, document name, source URL, and
        relevance score. This parallel structure allows:
          • The Response Node to render source links and document names in the final answer.
          • Guardrails to verify that LLM-generated citations correspond to real chunks.
          • Hallucination detection by cross-referencing LLM output against source content.
          • Evaluation pipelines to measure retrieval precision end-to-end.

        WHY total_documents_retrieved IS CAPTURED BEFORE DEDUPLICATION:
        This field represents the raw output count from the Retriever node — i.e., how
        many documents the retrieval system actually returned. Capturing it before
        deduplication ensures it is an accurate upstream metric, not inflated by our
        own processing choices. Downstream telemetry can use it to compute the
        deduplication ratio and the filtering ratio independently.

        Args:
            raw_documents: Raw retriever output in any supported format
                           (see normalize_retrieved_documents for accepted types).

        Returns:
            RetrievedContext with formatted prompt text, structured citations,
            and telemetry flags (has_relevant_documents, truncated, fallback_applied).
        """

        # ── Stage 1: Normalize ───────────────────────────────────────────────
        docs = normalize_retrieved_documents(raw_documents)

        # Capture the raw retrieval count BEFORE any of our own processing stages.
        # This is the true number of documents the Retriever returned to us.
        total_retrieved = len(docs)

        # ── Stage 2: Empty input → immediate fallback ────────────────────────
        if not docs:
            logger.info(
                "build_context: no documents after normalization. Returning fallback context."
            )
            return RetrievedContext(
                formatted_context=self.empty_fallback_message,
                sources=[],
                total_documents_retrieved=0,
                documents_used=0,
                has_relevant_documents=False,
                truncated=False,
                fallback_applied=True,
            )

        # ── Stage 3: Deduplicate ─────────────────────────────────────────────
        if self.deduplicate:
            docs = self.deduplicate_documents(docs)

        # ── Stage 4: Filter and sort ─────────────────────────────────────────
        docs = self.filter_and_sort(docs)

        # If score filtering eliminated everything, return a clear fallback.
        if not docs:
            logger.info(
                "build_context: all %d document(s) dropped by score filter. "
                "Returning fallback context.",
                total_retrieved,
            )
            return RetrievedContext(
                formatted_context=self.empty_fallback_message,
                sources=[],
                total_documents_retrieved=total_retrieved,
                documents_used=0,
                has_relevant_documents=False,
                truncated=False,
                fallback_applied=True,
            )

        # ── Stage 5: Budget enforcement ──────────────────────────────────────
        # Walk through candidates from highest to lowest score.
        # We compute the formatted length of each candidate before including it,
        # so we can stop cleanly before exceeding the budget.
        included_docs: List[RetrievedDocument] = []
        sources: List[ContextSource] = []
        current_char_count = 0
        truncated = False

        # Pre-measure the delimiter length once — it is added between chunks.
        delimiter_len = len(self.formatter.delimiter)

        for idx, doc in enumerate(docs):
            # citation_index is 1-based and matches [Document X] in the formatted text.
            citation_index = idx + 1
            formatted_chunk = self.formatter.format_single_chunk(doc, citation_index)

            # First chunk has no leading delimiter; subsequent chunks do.
            added_len = len(formatted_chunk) + (delimiter_len if included_docs else 0)

            if current_char_count + added_len > self.max_context_chars:
                if included_docs:
                    # We already have at least one chunk in the context.
                    # Stop here cleanly — never include a partial chunk in the middle.
                    # The LLM will work with the complete chunks we have included so far.
                    truncated = True
                    logger.info(
                        "build_context: budget reached after %d chunk(s) (%d chars). "
                        "%d candidate(s) not included.",
                        len(included_docs),
                        current_char_count,
                        len(docs) - len(included_docs),
                    )
                    break
                else:
                    # Edge case: the very first (and only so far) chunk alone exceeds
                    # the entire character budget. Returning empty context would be
                    # unhelpful, so we slice the formatted text to the budget limit
                    # and return early with a single-source citation.
                    #
                    # Note: slicing formatted_chunk may cut the text mid-word, but
                    # this is acceptable here because the alternative — returning
                    # zero context — is always worse for the user experience.
                    truncated = True
                    sliced_text = formatted_chunk[: self.max_context_chars]
                    source = ContextSource(
                        index=citation_index,
                        chunk_id=doc.id,
                        document_name=doc.metadata.document_name,
                        source_url=doc.metadata.source_url,
                        score=doc.score,
                    )
                    logger.warning(
                        "build_context: first chunk '%s' (%d chars) exceeds budget "
                        "(%d chars). Returning sliced context.",
                        doc.id,
                        len(formatted_chunk),
                        self.max_context_chars,
                    )
                    return RetrievedContext(
                        formatted_context=sliced_text,
                        sources=[source],
                        total_documents_retrieved=total_retrieved,
                        documents_used=1,
                        has_relevant_documents=True,
                        truncated=True,
                        fallback_applied=False,
                    )

            included_docs.append(doc)
            current_char_count += added_len

            # Record citation metadata matching the [Document X] index used in the
            # formatted text. The Response Node uses this list to build verifiable
            # source references in the final user-facing answer.
            sources.append(
                ContextSource(
                    index=citation_index,
                    chunk_id=doc.id,
                    document_name=doc.metadata.document_name,
                    source_url=doc.metadata.source_url,
                    score=doc.score,
                )
            )

        # Catch the case where the loop completed without breaking but not all docs fit.
        if len(included_docs) < len(docs) and not truncated:
            truncated = True

        # ── Stage 6: Format all included chunks into one prompt-ready string ──
        formatted_context = self.formatter.format_all_chunks(included_docs)

        logger.info(
            "build_context: complete — retrieved=%d, used=%d, truncated=%s, chars=%d.",
            total_retrieved,
            len(included_docs),
            truncated,
            len(formatted_context),
        )

        return RetrievedContext(
            formatted_context=formatted_context,
            sources=sources,
            total_documents_retrieved=total_retrieved,
            documents_used=len(included_docs),
            has_relevant_documents=True,
            truncated=truncated,
            fallback_applied=False,
        )
