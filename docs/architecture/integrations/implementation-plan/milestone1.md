# Milestone 1: Safe Input-To-Intent Graph Slice

## Goal

Create the smallest reliable graph slice that accepts a successful Input Processor result, converts it into `GraphState`, runs the Intent Classifier, and writes `intent_decision`.

This milestone should not change frontend behavior yet. It should make the backend graph integration ready and testable without real OpenAI calls.

## Target Flow

```text
InputProcessingResult(success=True)
  -> build_graph_state_update()
  -> GraphState.normalized_input
  -> intent_classifier node
  -> GraphState.intent_decision
```

## Tasks

### 1. Confirm The Current Contracts

Review the existing contracts before editing:

- `app/contracts/normalized_input.py`
- `app/contracts/intent_decision.py`
- `app/graph/state.py`
- `app/input_processing/processors.py`
- `app/intent/node.py`

Confirm that `GraphState` already contains:

```text
normalized_input
intent_decision
messages
conversation_summary
documents
retrieved_context
```

Do not add new state fields for this milestone. `messages` and `conversation_summary` are future memory fields and should remain optional.

### 2. Keep Input Processor As The Raw Input Boundary

Use the existing `build_graph_state_update(result)` helper to move from input processing into graph state.

Expected behavior:

- Successful input result returns `{"normalized_input": result.normalized_input}`.
- Failed input result returns `{}`.
- Raw uploads, API upload objects, temporary paths, attachment bytes, OCR providers, and `InputProcessingResult` must not enter graph state.

This keeps the graph clean and preserves the Input Processor ownership boundary.

### 3. Build The Input-Intent Graph In `app/graph/graph.py`

Add a graph builder dedicated to this slice:

```python
build_input_intent_graph(classifier)
```

The compiled graph should be:

```text
START
  -> intent_classifier
  -> END
```

The graph should start from `GraphState` that already contains `normalized_input`. It should not receive raw frontend payloads or `InputRequest`.

The classifier must be injected into the graph builder. Do not instantiate `OpenAIIntentClassifier` inside the intent node.

### 4. Add A Bridge Helper For Successful Input Results

Add a helper like:

```python
invoke_input_intent_graph(result, classifier, messages=None, conversation_summary=None)
```

This helper should:

- Convert `InputProcessingResult` to graph state with `build_graph_state_update()`.
- Reject failed or empty input results before invoking the classifier.
- Optionally pass through `messages` and `conversation_summary`.
- Return the final graph state after classification.

For this milestone, callers may omit `messages` and `conversation_summary`.

### 5. Preserve Intent Classifier Behavior

Do not change `app/intent/node.py` unless a real contract issue is found.

The intent node should continue to:

- Require `normalized_input`.
- Build the classification query with `build_classification_query()`.
- Use attachment previews, not full extracted text.
- Validate the provider result as `IntentDecision`.
- Return only `{"intent_decision": decision}` from the node.

### 6. Add Offline Integration Tests

Create focused tests for the graph slice using a fake classifier.

Tests should prove:

- The compiled graph accepts `normalized_input` and returns `intent_decision`.
- The classifier receives a query built from `NormalizedInput`.
- Image/PDF previews are included in the query.
- Full extracted text and `combined_text` are not included in the intent query.
- Failed `InputProcessingResult` objects are rejected before classifier invocation.
- The graph can run with only `normalized_input`; message history is optional.

Tests must not require `OPENAI_API_KEY` and must not make network calls.

### 7. Run Verification

Run the focused graph tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_input_intent_graph.py -q
```

Then run the full backend suite:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## Done Criteria

Milestone 1 is complete when:

- `app/graph/graph.py` exposes a compiled input-intent graph builder.
- A successful input result can produce final state containing both `normalized_input` and `intent_decision`.
- Failed input processing does not invoke intent classification.
- Tests are offline and deterministic.
- Full backend tests pass.

## Out Of Scope

- Changing the frontend request.
- Returning `intent_decision` to the frontend.
- Real OpenAI smoke testing.
- Routing by `intent_type`.
- Retriever, context builder, clarification, memory, or response generation.
