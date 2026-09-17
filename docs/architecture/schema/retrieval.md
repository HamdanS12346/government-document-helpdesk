# Retrieval Schema

## Overview

`documents` in the LangGraph shared `State` stores the list of retrieved and reranked document chunks produced by the Retriever Node.

The Retriever performs multi-turn query rewriting, dual hybrid search (dense vector + BM25 lexical), Reciprocal Rank Fusion (RRF), and Cohere reranking before returning chunks conforming to this schema.

The Context Builder Node consumes this list to construct grounded, bounded context for answer generation and source attribution.

The Retriever also writes `retrieval_status`, which records whether retrieval
completed successfully, found no matching documents, partially failed, or failed
before a reliable search could be completed.

Current default relevance thresholds:

- Dense/vector candidates must have `score > 0`.
- BM25 lexical candidates must have `score >= 8`.
- Cohere-reranked final candidates must have `score > 0.2`.

The reranker threshold is applied only when the reranker produced comparable
relevance scores. It is not applied to fallback ranking scores.

---

## Schema

```text
RetrievedDocument
├── id: str
├── text_content: str
├── metadata: ChunkMetadata
│   ├── document_id: str
│   ├── category: str
│   ├── document_name: str
│   ├── source_url: Optional[str]
│   └── source_type: Optional[str]
└── score: Optional[float]
```

### `id`

```text
id: str
```

The unique identifier of the specific chunk within the knowledge base.

Example:
```text
"income-documents__income-tax-return-and-related-forms__india__source-005__chunk-0004"
```

---

### `text_content`

```text
text_content: str
```

The primary textual content of the chunk retrieved from the government document knowledge base.

---

### `metadata`

```text
metadata: ChunkMetadata
```

Structured provenance and classification metadata associated with the chunk.

#### `ChunkMetadata` Fields

| Field | Type | Description | Example |
| :--- | :--- | :--- | :--- |
| `document_id` | `str` | Parent document identifier | `"income-documents__income-tax-return-and-related-forms__india"` |
| `category` | `str` | Broad category or domain | `"income-documents"` |
| `document_name` | `str` | Official name or title | `"income-tax-return-and-related-forms"` |
| `source_url` | `Optional[str]` | Link to official government source | `"https://www.incometax.gov.in/iec/foportal/..."` |
| `source_type` | `Optional[str]` | Format of the source | `"webpage"`, `"pdf"`, `"gazette"` |

`ChunkMetadata` is extensible (`extra="allow"`) to support domain-specific fields such as `page_number`, `section`, or `form_code` when available.

---

### `score`

```text
score: Optional[float]
```

The relevance score assigned to the chunk after reranking (via Cohere Rerank or Reciprocal Rank Fusion fallback). Higher scores indicate greater relevance to the user's query.

---

## Retrieval Status

```text
RetrievalStatus
|-- status: success | no_documents_found | partial_failure | failed | blocked_by_guardrail
|-- errors: List[RetrievalError]
|-- dense_result_count: int
|-- lexical_result_count: int
|-- final_document_count: int
`-- no_documents_found: bool
```

`no_documents_found` means dense and lexical retrieval completed without service
errors, but no usable document chunks were returned after fusion/reranking.

`failed` means retrieval could not complete because a required retrieval service
failed, such as OpenAI embeddings or Chroma querying. This must not be shown to
users as "no relevant documents were found."

`partial_failure` means at least one retrieval path failed, but another path
still returned usable document chunks.

---

## Example

```json
{
  "id": "income-documents__income-tax-return-and-related-forms__india__source-005__chunk-0004",
  "text_content": "To relieve small taxpayers from such compliance burden, the Income Tax Act has framed the presumptive taxation scheme u/s 44AD, 44ADA and 44AE. A person adopting the presumptive taxation scheme can declare income at a prescribed rate...",
  "metadata": {
    "document_id": "income-documents__income-tax-return-and-related-forms__india",
    "category": "income-documents",
    "document_name": "income-tax-return-and-related-forms",
    "source_url": "https://www.incometax.gov.in/iec/foportal/help/e-filing-itr4-form-sugam-faq",
    "source_type": "webpage"
  },
  "score": 0.942
}
```

---

## Role in the Workflow

```text
Retriever
    |
    | writes
    v
documents: List[RetrievedDocument]
retrieval_status: RetrievalStatus
    |
    v
Context Builder
    |
    | constructs bounded context & citations
    v
retrieved_context
    |
    v
Response Node
```
