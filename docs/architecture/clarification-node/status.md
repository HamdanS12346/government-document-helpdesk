# Clarification Node Status

## Current State

Milestone 1 backend foundation is implemented through Task 9.

Task 2, message reducer support, was intentionally skipped for now. The memory owner will handle message reducer behavior, durable message persistence, and conversation reload across HTTP requests. The Clarification Node still accepts `messages` and `conversation_summary` as placeholder/pass-through inputs so that memory can wire them later without changing the node contract.

## Completed

- Task 1: Aligned architecture/state docs with the narrow Clarification Node contract.
- Task 3: Added clarification-local schemas.
- Task 4: Added clarification prompt construction and generator interface.
- Task 5: Implemented the Clarification Node.
- Task 6: Replaced the ambiguous-route placeholder with the real clarification node.
- Task 7: Added three-round clarification routing guard.
- Task 8: Added safe Langfuse metadata for clarification.
- Task 9: Added focused clarification, graph, and observability tests.

## Implementation Summary

The Clarification Node lives under `app/clarification/`.

It reads:

- `intent_decision.intent_type`
- `intent_decision.query`
- `messages`
- `conversation_summary`
- `clarification_round_count`

It does not read `normalized_input` directly. Attachment context reaches clarification through `intent_decision.query`, because the Intent Classifier query already includes relevant attachment previews.

It writes:

- `messages: [AIMessage(content=result.question)]`
- `clarification_round_count: previous_count + 1`

The graph now routes:

- `document_info -> retriever -> context_builder -> END`
- `general_chat -> general_chat_placeholder -> END`
- `ambiguous -> clarification -> END`, while `clarification_round_count < 3`
- `ambiguous -> retriever -> context_builder -> END`, when `clarification_round_count >= 3`

The clarification counter resets to `0` on retriever and general-chat paths in the current graph implementation.

## Files Added

- `app/clarification/__init__.py`
- `app/clarification/schemas.py`
- `app/clarification/prompts.py`
- `app/clarification/generator.py`
- `app/clarification/node.py`
- `tests/clarification/__init__.py`
- `tests/clarification/test_schemas.py`
- `tests/clarification/test_prompts.py`
- `tests/clarification/test_generator.py`
- `tests/clarification/test_node.py`

## Key Files Changed

- `app/graph/graph.py`
- `app/graph/routing.py`
- `app/graph/state.py`
- `app/observability/metadata.py`
- `tests/integration/test_intent_retriever_graph.py`
- `tests/observability/test_langfuse.py`
- `docs/architecture/state-flow.md`
- `docs/architecture/state.md`
- `docs/architecture/architecture.md`
- `docs/architecture/observability/observability.md`

## Tests

Last full test run:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Result:

```text
584 passed, 2 skipped, 1 warning
```

Focused test run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\clarification tests\integration tests\observability
```

Result:

```text
52 passed
```

`git diff --check` passed.

## Limitations / Follow-Up

- Task 2 is pending with the memory owner: `messages` is still not wired with LangGraph `add_messages`.
- Durable conversation persistence across HTTP requests is not implemented in this milestone.
- `/chat` may still expose the older API response shape until milestone 2 connects clarification output to the API/frontend boundary.
- Response generation remains separate from clarification.
- The Clarification Node uses an OpenAI-backed generator by default, but tests inject fakes and do not require network calls.
- Richer end-to-end API behavior should be covered in milestone 2 after the response shape is finalized.

## Suggested Next Step

Proceed with Task 10 handoff / PR summary for Milestone 1, then start Milestone 2 only after confirming the API response contract for `clarification_required`.
