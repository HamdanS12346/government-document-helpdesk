# Hybrid Retrieval Architecture and Latency Analysis

## 1. Overall retrieval flow

This project uses the following pipeline:

```text
User query
   ↓
Intent classification
   ↓
Query optimization
   ↓
Metadata extraction and normalization
   ↓
                    ┌───────────────┐
                    │               │
                    ▼               ▼
              Dense retrieval   Sparse retrieval
                Chroma          BM25
                    │               │
                    └───────┬───────┘
                            ▼
                         RRF fusion
                            ▼
                    Cohere reranking
                            ▼
                      Final Node[]
                            ▼
                     Context builder
```

The final application contract remains:

```python
list[Node]
```

The downstream graph and context builder do not need to know whether a result came from dense retrieval, BM25, RRF, or Cohere.

---

# 2. Query preparation

Before retrieval starts, the application performs:

1. Intent classification
2. Query extraction
3. Optional query optimization
4. Metadata extraction
5. Metadata normalization

For example:

```text
User query:
"How does the two sum problem work?"

Optimized query:
"How does the two sum problem work"
```

For a follow-up query:

```text
Previous context:
The user was discussing Two Sum.

User query:
"What is its complexity?"

Optimized query:
"Two Sum time complexity"
```

The optimized query is passed to dense retrieval, sparse retrieval, RRF diagnostics, and Cohere reranking.

Important latency point:

- Intent classification is an LLM/API call.
- Query optimization is another LLM/API call.
- Metadata extraction may be another LLM/API call.

These calls happen before the actual retriever and can contribute significant latency.

If there is no conversation context, query optimization may still execute because the node receives the optimizer dependency. Therefore, the system should measure whether optimization is actually necessary before calling an LLM.

---

# 3. Metadata filtering

Metadata is normalized before retrieval.

For DSA retrieval, supported metadata may include:

```text
category
subcategory
data_structures
algorithms
variant
```

For interview retrieval:

```text
company
```

The normalized metadata is sent to both dense and sparse retrieval.

Example:

```python
{
    "category": "Solve Problems on Arrays [...]",
    "algorithms": ["Two Sum"]
}
```

The same filter is applied to both retrieval systems so that they search the same logical corpus subset.

## Empty-filter behavior

If a metadata filter matches no documents:

- Dense retrieval retries without the Chroma filter.
- Sparse retrieval searches the complete BM25 corpus.
- Retrieval continues instead of returning an immediate empty result.

This improves recall, but it can increase work because the system may perform:

```text
filtered query
   ↓
zero results
   ↓
unfiltered query
```

For dense retrieval, that can mean two Chroma network queries.

---

# 4. Dense retrieval

Dense retrieval is implemented in:

```text
app/retrieval/semantic.py
```

The dense process is:

```text
Optimized query
   ↓
OpenAI embedding API
   ↓
Query embedding
   ↓
Chroma query
   ↓
Top-K dense documents
```

The system:

1. Creates an embedding for the query.
2. Opens or retrieves the configured Chroma collection.
3. Executes a vector query.
4. Requests documents, metadata, and distances.
5. Converts Chroma results into canonical candidates.
6. Converts them into `Node` objects where needed.

The current dense score is derived from Chroma distance:

```python
dense_score = 1.0 - distance
```

The dense top-k is configured by:

```env
DENSE_RETRIEVAL_TOP_K=25
```

The same setting is used for both DSA and interview hybrid retrieval in the new hybrid path.

## Dense latency sources

Dense retrieval may include:

- Chroma client/connection initialization
- Chroma network latency
- OpenAI embedding API latency
- Chroma vector search latency
- Metadata filter evaluation
- A second unfiltered Chroma query if filtering returns no results

The vector search itself may be fast, while the embedding API and remote Chroma connection dominate total time.

---

# 5. Sparse retrieval

Sparse retrieval is implemented in:

```text
app/retrieval/sparse.py
```

It uses:

```python
rank_bm25.BM25Okapi
```

The sparse process is:

