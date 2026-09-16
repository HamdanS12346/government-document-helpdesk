# Hybrid Retrieval Debug Plan

## Baseline Latency

Observed before this pass:

| Input type | First query | Second query | Third query |
| --- | ---: | ---: | ---: |
| Text only | 24s | 21s | 10s |
| PDF query | 12s | 11.88s | 9s |
| Image query | good | good | good |

The main correctness issue was that lexical retrieval returned no documents, so
RRF and Cohere reranking were effectively operating on dense results only.

## Architecture Mismatch Found

The better reference architecture in `hybrid-optimization.md` assumes:

```text
canonical corpus
  -> dense search over Chroma
  -> sparse search over a reusable BM25 index
  -> RRF over both ranked lists
  -> reranker over fused candidates
```

This project had the dense side connected to Chroma, but the default BM25
searcher started empty:

```text
RetrieverPipeline()
  -> BM25LexicalSearcher() with no documents
  -> VectorStoreRetriever() that can query Chroma directly
```

That means:

```text
dense_results = Chroma query results
lexical_results = []
fused_results = dense_results only
```

## Step 1 Implemented: Lexical Corpus Warm-Up

Files changed:

- `app/rag/lexical_search.py`
- `app/rag/node.py`
- `tests/rag/test_lexical_search.py`
- `tests/rag/test_retriever_node.py`

Change:

```text
BM25LexicalSearcher.ensure_indexed(...)
  -> loads external documents only once
  -> builds the in-memory BM25 index
  -> reuses it for later requests

RetrieverPipeline.warm_lexical_index()
  -> asks VectorStoreRetriever.get_all_documents() for the canonical Chroma corpus
  -> warms BM25 before lexical search when BM25 is empty
```

Expected trace behavior after a fresh app process:

- `lexical_retrieval` should now return documents for keyword-friendly queries.
- `reciprocal_rank_fusion.input.lexical_result_count` should be greater than 0.
- The first request after restart may include the one-time Chroma corpus load and
  BM25 build inside lexical retrieval.
- Later requests should reuse the same in-memory BM25 index and should not reload
  the whole corpus.

If first-query latency gets worse but second/third query latency improves, the
BM25 warm-up is confirmed as a first-query cost. The next optimization should
move that cost out of the request path.

## Step 2 Implemented: Startup BM25 Warm-Up

Files changed:

- `app/api/main.py`
- `app/rag/node.py`
- `tests/api/test_chat.py`
- `tests/rag/test_retriever_node.py`

Change:

```text
FastAPI lifespan startup
  -> get_default_retriever_pipeline()
  -> pipeline.warm_lexical_index()
  -> BM25 corpus load/index build happens before serving requests

RetrieverPipeline.execute()
  -> lexical_retrieval now only runs lexical_searcher.search(...)
  -> request path no longer warms BM25
```

Expected trace behavior after restarting the API:

- The one-time Chroma corpus load and BM25 build should move from the first
  `lexical_retrieval` span into application startup.
- First real request should still show lexical documents when BM25 terms match.
- `lexical_retrieval` duration should drop because it is no longer doing
  `collection.get(...)` and BM25 construction.
- If lexical returns zero documents on later queries, that should now mean query
  terms/filtering did not produce BM25 hits, not that BM25 failed to load.

## Step 3 Implemented: Dense Resource Warm-Up And Count Cache

Files changed:

- `app/api/main.py`
- `app/rag/node.py`
- `app/rag/vector_store.py`
- `tests/api/test_chat.py`
- `tests/rag/test_vector_store.py`

Change:

```text
FastAPI lifespan startup
  -> pipeline.warm_dense_resources()
  -> initialize embedding model object
  -> initialize Chroma client/collection
  -> cache Chroma collection.count()
  -> pipeline.warm_lexical_index()

VectorStoreRetriever.search()
  -> reuses cached collection count
  -> avoids collection.count() during normal dense retrieval after startup
```

