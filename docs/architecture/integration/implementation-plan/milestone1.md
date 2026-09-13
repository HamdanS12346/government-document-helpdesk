# Milestone 1: Intent-to-Retriever Graph Slice

## Goal

Create the first implementation phase for connecting the existing Input
Processor and Intent Classifier graph slice to the Retriever path.

By the end of this milestone, the backend graph can route from
`intent_decision.intent_type` and only call the Retriever for `document_info`.
The `general_chat` and `ambiguous` branches exist as placeholders and stop
cleanly.

This milestone does not require live provider calls in tests and does not
change the public `/chat` response contract.

## Starting State

The project currently has this local flow:

```text
Frontend chat
  -> FastAPI /chat
  -> Input Processor
  -> normalized_input
  -> input-intent graph
  -> Intent Classifier
  -> intent_decision
  -> END
```

The existing graph is built by:

```python
build_input_intent_graph(classifier)
```

The existing bridge is:

```python
invoke_input_intent_graph(
    result,
    classifier,
    messages=None,
    conversation_summary=None,
)
```

The graph assumes input processing already succeeded and requires
`normalized_input` before classification. The FastAPI route currently prints
`normalized_input` and `intent_decision` in the backend terminal, then stops.

## Target State

This milestone adds a new graph path:

```text
START
  -> intent_classifier
  -> route_after_intent

route_after_intent:
  document_info -> retriever
  general_chat  -> general_chat_placeholder
  ambiguous     -> clarification_placeholder

retriever -> END
general_chat_placeholder -> END
clarification_placeholder -> END
```

The final state for a `document_info` request includes:

```text
normalized_input
intent_decision
documents
messages, if provided
conversation_summary, if provided
```

The final state for `general_chat` and `ambiguous` includes no `documents`
field for now.

## Phase Tasks

### 1. Preserve the Existing Input-Intent Graph

Keep `build_input_intent_graph()` and `invoke_input_intent_graph()` available
so existing tests and callers do not silently change behavior.

Continuity note: this keeps the current frontend/API behavior stable while the
new integration graph is built beside it.

### 2. Add Stable Graph Node Names

Add graph node-name constants in `app/graph/graph.py`:

```python
INTENT_CLASSIFIER_NODE = "intent_classifier"
RETRIEVER_NODE = "retriever"
GENERAL_CHAT_PLACEHOLDER_NODE = "general_chat_placeholder"
CLARIFICATION_PLACEHOLDER_NODE = "clarification_placeholder"
```

Use these constants when wiring the new graph and route table.

Continuity note: these names become the stable replacement points for the
future Response and Clarification nodes.

### 3. Implement Intent Routing

Add `route_after_intent(state)` in `app/graph/routing.py`.

The router should:

- Read `state["intent_decision"]`.
- Raise a clear `ValueError` if `intent_decision` is missing.
- Route `document_info` to the Retriever node.
- Route `general_chat` to the general-chat placeholder.
- Route `ambiguous` to the clarification placeholder.
- Raise a clear `ValueError` for unsupported intent values.

Continuity note: routing should stay orchestration-only. Do not put retrieval,
response, or clarification business logic in this helper.

### 4. Add Placeholder Nodes

Add explicit placeholder node functions for the incomplete branches:

```python
def general_chat_placeholder(state):
    return {}


def clarification_placeholder(state):
    return {}
```

These placeholders should not call LLMs, produce fake assistant answers, or
print terminal output from inside the node.

Continuity note: the placeholders exist only so graph routing is complete
enough to test now and replace cleanly later.

### 5. Add the New Graph Builder

Add:

```python
build_intent_retriever_graph(classifier, retriever=retriever_node)
```

The builder should:

- Add the existing Intent Classifier node.
- Add the Retriever node.
- Add the two placeholder nodes.
- Route from `START` to the Intent Classifier.
- Add conditional edges after the Intent Classifier using `route_after_intent`.
- End after the Retriever or either placeholder.

Continuity note: accept an injectable `retriever` callable so tests can use a
fake retriever without touching live Chroma, embeddings, or reranking.

### 6. Add the New Graph Bridge

Add:

```python
invoke_intent_retriever_graph(
    result,
    classifier,
    retriever=retriever_node,
    messages=None,
    conversation_summary=None,
)
```

The bridge should mirror the current input-intent bridge:

- Convert successful `InputProcessingResult` into graph state.
- Require `normalized_input`.
- Preserve optional `messages`.
- Preserve optional `conversation_summary`.
- Invoke `build_intent_retriever_graph()`.
- Return the final graph state.

Continuity note: this bridge is the future FastAPI route boundary. Keep it
small and predictable.

### 7. Update the Retriever Query Source

Update `RetrieverPipeline.execute(state)` so the rewriter receives
`normalized_input.combined_text` as the current retrieval input:

```python
retrieval_input = norm_input.combined_text.strip() or norm_input.user_query
```

Pass `retrieval_input` to the query rewriter instead of relying only on
`norm_input.user_query`.

If the existing `QueryRewriter.rewrite()` signature stays unchanged, call it
with empty attachment previews:

```python
rewritten_query = self.query_rewriter.rewrite(
    user_query=retrieval_input,
    messages=messages,
    conversation_summary=summary,
    attachment_previews=[],
)
```

Continuity note: `combined_text` already contains user text plus extracted
image/PDF content, so avoid injecting the same attachment content twice.

### 8. Add Focused Integration Tests

Create tests under `tests/integration/` for graph-level behavior using fake
classifiers and fake retrievers.

Coverage should include:

- `document_info` routes to the Retriever and writes `documents`.
- `general_chat` routes to the placeholder and does not write `documents`.
- `ambiguous` routes to the placeholder and does not write `documents`.
- Missing `normalized_input` still fails before classification.
- Missing `intent_decision` in routing raises a clear error.
- Existing `messages` are preserved.
- Existing `conversation_summary` is preserved.
- The Retriever receives the same `normalized_input` object produced by input
  processing.

Continuity note: these are integration tests for the local graph contract, not
live provider tests.

### 9. Add Retriever Query-Source Test

Add a Retriever pipeline test with a fake query rewriter that records the
`user_query` argument.

Assert that the recorded value equals:

```python
normalized_input.combined_text
```

and not:

```python
intent_decision.query
```

Continuity note: this protects the most important retrieval-quality detail in
the integration.

### 10. Run Focused Tests

Run the new integration tests first:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration
```

Then run the existing relevant areas:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/intent-classifier tests/rag tests/api
```

Finally run the full suite when practical:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## Done Criteria

Milestone 1 is complete when:

- The old input-intent graph still works.
- The new intent-retriever graph exists.
- `document_info` reaches the Retriever through graph routing.
- `general_chat` and `ambiguous` stop at explicit placeholders.
- Retriever query rewriting starts from `normalized_input.combined_text`.
- Automated tests cover graph routing without live external calls.
- No shared contract fields are renamed or removed.

## Out of Scope

- Do not implement the Response Node.
- Do not implement the Clarification Node.
- Do not implement Memory.
- Do not expose raw retrieved documents in the public frontend response.
- Do not make automated tests depend on OpenAI, Cohere, Chroma Cloud, or any
  other live provider.
