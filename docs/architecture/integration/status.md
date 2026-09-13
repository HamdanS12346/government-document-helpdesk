# Intent-Retriever Integration Status

## Current Status

Milestone 1 is complete.

The backend now has an intent-to-retriever graph slice that starts after input
processing and routes based on `intent_decision.intent_type`.

Implemented flow:

```text
Input Processor result
  -> normalized_input
  -> Intent Classifier
  -> intent_decision
  -> route_after_intent
  -> document_info: retriever
  -> general_chat: general_chat_placeholder
  -> ambiguous: clarification_placeholder
```

For now, only `document_info` reaches the Retriever. The `general_chat` and
`ambiguous` branches stop at placeholder nodes.

## Implemented Pieces

- Preserved the existing input-intent graph:
  `build_input_intent_graph()` and `invoke_input_intent_graph()`.
- Added stable graph node constants for intent classifier, retriever, and
  placeholder branches.
- Added `route_after_intent()` in `app/graph/routing.py`.
- Added placeholder nodes in `app/graph/graph.py`.
- Added `build_intent_retriever_graph()`.
- Added `invoke_intent_retriever_graph()`.
- Updated `RetrieverPipeline.execute()` so retrieval query rewriting starts
  from `normalized_input.combined_text.strip() or normalized_input.user_query`.
- Kept attachment previews out of the retriever rewriter call because
  `combined_text` already contains extracted attachment content.

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
7 passed
```

```powershell
.\.venv\Scripts\python.exe -m pytest tests/intent-classifier tests/rag tests/api
```

Result:

```text
45 passed, 1 warning
```

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Result:

```text
535 passed, 2 skipped, 1 warning
```

## Important Boundaries

- No shared state fields were added or renamed.
- No `IntentDecision` or `NormalizedInput` fields were changed.
- No live external provider calls were added to automated tests.
- Response generation, clarification behavior, memory, and context building are
  still out of scope.
- `/chat` has not yet been switched to the new graph bridge in this milestone.

## Next Milestone

Milestone 2 should connect FastAPI `/chat` to:

```python
invoke_intent_retriever_graph(...)
```

The expected local debug output for a `document_info` frontend request is:

```text
Normalized input:
Intent decision:
Documents:
```

The API response can remain focused on the current public input-processing
payload until the Response Node is implemented.