Expected trace behavior after restarting the API:

- Startup may take a little longer because Chroma collection/count and embedding
  client setup happen before the first request.
- First real `dense_retrieval` should no longer pay Chroma client/collection
  creation or collection count.
- `dense_retrieval` can still be several seconds because query embedding and
  Chroma vector query remain request-time work.
- If `chat_request` is still much larger than the sum of child spans, the missing
  time is probably outside retrieval spans, especially response payload
  serialization, console printing, graph/memory wrapper work, or Langfuse flush.

## Step 4 Implemented: Dense Retrieval Sub-Spans

Files changed:

- `app/rag/vector_store.py`

Change:

```text
dense_retrieval
  -> dense_embedding
  -> dense_chroma_query
  -> dense_chroma_fallback_query, only when filtered query returns zero hits
  -> dense_result_conversion
```

For in-memory fallback mode:

```text
dense_retrieval
  -> dense_embedding
  -> dense_in_memory_search
```

How to read random latency spikes:

- If `dense_embedding` spikes, the delay is OpenAI embedding latency or SDK
  retry behavior.
- If `dense_chroma_query` spikes, the delay is Chroma Cloud/vector query/network
  latency.
- If `dense_chroma_fallback_query` appears, metadata filtering caused an extra
  Chroma query.
- If `dense_result_conversion` spikes, local result conversion or returned
  payload size is unexpectedly expensive.
- If none of the dense children explain the parent `dense_retrieval` time, the
  gap is likely observation overhead or SDK work around the measured calls.

## Ranked Solutions

### 1. Move BM25 Warm-Up Out Of The Request Path

Status: implemented.

Confidence: very high.

Reason:

The lexical fix currently warms BM25 lazily. This fixes correctness, but the
first query after process start may still pay for:

```text
Chroma collection.get(...)
  -> all document text and metadata
  -> Pydantic conversion
  -> full-corpus tokenization
  -> BM25Okapi construction
```

Implemented design:

```text
FastAPI startup
  -> initialize default RetrieverPipeline
  -> load Chroma corpus once
  -> build BM25 once
  -> first user query uses an already-warm lexical index
```

If startup becomes too slow, use a background warm-up with a readiness flag, but
for clean latency testing a blocking startup warm-up is easiest to reason about.

Verification:

- Fresh server startup logs BM25 document count.
- First query no longer performs the full corpus load.
- `lexical_result_count > 0` on the first real query.

### 2. Persist Or Snapshot The Lexical Index Locally

Confidence: very high if the corpus changes infrequently.

Reason:

Even startup warm-up still pulls the full corpus from remote Chroma. A local
snapshot avoids repeatedly paying network transfer and tokenization after every
server restart.

Possible implementation:

```text
build/rebuild command
  -> fetch Chroma corpus once
  -> store canonical chunk JSON locally
  -> optionally store tokenized corpus/BM25 artifact

runtime startup
  -> load local snapshot
  -> build or restore BM25
```

Important:

- Keep Chroma as the source of truth for dense embeddings.
- Store only non-sensitive knowledge-base chunks.
- Add a corpus version/hash so stale snapshots are detectable.

### 3. Run Dense And Lexical Retrieval In Parallel

Confidence: high.

Reason:

The reference architecture runs dense and sparse branches concurrently. This
project still runs:

```text
dense_retrieval
then lexical_retrieval
then RRF
```

After BM25 is warm, lexical search should be CPU/local memory work and can
overlap with:

```text
OpenAI embedding request
Chroma query request
```

Expected impact:

```text
retrieval branch time ~= max(dense_ms, lexical_ms)
instead of dense_ms + lexical_ms
```

Implementation note:

Preserve the same trace span names: `dense_retrieval`, `lexical_retrieval`,
`reciprocal_rank_fusion`, and `reranking`.

### 4. Cache Or Avoid `collection.count()` During Dense Search

Status: implemented with a cached count warmed at startup.

