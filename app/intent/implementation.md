# Intent Classifier Implementation

## Purpose

This document records the Intent Classifier work currently implemented in the
`feature/intent_classifier` branch and the remaining integration work.

The classifier follows the workflow contract in `docs/architecture/state-flow.md`:

```text
normalized_input + messages + conversation_summary
                         |
                         v
                 Intent Classifier
                         |
                         v
                  intent_decision
```

## What Has Been Implemented

### 1. Intent decision contract

File: `app/contracts/intent_decision.py`

Implemented:

- `IntentType` with the supported values:
  - `document_info`
  - `general_chat`
  - `ambiguous`
- `IntentDecision` with:
  - `query: str`
  - `intent_type: IntentType`
  - `confidence_score: float`
- Validation that:
  - `query` is not empty.
  - `intent_type` is one of the supported values.
  - `confidence_score` is between `0.0` and `1.0`.

`document_info` should route toward retrieval, `general_chat` should route toward
response generation without retrieval, and `ambiguous` should route toward
clarification.

### 2. Provisional normalized-input contract

File: `app/contracts/normalized_input.py`

The current provisional model contains:

```text
NormalizedInput
├── user_query: str
├── image_preview: list
├── pdf_preview: list
└── context: Any | None
```

The preview lists currently use flexible item types because the Input Processor owner
has not yet confirmed whether each item will be a string or a structured object. The
exact item schema must be confirmed before final integration.

### 3. Shared graph state

File: `app/graph/state.py`

Implemented state fields:

```text
State
├── normalized_input: NormalizedInput
├── intent_decision: IntentDecision
├── documents: list
├── retrieved_context: Any
├── messages: list
└── conversation_summary: str
```

The Intent Classifier reads `normalized_input`, `messages`, and
`conversation_summary`, and writes only `intent_decision`.

### 4. Deterministic query builder

File: `app/intent/query_builder.py`

`build_classification_query()` constructs the query given to the classifier from:

1. `normalized_input.user_query`.
2. Every item in `normalized_input.image_preview`.
3. Every item in `normalized_input.pdf_preview`.
4. `normalized_input.context`, when present.
5. The latest 10 entries from `messages`.
6. `conversation_summary`, when present.

The latest 10 messages represent 5 human/agent conversation cycles. Older turns are
represented by the summary.

The query builder also:

- Handles empty previews and optional context.
- Supports dictionary messages with `role` and `content`.
- Supports message-like objects with `type` and `content`.
- Limits each attachment preview to 4,000 characters.
- Produces deterministic labeled sections such as `User Query`, `Image Preview`,
  `PDF Preview`, `Recent Conversation`, and `Older Conversation Summary`.

The query builder is isolated so changes to the Input Processor field names or preview
item structures can be handled in one place.

### 5. Provider interface

File: `app/intent/classifier.py`

`IntentClassifier` is a protocol with this interface:

```python
class IntentClassifier(Protocol):
    def classify(self, query: str) -> IntentDecision:
        ...
```

This keeps the LLM/provider implementation separate from state orchestration and makes
unit tests independent of external APIs.

An actual OpenAI/LangChain implementation has not yet been added. The provider should
return structured data that can be validated as an `IntentDecision`.

### 6. Intent classifier node

File: `app/intent/node.py`

`classify_intent(state, classifier)` currently:

1. Requires `normalized_input`.
2. Validates dictionary input into `NormalizedInput` when necessary.
3. Builds the classification query.
4. Calls the injected classifier.
5. Validates the provider result as `IntentDecision`.
6. Replaces the decision query with the actual constructed query.
7. Returns only:

```python
{"intent_decision": decision}
```

The node does not mutate unrelated state or depend on the Input Processor's internal
implementation.

## Tests Added

File: `tests/test_intent_classifier.py`

Current tests cover:

- Supported intent and confidence validation.
- Rejection of unsupported intents.
- Rejection of confidence values above `1.0`.
- Query construction from user input, image previews, PDF previews, normalized context,
  recent messages, and summary.
- Truncation to the latest 10 messages.
- Node output containing only `intent_decision`.
- Missing `normalized_input` failure.

Focused validation command:

```powershell
.\\.venv\\Scripts\\python.exe -m pytest tests/test_intent_classifier.py -q
```

The current result is 4 passing tests.

## What Must Change After NormalizedInput Confirmation

When the Input Processor owner confirms the final contract, make these changes before
integration:

### 1. Update the normalized-input model

Update `app/contracts/normalized_input.py` to use the agreed exact names and types.
Possible changes include:

- `image_preview` becoming `image_previews`.
- `pdf_preview` becoming `pdf_previews`.
- Preview list items changing from strings to typed preview models.
- `context` becoming a string, list, or structured context model.
- Empty values being represented by `[]`, `None`, or another agreed convention.

