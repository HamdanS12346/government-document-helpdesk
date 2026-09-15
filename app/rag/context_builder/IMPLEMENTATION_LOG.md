# Context Builder — Implementation Log

This document is the authoritative reference for everything implemented in the **Context Builder node** (Node 5 in the LangGraph workflow) and the shared contracts it depends on. For each module, every important function is explained with its **exact location**, **what it does**, **why it was designed that way**, and **how the internal mechanics work**.

> **Last updated**: After integration with the Retriever node (Adarsh's PR #5). The `ChunkMetadata` schema, formatter, node, and test structure were updated to match the merged retriever contract.

---

## Position in the Workflow

```text
Retriever (Node 4)
      |
      | writes state["documents"]   →   List[RetrievedDocument]
      v
Context Builder (Node 5)          ← this node
      |
      | writes state["retrieved_context"]   →   RetrievedContext
      v
Response Node (Node 6)
```

The Context Builder sits between retrieval and generation. Its job is to take the raw list of retrieved chunks, normalize and bound them, and produce a clean formatted context string for the LLM.

**State contract (corrected)**:

| Field | Direction | Type |
|---|---|---|
| `state["documents"]` | INPUT (from Retriever) | `List[RetrievedDocument]` |
| `state["retrieved_context"]` | OUTPUT (to Response Node) | `RetrievedContext` |

The context builder reads **only** `state["documents"]`. It reads nothing else from state. An earlier version of `state-flow.md` incorrectly listed additional inputs (`intent_decision`, `normalized_input`, `messages`, `conversation_summary`) — these were removed from `node.py` after the state contract was clarified.

---

## Module Map

```text
app/contracts/
├── retrieval.py      — ChunkMetadata, RetrievedDocument, RetrievalOutput
├── response.py       — ContextSource, RetrievedContext
└── __init__.py       — re-exports all contract classes from both teams

app/rag/context_builder/
├── builder.py        — normalize_retrieved_documents(), ContextBuilder class
├── formatter.py      — DocumentFormatter class
├── node.py           — context_builder_node() LangGraph adapter
└── __init__.py       — public API exports for the package

tests/context-builder/
├── test_contracts.py     — ContextSource, RetrievedContext model tests
├── test_normalization.py — normalize_retrieved_documents tests
├── test_builder.py       — ContextBuilder pipeline tests
├── test_formatter.py     — DocumentFormatter tests
└── test_node.py          — context_builder_node LangGraph adapter tests
```

---

## 1. Shared Contracts (`app/contracts/`)

Contracts are Pydantic models that define the data shapes shared between nodes. They live in `app/contracts/` so any node can import them without creating circular dependencies.

---

### `app/contracts/retrieval.py`

**Role**: Defines the data shapes produced by the Retriever and consumed by the Context Builder. This file is owned jointly — the Retriever team defined the schema, the Context Builder team adapted to it.

---

#### `ChunkMetadata`

```python
class ChunkMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    document_id: str       # required — corpus key, e.g. "income-documents__itr4__india"
    category: str          # required — corpus category, e.g. "income-documents"
    document_name: str     # required — human title, e.g. "income-tax-return-and-related-forms"
    source_url: Optional[str]    # optional — URL for citation rendering
    source_type: Optional[str]   # optional — "webpage", "pdf", etc.
```

**What it is**: Metadata attached to every retrieved chunk. This is the schema the Retriever writes when it indexes the corpus.

**Why `document_id`, `category`, and `document_name` are required**:
The corpus is structured with a consistent naming convention (`category__document_name__region`). Every chunk in the vector store has these three fields populated. Making them required enforces this — a chunk without a document name or category cannot be cited or filtered correctly by category at query time.

**Why `extra="allow"`**:
Government document corpora are heterogeneous. Additional fields (e.g., `department`, `effective_date`, `gazette_number`) may exist for specific document types. `extra="allow"` lets these pass through without requiring a schema change every time a new document type is added.

**Integration note**: The previous version of this schema (before the Retriever PR) had all fields optional (`source_url`, `document_name`, `title`, `page_number`, `section`). After the Retriever PR was merged, the schema was updated to match the actual corpus structure. `title`, `page_number`, and `section` were removed. The formatter was updated accordingly.

---

#### `RetrievedDocument`

```python
class RetrievedDocument(BaseModel):
    id: str                       # required, e.g. "income-documents__itr4__source-005__chunk-0004"
    text_content: str             # required — the actual chunk text
    metadata: ChunkMetadata       # required — corpus metadata
    score: Optional[float]        # optional — Cohere rerank score or RRF score

    @property
    def content(self) -> str: ...      # alias for text_content
    @property
    def source(self) -> Optional[str]: ...  # returns source_url or document_name
```

**What it is**: The core contract for a single retrieved and reranked chunk. This is the unit of work that flows from the Retriever into the Context Builder.

**Why `id` uses a hierarchical naming convention**:
The Retriever names chunks as `{category}__{document_name}__{source}__{chunk_index}`. This makes the ID human-readable for debugging and unique across the entire corpus without a UUID.

**Why `score` is Optional**:
Not all retrieval backends produce a score. The initial BM25-only path or a rule-based retriever may return chunks without a confidence value. Making `score` optional means the contract does not force every retriever to implement Cohere reranking — scoring is a quality feature, not a correctness requirement.

---

#### `RetrievalOutput`

```python
class RetrievalOutput(BaseModel):
    original_query: str
    rewritten_query: str
    documents: List[RetrievedDocument]
    applied_fallback: bool = False
```

**What it is**: A diagnostic wrapper the Retriever can use to return documents alongside query metadata. The Context Builder's `normalize_retrieved_documents` automatically unwraps it.

**Why this exists**: During evaluation and debugging, it is useful to know whether query rewriting changed the query, and whether the Retriever fell back to a simpler strategy. This carries that information alongside the documents without changing the `List[RetrievedDocument]` interface the Context Builder depends on.

---

### `app/contracts/response.py`

**Role**: Defines the data shapes produced by the Context Builder and consumed by the Response Node and Guardrails.

---

#### `ContextSource`

```python
class ContextSource(BaseModel):
    index: int                    # 1-based, matches [Document X] in formatted text
    chunk_id: str                 # ID of the source chunk
    document_name: Optional[str]  # human-readable name for citation rendering
    source_url: Optional[str]     # URL for hyperlink rendering
    score: Optional[float]        # relevance score for Guardrails
```

**What it is**: Structured citation metadata for one chunk included in the context.

**Why `index` must match `[Document X]`**: The formatted context contains labels like `[Document 1]`, `[Document 2]`. The Response Node and Guardrails use `ContextSource.index` to look up which chunk a given `[Document X]` reference corresponds to, enabling hallucination detection — if the LLM cites `[Document 3]` and `sources[2]` exists, the citation is verifiable. If it doesn't, the LLM fabricated it.

---

#### `RetrievedContext`

```python
class RetrievedContext(BaseModel):
    formatted_context: str          # prompt-ready evidence string
    sources: List[ContextSource]    # parallel citation metadata
    total_documents_retrieved: int  # raw count from Retriever
    documents_used: int             # count in context window
    has_relevant_documents: bool    # False → Response Node tells user "nothing found"
    truncated: bool                 # True → some candidates were budget-dropped
    fallback_applied: bool          # True → empty fallback message was used

    @property
    def text(self) -> str: ...      # alias for formatted_context
    def __str__(self) -> str: ...   # returns formatted_context
```

**Why telemetry flags (`truncated`, `fallback_applied`, `has_relevant_documents`)**: These allow the Response Node to adapt its behaviour without re-examining the formatted text:
- `has_relevant_documents=False` → generate a "nothing found" response, do not cite sources.
- `truncated=True` → optionally tell the user that additional documents exist.
- `fallback_applied=True` → log the event and alert if it happens too frequently.

---

## 2. Context Builder Subsystem (`app/rag/context_builder/`)

---

### `app/rag/context_builder/builder.py`

**Role**: All transformation logic — normalization, deduplication, filtering, sorting, budget enforcement, and citation assembly.

---

#### `normalize_retrieved_documents(raw_docs)` — module-level function

**What it does**: Accepts any retriever output format and returns a uniform `List[RetrievedDocument]`.

**Why it exists — the cross-team integration problem**:
The Retriever and Context Builder are owned independently. Different development stages may produce different shapes:
- Native `RetrievedDocument` Pydantic instances (the canonical case).
- Plain Python dicts (common during early integration before the Pydantic model is wired up).
- LangChain `Document` objects (`.page_content`, `.metadata`).
- A `RetrievalOutput` diagnostic container wrapping the document list.

Rather than requiring every Retriever implementation to produce the exact same Python object type, `normalize_retrieved_documents` acts as a **defensive conversion layer at the boundary**.

**The four-case logic**:

| Input shape | How it is handled |
|---|---|
| `None` | Returns `[]` immediately |
| `RetrievalOutput` or dict with `"documents"` key | Unwrapped, inner list is processed |
| `List[RetrievedDocument]` | Passed through directly |
| `List[dict]` | Constructed via key fallbacks: `"text_content"` → `"content"` → `"page_content"` |
| Object with attributes (LangChain etc.) | Extracted via `getattr()` with the same fallback chain |

**Why `(list, tuple)` and not `Sequence`**: Python strings are `Sequence` instances. Iterating a string as a document list would produce individual characters as "documents." The explicit `isinstance(raw_docs, (list, tuple))` check rejects strings immediately.

**Handling missing required fields in fallback paths**:
Because `ChunkMetadata` requires `document_id`, `category`, and `document_name`, the fallback path for arbitrary objects fills in `"unknown"` for all three when the object does not have those attributes. This is preferable to raising a `ValidationError` deep inside a LangGraph graph execution, which would be harder to diagnose.

---

#### `ContextBuilder.__init__(...)` — Constructor

**Why the defaults were chosen**:

| Parameter | Default | Rationale |
|---|---|---|
| `max_context_chars` | `16000` | ~4,000 tokens at ~4 chars/token for English prose |
| `min_relevance_score` | `None` (disabled) | No threshold during development; enable per deployment |
| `deduplicate` | `True` | Hybrid search almost always produces duplicates |
| `sort_by_score` | `True` | Combats the "lost in the middle" LLM attention problem |
| `empty_fallback_message` | Government-specific text | Tells the LLM what to say when retrieval fails |

---

#### `ContextBuilder.deduplicate_documents(docs)` — Two-Layer Deduplication

**Layer 1 — ID-based**: The same chunk ID from both dense vector search and BM25 is caught in O(1) per document.

**Layer 2 — Content hash-based**: Catches re-indexed duplicates and overlapping chunks that have different IDs but identical text.

**How the content hash is computed**:
```python
content_norm = " ".join((doc.text_content or "").split())
content_hash = hashlib.md5(content_norm.encode("utf-8")).hexdigest()
```
`str.split()` collapses all whitespace variants to single spaces, so trivial formatting differences do not cause semantically identical passages to be treated as distinct.

**Important test finding**: During integration, test helpers that gave multiple documents the same default `text_content` string were incorrectly deduplicated to one document. This is correct behaviour — the fix was to ensure each test document has unique text, not to disable deduplication.

---

#### `ContextBuilder.filter_and_sort(docs)` — Score Filtering and Sorting

**Why sort descending ("best first")**: Addresses the **"lost in the middle" problem**. LLMs are more attentive to content at the beginning of their context window. Placing highest-scoring chunks first maximizes the probability that the best evidence drives the generated response.

**Why unscored chunks sort last**: `None` scores map to `float("-inf")` in the sort key. Unscored chunks may be relevant but their relevance cannot be quantified, so scored evidence should always take priority.

**Score threshold is inclusive**: `doc.score < self.min_relevance_score` (strict less-than). A chunk with a score exactly equal to the threshold is included.

---

#### `ContextBuilder.build_context(raw_documents)` — The Main Pipeline

**Six stages in order**:
```
Stage 1: NORMALIZE   — any input format → List[RetrievedDocument]
Stage 2: EMPTY CHECK — if no docs, return fallback context immediately
Stage 3: DEDUPLICATE — remove ID-duplicate and content-duplicate chunks
Stage 4: FILTER+SORT — drop low-score chunks, sort best-first
Stage 5: BUDGET      — include whole chunks until char limit reached
Stage 6: FORMAT+CITE — render text and record ContextSource list
```

**Why whole-chunk inclusion (not mid-chunk slicing) in the main loop**:
Cutting a chunk at a character boundary in the middle would produce partial sentences. A truncated evidence passage about a government regulation could cause the LLM to complete the sentence incorrectly. We include complete chunks or skip them entirely.

**The first-chunk edge case**:
If the very first chunk exceeds the entire budget, we slice `formatted_chunk[:max_context_chars]` and return early with a `truncated=True` result. Zero context is always worse than a slightly truncated first chunk.

---

### `app/rag/context_builder/formatter.py`

**Role**: All text rendering. Converts `RetrievedDocument` objects into prompt-ready Markdown blocks.

---

#### `DocumentFormatter.format_single_chunk(doc, index)` — Per-Chunk Rendering

**Output format** (updated to match Retriever corpus schema):
```
[Document 1]
Document: income-tax-return-and-related-forms
Category: income-documents
Source URL: https://www.incometax.gov.in/iec/foportal/help/e-filing-itr4
Source Type: webpage
Relevance Score: 0.9400
Content:
To relieve small taxpayers from such compliance burden...
```

**What changed from the original design**:
- `document_name` (required) — always emitted since it is now a required field.
- `category` (required) — new addition, always emitted. Useful for the LLM to know the document domain.
- `source_type` (optional) — new addition, emitted when present.
- `title`, `page_number`, `section` — **removed**. These were in the original design but do not exist in the Retriever's corpus schema.

**Why `document_name` is shown instead of `document_id`**:
`document_name` is the human-readable title (`income-tax-return-and-related-forms`). `document_id` is the internal corpus key (`income-documents__income-tax-return-and-related-forms__india`). The LLM should reason from the human name. `document_id` is not shown in the formatted block.

**Why `category` is included**:
Government documents span multiple domains (income, welfare, transport, identity). Including the category in the prompt helps the LLM understand which domain the evidence comes from and avoids conflating tax documents with welfare documents when answering a query that spans categories.

---

#### `DocumentFormatter.format_all_chunks(docs)` — Full Context Assembly

**Why return `default_empty_message` instead of empty string**: An empty string leaves the LLM with no signal about why there is no context. A clear message ("No relevant government documents were found") gives the LLM the information it needs to produce a helpful response rather than hallucinating documents.

---

### `app/rag/context_builder/node.py`

**Role**: The LangGraph integration adapter. Connects the Context Builder logic to the graph state.

---

#### `context_builder_node(state, builder)` — LangGraph Node Function

**State contract (simplified)**:
```python
# reads:
raw_documents = state.get("documents")   # List[RetrievedDocument] from Retriever

# writes:
return {"retrieved_context": retrieved_context}
```

**Why the node was simplified**:
An earlier version read `intent_decision`, `normalized_input`, `messages`, and `conversation_summary` from state. These were added based on an incorrect reading of `state-flow.md`. After clarification, the context builder's contract was confirmed as: **it only receives the documents list and only produces the context string**. All other state fields are read by other nodes. The node was simplified accordingly.

**Why this function is an adapter (not a processor)**:
LangGraph nodes receive the entire state dict. Mixing state-access code with transformation logic would make both harder to test. `ContextBuilder.build_context()` is fully testable without LangGraph. The node only adds the state-access layer.

---

## 3. Test Suite (`tests/context-builder/`)

**74 tests across 5 focused files, all passing.**

Tests are structured to match the Retriever team's convention (`tests/rag/`) — one file per module, plain functions (not classes), realistic corpus data.

| File | What it tests | Count |
|---|---|---|
| `test_contracts.py` | `ContextSource`, `RetrievedContext` model fields, properties, defaults | 6 |
| `test_normalization.py` | `normalize_retrieved_documents` — all input formats, edge cases | 16 |
| `test_builder.py` | `ContextBuilder` — full pipeline, dedup, sort, filter, budget | 26 |
| `test_formatter.py` | `DocumentFormatter` — every rendered field, empty list, delimiter | 16 |
| `test_node.py` | `context_builder_node` — state contract, normal processing, fallbacks | 10 |

**Why tests use unique text content per document**:
The deduplication stage uses content-hash deduplication. Test helpers that give multiple documents identical default text would correctly deduplicate them to one document, making multi-document tests appear to fail. Every test document uses distinct text.

**Using realistic corpus data**:
All test fixtures use real corpus naming conventions (`income-documents__itr4__india`, `gst-docs__registration__india`) rather than generic placeholders (`chunk-001`, `doc-1`). This makes test failures immediately point to the relevant document type.

---

## 4. Verification

```powershell
.\venv\Scripts\pytest tests\context-builder\ -v
```

**Result**: `74 passed in 3.51s` — zero failures, zero warnings.

---

## 5. Known Limitations and Follow-Up Work

| Item | Priority | Description |
|---|---|---|
| Config-driven builder defaults | High | `max_context_chars` and `min_relevance_score` should come from `app/config/` settings |
| `HelpdeskState` TypedDict | High | All node functions use `Dict[str, Any]`; a typed state schema should be defined in `app/graph/state.py` |
| Graph registration | High | `context_builder_node` is not yet wired into `app/graph/graph.py` |
| End-to-end integration test | Medium | A test feeding real Retriever output through the Context Builder is needed once the graph is wired |
