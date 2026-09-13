"""Formatting and citation layout utilities for the Context Builder.

WHY THIS MODULE IS SEPARATE FROM builder.py:
The decision of HOW documents appear in the prompt is an independent concern from
WHICH documents are selected and HOW MANY fit within the budget. Separating these
concerns means:

  - Prompt engineers can change the citation format or metadata layout without
    touching the bounding algorithm in builder.py.
  - The formatter can be unit-tested independently for layout correctness.
  - A different formatter (e.g. XML-tagged blocks, JSON-wrapped passages) can be
    injected via ContextBuilder's formatter parameter without changing any other code.

OUTPUT FORMAT:
Each document block is structured as:

    [Document 1]
    Document: income-tax-return-and-related-forms
    Category: income-documents
    Source URL: https://www.incometax.gov.in/...
    Source Type: webpage
    Relevance Score: 0.9400
    Content:
    To relieve small taxpayers from such compliance burden...

The [Document X] label is the citation anchor that links claims in the LLM's
generated response back to a verifiable source chunk.
"""

from typing import Sequence
from app.contracts.retrieval import RetrievedDocument


class DocumentFormatter:
    """Renders document chunks into structured text blocks for LLM prompts."""

    def __init__(
        self,
        delimiter: str = "\n\n---\n\n",
        include_score: bool = True,
        default_empty_message: str = (
            "No relevant government documents were found for this query."
        ),
    ):
        """Initialise the formatter with display preferences.

        WHY THE DELIMITER IS "\\n\\n---\\n\\n":
        The Markdown horizontal rule surrounded by blank lines creates a strong
        token-level separator that signals to the LLM that each block is an
        independent evidence source, not a continuation of the previous passage.

        WHY include_score IS True BY DEFAULT:
        Including the relevance score in the prompt allows the LLM to self-regulate
        the weight it gives to each piece of evidence and makes prompt debugging
        significantly easier.

        Args:
            delimiter: String placed between consecutive document blocks.
            include_score: Whether to display the relevance score in each block.
            default_empty_message: Text returned when the document list is empty.
        """
        self.delimiter = delimiter
        self.include_score = include_score
        self.default_empty_message = default_empty_message

    def format_single_chunk(self, doc: RetrievedDocument, index: int) -> str:
        """Format one document chunk into a citation block with metadata and content.

        HOW THE FORMAT IS ASSEMBLED:
        Header lines are appended only when the corresponding metadata field is
        non-null. This adaptive approach means the format automatically adjusts:
          - A fully-indexed chunk gets: citation label, document name, category,
            source URL, source type, score.
          - A minimal chunk gets: citation label + document name (always present).

        WHY document_name IS PREFERRED OVER document_id:
        document_name is the human-readable title shown to the LLM (e.g.
        "income-tax-return-and-related-forms"). document_id is the internal corpus
        key. The LLM should reason from the human name, not the internal key.
        document_id is shown as a secondary fallback label only.

        WHY "Content:" IS A SEPARATE LABEL:
        Separating the metadata header from the content text with an explicit
        "Content:" label gives the LLM a reliable anchor to locate where the actual
        evidence text begins within each block.

        Args:
            doc: A RetrievedDocument chunk from the retriever.
            index: 1-based citation index matching [Document X] in the prompt.

        Returns:
            A complete formatted string block for this single document chunk.
        """
        header_lines = [f"[Document {index}]"]

        # document_name is required by ChunkMetadata — always present.
        header_lines.append(f"Document: {doc.metadata.document_name.strip()}")

        # category is required by ChunkMetadata — always present.
        header_lines.append(f"Category: {doc.metadata.category.strip()}")

        # source_url is optional — emit only when present.
        if doc.metadata.source_url:
            header_lines.append(f"Source URL: {doc.metadata.source_url.strip()}")

        # source_type is optional (e.g. 'webpage', 'pdf') — emit when present.
        if doc.metadata.source_type:
            header_lines.append(f"Source Type: {doc.metadata.source_type.strip()}")

        # Relevance score — helps the LLM gauge evidence quality.
        if self.include_score and doc.score is not None:
            header_lines.append(f"Relevance Score: {doc.score:.4f}")

        content = (doc.text_content or "").strip()
        metadata_block = "\n".join(header_lines)
        return f"{metadata_block}\nContent:\n{content}"

    def format_all_chunks(self, docs: Sequence[RetrievedDocument]) -> str:
        """Format an ordered sequence of document chunks into one context string.

        ORDERING CONTRACT:
        The caller (ContextBuilder.build_context) must pass chunks in the SAME ORDER
        that citation indexes were assigned when building the ContextSource list.
        Reordering docs between recording sources and calling this method would cause
        [Document X] labels in the formatted text to mismatch ContextSource objects,
        breaking citation verification.

        WHY WE RETURN default_empty_message INSTEAD OF AN EMPTY STRING:
        An empty string leaves the LLM with no signal about why there is no context.
        A clear message gives the LLM the information it needs to produce a helpful
        "I couldn't find that in our documents" response.

        Args:
            docs: Ordered sequence of document chunks to format.

        Returns:
            A single string with all chunks joined by the delimiter,
            or the configured empty message if the sequence is empty.
        """
        if not docs:
            return self.default_empty_message

        formatted_blocks = [
            self.format_single_chunk(doc, idx + 1)
            for idx, doc in enumerate(docs)
        ]
        return self.delimiter.join(formatted_blocks)