Do not add compatibility aliases without coordinating the shared contract. If a gradual
migration is required, use an explicit compatibility layer and tests.

### 2. Update the query builder in one location

Change only `app/intent/query_builder.py` for the mapping from normalized input to the
classifier query. Keep the node interface unchanged where possible.

If previews become structured objects, render only the agreed fields and preserve the
4,000-character bound per preview. Add tests for the final item shape.

### 3. Update fixtures and contract tests

Update `tests/test_intent_classifier.py` and add fixtures matching the final
`NormalizedInput` model. Verify:

- No attachment case.
- One image and one PDF.
- Multiple images and PDFs.
- Empty or missing context.
- Preview text and metadata are rendered correctly.

### 4. Resolve context ownership

Confirm whether `NormalizedInput.context` duplicates or complements graph-level
`messages` and `conversation_summary`.

Recommended responsibility:

- `NormalizedInput.context`: context extracted or normalized directly from the current
  input and attachments.
- `messages`: latest 10 conversation messages.
- `conversation_summary`: older conversation history.

If the team assigns a different meaning, update the query builder and documentation so
the same context is not passed twice or omitted.

## Provider Integration Still Needed

Add a concrete classifier implementation after the model/provider configuration is
agreed. It should:

1. Read the model configuration from the existing settings/environment pattern.
2. Use `OPENAI_API_KEY` only through the configured client.
3. Send the constructed query with clear classification instructions.
4. Restrict output to `document_info`, `general_chat`, or `ambiguous`.
5. Request a confidence score from `0.0` to `1.0`.
6. Parse structured output into `IntentDecision`.
7. Raise a clear error for malformed or unsupported output.
8. Remain injectable so unit tests continue using a fake classifier.

Do not require `LANGGRAPH_API_KEY` for local unit tests. It is only needed if the project
uses a hosted LangGraph/LangSmith service.

## Connecting to the Other Nodes

### Input Processor -> Intent Classifier

The graph should pass the Input Processor output into shared state:

```text
Input Processor
      |
      v
normalized_input
      |
      v
Intent Classifier
```

Required work:

- Confirm the final `NormalizedInput` model.
- Ensure the Input Processor returns that model, or a dictionary accepted by
  `NormalizedInput.model_validate()`.
- Register the classifier node in `app/graph/graph.py` using the project's graph style.
- Pass the configured concrete classifier into `classify_intent`.
- Add an integration test using a representative Input Processor output.

The classifier should not import or call the Input Processor directly.

### Intent Classifier -> Routing

Routing should inspect:

```python
state["intent_decision"].intent_type
```

Expected routes:

```text
document_info -> Retriever
ambiguous     -> Clarification Node
general_chat -> Response Node
```

Required work:

- Add or update routing logic in `app/graph/routing.py`.
- Add routing tests for all three intent values.
- Ensure an ambiguous clarification cycle returns to the Intent Classifier after the
  user responds.

### Intent Classifier -> Retriever

For `document_info`, the Retriever should receive the same shared state, including:

- `normalized_input`
- `intent_decision`
- `messages`
- `conversation_summary`

The Retriever should use `intent_decision` as the routing/classification result, not
re-run intent classification.

### Intent Classifier -> Clarification Node

For `ambiguous`, the Clarification Node should receive:

- `normalized_input`
- `intent_decision`
- `messages`
- `conversation_summary`

After the user answers, the clarification interaction should update `messages` and route
back through the Intent Classifier. The classifier should then build a fresh query using
the updated recent message window.

### Intent Classifier -> Response Node

For `general_chat`, the workflow may skip retrieval and route directly to the Response
Node. The Response Node should receive:

- `normalized_input`
- `intent_decision`
- `messages`
- `conversation_summary`

For `document_info`, it should additionally receive `retrieved_context` after retrieval
and context building.

## Recommended Integration Order

1. Receive confirmation of the final `NormalizedInput` fields and preview item types.
2. Update the normalized-input model and query builder.
3. Run the focused intent tests.
4. Implement the concrete LLM classifier with dependency injection.
5. Add provider parsing/error tests using mocked responses.
6. Register the Intent Classifier in `app/graph/graph.py`.
7. Implement or update routing for all three intent values.
8. Add graph integration tests with fake downstream nodes.
9. Restore or add intent evaluation cases.
10. Run the full test suite:

```powershell
.\\.venv\\Scripts\\python.exe -m pytest
```

## Current Limitations

- The final Input Processor schema is not confirmed.
- Preview item structures are intentionally flexible.
- No concrete LLM provider implementation has been added.
- Graph registration and routing are not yet connected.
- The intent evaluation dataset is not available on this branch.
- The current node expects the caller to inject a classifier instance.

These limitations are deliberate boundaries, not failures of the deterministic node
slice. They allow contract and query behavior to be tested without API calls while the
other component contracts are finalized.
