# Intent-Retriever-Context Integration Status

## Current Status

Milestone 2 is complete, and the document-info branch now continues through
Context Builder.

The backend now has an intent-to-retriever-context graph slice that starts after
input processing and routes based on `intent_decision.intent_type`.

Implemented flow:

```text
Input Processor result
  -> normalized_input
  -> Intent Classifier
  -> intent_decision
  -> route_after_intent
      -> document_info: retriever -> context_builder -> retrieved_context
      -> general_chat: general_chat_placeholder
      -> ambiguous: clarification_placeholder
```

For now, only `document_info` reaches the Retriever and Context Builder. The
`general_chat` and `ambiguous` branches stop at placeholder nodes.

## Implemented Pieces

- Preserved the existing input-intent graph:
  `build_input_intent_graph()` and `invoke_input_intent_graph()`.
- Added stable graph node constants for intent classifier, retriever, context
  builder, and placeholder branches.
- Added `route_after_intent()` in `app/graph/routing.py`.
- Added placeholder nodes in `app/graph/graph.py`.
- Added `build_intent_retriever_graph()`.
- Added `invoke_intent_retriever_graph()`.
- Wired `document_info` routing as `retriever -> context_builder -> END`.
- Updated `RetrieverPipeline.execute()` so retrieval query rewriting starts
  from `normalized_input.combined_text.strip() or normalized_input.user_query`.
- Kept attachment previews out of the retriever rewriter call because
  `combined_text` already contains extracted attachment content.
- Updated `/chat` to print `retrieved_context` when the final graph state
  contains it.

## Tests Added

- Added graph integration coverage in `tests/integration/`.
- Added Retriever pipeline coverage proving the query rewriter receives
  `normalized_input.combined_text`, not `intent_decision.query`.

Latest verified test runs:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration
```

Result:

```text
9 passed
```

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration tests/api tests/context-builder
```

Result:

```text
99 passed, 1 warning
```

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Result:

```text
541 passed, 2 skipped, 1 warning
```

## Important Boundaries

- No shared state fields were added or renamed.
- No `IntentDecision` or `NormalizedInput` fields were changed.
- No live external provider calls were added to automated tests.
- Response generation, clarification behavior, and memory are still out of
  scope.
- `/chat` uses the intent-retriever graph bridge and keeps the current public
  input-processing response shape.

## Next Milestone

The expected local debug output for a `document_info` frontend request is:

```text
Normalized input:
Intent decision:
Documents:
Retrieved context:
```

The API response can remain focused on the current public input-processing
payload until the Response Node is implemented.