```text
Canonical Chroma corpus
   ↓
Tokenization
   ↓
BM25 index
   ↓
Tokenized query
   ↓
BM25 scores
   ↓
Top-K sparse documents
```

The tokenizer lowercases words and extracts alphanumeric tokens. Non-empty symbol-only/code-like chunks are still kept indexable.

The sparse top-k is configured by:

```env
SPARSE_RETRIEVAL_TOP_K=25
```

## Important implementation detail

The sparse index is built from the Chroma collection using:

```python
collection.get(include=["documents", "metadatas"])
```

The index contains:

```text
stable ID
document content
metadata
parent ID
child IDs
BM25 index
```

The BM25 index is intended to represent the same canonical chunks as Chroma.

## Critical latency risk

Currently, when `sparse_index` is not passed into the hybrid retriever, this happens per query:

```text
Chroma collection.get(all documents)
   ↓
Load entire corpus remotely
   ↓
Create RetrievalCandidate objects
   ↓
Tokenize entire corpus
   ↓
Build BM25Okapi index
   ↓
Run BM25 search
```

This is potentially the largest performance problem in the current implementation.

The hybrid call currently defaults to:

```python
sparse_index=None
```

Then sparse retrieval builds the index dynamically:

```python
sparse_index = index or build_dsa_index(collection)
```

Therefore, unless the caller provides a prebuilt index, every query can rebuild the complete sparse index.

For a small corpus this may appear fast. For a large corpus, this causes:

- A full remote Chroma read per query
- Full-corpus tokenization per query
- Full BM25 index construction per query
- Extra memory allocation
- Possible connection and serialization overhead

A production implementation should usually build the BM25 index once and reuse it.

Recommended design:

```text
Application startup
   ↓
Load DSA Chroma corpus once
   ↓
Build DSA BM25 index once
   ↓
Load interview Chroma corpus once
   ↓
Build interview BM25 index once
   ↓
Reuse indexes for every query
```

Possible approaches:

- Application startup initialization
- Lazy singleton with thread-safe caching
- Process-level cache
- Persistent local BM25 artifact
- External search index
- Background rebuild when the corpus changes

The index should not be rebuilt for every request.

---

# 6. Parallel dense and sparse retrieval

The hybrid retriever runs dense and sparse retrieval in parallel using:

```python
ThreadPoolExecutor(max_workers=2)
```

The intended flow is:

```text
                    ┌──────────────────┐
                    │                  │
                    ▼                  ▼
             Dense retrieval     Sparse retrieval
             OpenAI + Chroma     BM25 + corpus
                    │                  │
                    └────────┬─────────┘
                             ▼
                       RRF fusion
```

This reduces latency because the dense and sparse branches overlap.

Approximate execution time becomes:

```text
parallel retrieval time
≈ max(dense retrieval time, sparse retrieval time)
```

instead of:

```text
dense retrieval time + sparse retrieval time
```

However, parallelism does not remove the work. If sparse retrieval rebuilds the index while dense retrieval calls OpenAI and Chroma, the total time is still limited by the slower branch.

Also, Python threads do not necessarily improve CPU-heavy BM25 index construction. They mainly help overlap network-bound work.

---

# 7. Canonical retrieval candidates

The shared internal representation is defined in:

```text
app/retrieval/candidates.py
```

A candidate contains:

```python
RetrievalCandidate(
    id,
    content,
    metadata,
    parent_id,
    child_ids,
    dense_score,
    sparse_score,
    rrf_score,
    reranker_score,
)
```

This solves an important hybrid retrieval problem.

Dense and sparse systems must refer to the same document using the same stable ID.

The public application object remains:

```python
Node(
    id,
    content,
    metadata,
    score,
    parent_id,
    child_ids,
)
```

Internal scores do not leak into `Node.metadata`.

---

# 8. Reciprocal Rank Fusion

RRF is implemented in:

```text
app/retrieval/fusion.py
```

Dense and sparse scores are not directly comparable.

For example:

