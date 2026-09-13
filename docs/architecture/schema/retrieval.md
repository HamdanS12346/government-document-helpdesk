# Retrieval Schema

## Overview

`documents` in the LangGraph shared `State` stores the list of retrieved and reranked document chunks produced by the Retriever Node.

The Retriever performs multi-turn query rewriting, dual hybrid search (dense vector + BM25 lexical), Reciprocal Rank Fusion (RRF), and Cohere reranking before returning chunks conforming to this schema.

The Context Builder Node consumes this list to construct grounded, bounded context for answer generation and source attribution.

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