Confidence: high.

Reason:

`VectorStoreRetriever.search()` calls `collection.count()` before every Chroma
query to clamp `n_results`. With Chroma Cloud, that can be an extra network
round trip on every retrieval.

Possible implementation:

```text
cache collection count once per process
or
query with configured top_k directly if Chroma accepts n_results > collection size
```

Verification:

- Compare dense span before and after removing/caching count.
- Confirm no error when corpus size is smaller than `top_k`.

### 5. Add A Deterministic Metadata Filter Fast Path

Confidence: high.

Reason:

`MetadataExtractor.extract()` is an LLM call for every non-empty query. Many
government document queries contain exact terms already present in
`metadata_catalog.json`, such as Aadhaar, PAN, passport, caste certificate, or
driving license.

Possible implementation:

```text
exact/synonym catalog matcher
  -> if confident, return MetadataFilterDecision without LLM
  -> otherwise call the current LLM extractor
```

This preserves recall because uncertain queries still use the existing LLM path.

### 6. Warm Reusable Clients At Startup

Confidence: medium-high.

Reason:

The first query likely pays lazy initialization costs for:

- Chroma client
- Chroma collection
- OpenAI embeddings client
- Cohere client
- Langfuse client

Some of these are already cached after first use, which matches the observed
first-query penalty pattern.

Possible implementation:

```text
startup warm-up
  -> get Chroma collection
  -> initialize embedding model object
  -> initialize Cohere client when configured
```

Avoid making real OpenAI/Cohere inference calls during startup unless explicitly
needed.

### 7. Reduce Reranker Payload Size

Confidence: medium-high.

Reason:

Cohere reranking receives all fused document text. Current defaults can send up
to 25 chunks. If chunks are long, the reranker request becomes expensive.

Possible implementation:

```text
RRF_TOP_N: 25 -> 12 or 15
or
truncate reranker document text to a measured character/token budget
```

Verification:

- Check answer quality after reducing candidate count.
- Track `reranking` span latency and final source quality.

### 8. Make Metadata Filter Fallback More Selective

Confidence: medium.

Reason:

Dense search retries without filters when a filtered Chroma query returns zero
hits. This is good for recall, but it can double Chroma query work.

Possible implementation:

```text
only apply filters when metadata confidence is very high
or
use catalog/document counts to avoid filters known to be empty
or
trace when fallback happens and tune after evidence
```

Do not remove the fallback until recall is measured.

### 9. Review API Console Printing During Latency Tests

Confidence: medium.

Reason:

The `/chat` route prints full `documents` and `retrieved_context` JSON. During
debugging this is useful, but pretty-printing large document/context payloads can
add terminal I/O time.

Do not change this while tracing latency, but keep it on the list for later once
retrieval behavior is stable.

### 10. Consider A Dedicated Search Backend For Lexical Retrieval

Confidence: lower for this stage, higher long term.

Reason:

In-memory BM25 is simple and likely enough now. If the corpus grows large or
multiple workers need consistent warm indexes, a dedicated lexical backend may
be cleaner.

Options:

- SQLite FTS
- Tantivy/Lucene-style index
- OpenSearch/Elasticsearch
- Chroma metadata plus external keyword index

This is a later architecture choice, not the first optimization.

## Test Commands

Focused retrieval tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/rag
```

Current result:

```text
34 passed
```

## Next Recommended Implementation Order

1. Run a fresh latency test with the lexical fix and record:
   `lexical_result_count`, `dense_result_count`, `reranking.input_document_count`,
   and total request time.
2. If first query is worse but later queries improve, move BM25 warm-up to
   startup.
3. If dense remains slow on every query, cache or remove the per-query
   `collection.count()`.
4. If retrieval branch time is still additive, parallelize dense and lexical.
5. If pre-retrieval time dominates, add deterministic metadata extraction.
6. If reranking dominates, reduce/truncate reranker inputs.