```text
Dense score:
0.87

BM25 score:
14.2
```

RRF does not compare those raw values. It uses rank:

```python
RRF score = 1 / (rrf_k + rank)
```

If a document appears in both lists, it receives contributions from both systems.

Example:

```text
Dense:
1. A
2. B
3. C

Sparse:
1. B
2. A
3. D
```

Both `A` and `B` receive two contributions. The document with the stronger combined rank receives the higher RRF score.

Current configuration:

```env
RRF_K=60
RRF_TOP_K=25
```

The result is a fused candidate pool of up to 25 documents.

RRF is computationally inexpensive compared with:

- LLM calls
- embedding calls
- remote Chroma operations
- Cohere reranking
- rebuilding BM25

RRF is very unlikely to be the primary source of latency.

---

# 9. Cohere reranking

The Cohere adapter is implemented in:

```text
app/retrieval/reranker.py
```

The reranker receives:

```text
Optimized query
+
RRF candidate documents
```

The current sequence is:

```text
RRF candidates: up to 25
   ↓
Cohere rerank API
   ↓
Provider ranking and relevance scores
   ↓
Final candidate order
```

Cohere returns candidate indexes and relevance scores. The adapter maps those indexes back to canonical candidates and stores:

```python
candidate.reranker_score
```

The final public score is:

```python
Node.score = reranker_score
```

Current final top-k:

```env
RERANK_TOP_K=10
```

Therefore, the current default flow is:

```text
Dense: 25
Sparse: 25
RRF: 25
Cohere reranks: 25
Final nodes: 10
```

The context builder receives up to:

```text
10 knowledge nodes
10 interview nodes
```

if both retrieval routes are active.

## Cohere latency sources

The reranker adds:

- Network connection latency
- TLS/request overhead
- Provider queueing
- Serialization of up to 25 documents
- Provider inference time
- Response parsing

If the RRF pool is large or document contents are long, the reranker request becomes more expensive.

The number of candidates and document length should be measured.

---

# 10. Final application result

 
# 10. Final application result

After reranking:

```text
Reranked candidates
   ↓
Take RERANK_TOP_K
   ↓
Convert candidates to Node[]
   ↓
Context builder
```

The context builder receives ordinary `Node` objects.

It does not need to know:

- Which documents came from dense retrieval
- Which documents came from BM25
- Their RRF scores
- Their raw dense scores
- Their raw BM25 scores

The only visible score is the final Cohere score:

```python
Node.score
```

---

# 11. Current diagnostics

The hybrid retriever supports a trace callback.

The current phases are:

```text
metadata_filtering
dense_retrieval
sparse_retrieval
rrf_fusion
cohere_reranking
```

For each candidate, the diagnostic output contains:

```text
document ID
score
first 200 characters
```

The harness also logs:

```text
dense candidate count
sparse candidate count
fused count
reranked count
elapsed milliseconds
```

The interactive `test.py` harness measures total time from when the query is submitted until retrieval completes.

It also prints the configured values:

```text
dense top-k
sparse top-k
RRF top-k
rerank top-k
RRF k
```

---

# 12. Most likely latency problems in another hybrid project

When comparing this architecture with another project, inspect these areas first.

## A. Rebuilding BM25 on every query

This is the most important issue to check.

Bad pattern:

```python
def retrieve(query):
    documents = chroma.get(...)
    bm25 = BM25Okapi(...)
    return bm25.get_top_n(query)
```

This causes a complete corpus load and index rebuild per request.

Better:

```python
bm25 = build_index_once()

def retrieve(query):
    return bm25.search(query)
```

## B. Loading the full Chroma corpus remotely

Avoid doing this during every query:

```python
collection.get(include=["documents", "metadatas"])
```

This transfers all documents over the network and can dominate latency.

## C. Recreating clients repeatedly

Check whether the application creates these on every request:

- Chroma client
- OpenAI client
- Cohere client
- Embedding model
- BM25 index
- HTTP session

Clients and indexes should generally be reused.

## D. Sequential dense and sparse retrieval

Bad:

```python
dense_results = dense_search(query)
sparse_results = sparse_search(query)
```

Better:

```python
run dense and sparse concurrently
```

This project runs those two branches concurrently.

## E. Too many candidates sent to the reranker

If dense and sparse each return hundreds of documents and RRF sends hundreds to Cohere, latency and cost increase.

The current project keeps:

```text
dense: 25
sparse: 25
RRF: 25
reranker input: 25
```

## F. Sending excessively large documents to Cohere

The reranker receives document text, not just IDs.

Long documents increase:

- Request payload size
- Token processing
- Provider inference time
- Response latency

Chunk length should be measured and limited appropriately.

## G. Multiple LLM calls before retrieval

The full application may call:

```text
Intent classifier
Query optimizer
Metadata extractor
```

before retrieval even begins.

If latency is measured only around Chroma, the actual user-perceived delay may be missed.

## H. Metadata filter fallback causing duplicate searches

If filtered retrieval returns no results and the system retries without filters, the request may perform multiple searches.

This is intentional for recall, but it should be measured and logged.

## I. Creating an embedding model per request

Check whether the embedding object is cached.

Bad:

```python
def retrieve(query):
    embedder = OpenAIEmbedding(...)
    embedding = embedder.embed(query)
```

Better:

```python
embedder = OpenAIEmbedding(...)  # initialized once
```

## J. Remote Chroma latency

Chroma Cloud/network latency can be larger than local vector search latency.

Measure separately:

```text
client initialization
embedding request
Chroma query request
result conversion
```

## K. Thread-pool creation per request

This project creates a small `ThreadPoolExecutor` per hybrid call. That is acceptable for low traffic, but for high-throughput systems a shared executor or async implementation may be more efficient.

This is usually less important than rebuilding BM25 or making unnecessary network calls.

## L. Hidden retries and timeouts

Inspect:

- HTTP retry policies
- SDK retries
- Chroma retries
- OpenAI retries
- Cohere retries
- Long default timeouts

A single request can appear slow because each external component retries internally.

## M. Logging large payloads

Logging full documents, embeddings, or provider responses can slow the application and produce excessive I/O.

This project logs:

```text
IDs
scores
counts
timings
short content previews
```

That is the safer pattern.

---

# 13. Recommended timing instrumentation

The other project should measure each phase independently:

```text
total_request_ms
intent_classification_ms
query_optimization_ms
metadata_extraction_ms
dense_embedding_ms
dense_chroma_query_ms
sparse_index_lookup_ms
sparse_query_ms
rrf_ms
reranker_request_ms
node_conversion_ms
context_builder_ms
```

A useful log format is:

```text
retrieval_complete
total_ms=842
intent_ms=120
optimizer_ms=0
metadata_ms=95
dense_ms=310
sparse_ms=12
rrf_ms=1
reranker_ms=300
final_count=10
```

For the current implementation specifically, the most important additional timings would be:

```text
sparse_corpus_load_ms
sparse_tokenization_ms
sparse_index_build_ms
sparse_search_ms
```

If those are included in each request, they are likely the main bottleneck.

---

# 14. Honest assessment of this implementation

The architecture is good in these areas:

- Dense and sparse results use stable IDs.
- Dense and sparse retrieval execute in parallel.
- RRF avoids comparing incompatible score scales.
- Cohere reranking is isolated behind an adapter.
- The public `Node` contract remains stable.
- Internal scores do not leak into application objects.
- The retrieval phases are traceable.
- Failures are typed and visible.

The most important architectural weakness is:

```text
BM25 index construction is not clearly cached or initialized once.
```

Because `retrieve_sparse_dsa()` and `retrieve_sparse_interview()` build indexes when no index is supplied, the caller must explicitly provide a reusable `SparseIndex` for production performance.

A production-ready version should guarantee:

```text
one corpus load and index build per process/startup
```

rather than relying on every caller to pass `sparse_index`.

That is the first thing I would compare against the slower project.
 