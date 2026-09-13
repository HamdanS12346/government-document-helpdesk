# Intent Classifier Node Plan

## Goal

Implement the Intent Classifier Node described in `docs/architecture/state-flow.md`.
The node should read the normalized user input and conversation context, classify the
request, validate the result against the `IntentDecision` contract, and write
`intent_decision` to shared graph state.

The provisional `NormalizedInput` fields supplied to this node are:

- `user_query`: the user's text-based request.
- `image_preview`: a list containing previews for zero or more attached images.
- `pdf_preview`: a list containing previews for zero or more attached PDFs.
- `context`: normalized conversation context supplied by the Input Processor.

The exact preview item structures and the relationship between `context` and the
graph-level `messages` and `conversation_summary` fields must be confirmed with the
Input Processor owner before final integration.

Supported intent types:

- `document_info`: requires government-document or government-service retrieval.
- `general_chat`: does not require document retrieval.
- `ambiguous`: lacks enough information for a reliable classification and should route to clarification.

## Current Starting Point

- `app/intent/` currently contains only `__init__.py`.
- `app/contracts/intent_decision.py` and `app/contracts/normalized_input.py` now define the initial typed contracts.
- `app/graph/state.py` now defines the initial shared state shape.
- `app/intent/query_builder.py`, `classifier.py`, and `node.py` provide the initial provider-independent classifier slice.
- The architecture and schema documents define the intended interfaces, but the Python contracts still need to be implemented.
- The intent evaluation dataset is not present on this branch, so create focused tests and restore or coordinate evaluation cases before running the evaluator.

## Implementation Sequence

### 1. Confirm the contracts before coding

Status: initial provisional contracts implemented; confirm preview item types and
the ownership of `context` before final integration.

Read and agree on the exact fields for:

- `NormalizedInput`, especially `user_query` and attachment preview fields.
- `IntentDecision`: `query`, `intent_type`, and `confidence_score`.
- Shared `State`: `normalized_input`, `messages`, `conversation_summary`, and `intent_decision`.

Do not silently add or rename shared fields. If the contract needs to change, update
its Python model, architecture/schema documentation, and tests together.

### 2. Implement the shared Pydantic models

Complete the contract models before implementing the node:

- Define the supported intent values as a constrained type or enum.
- Validate `confidence_score` within `0.0` to `1.0`.
- Require a non-empty classification `query`.
- Preserve the public field names documented in `docs/architecture/schema/intent_decision.md`.

Add model tests for valid decisions and invalid intent/confidence values.

### 3. Define the classifier input boundary

Status: initial deterministic query builder implemented.

Create a small, testable query-building helper in `app/intent/` that combines:

1. `normalized_input.user_query`.
2. `normalized_input.image_preview`, containing previews for all attached images.
3. `normalized_input.pdf_preview`, containing previews for all attached PDFs.
4. `normalized_input.context`, when supplied by the Input Processor.
5. The latest 10 conversation messages from `messages`, representing 5 human/agent cycles.
6. `conversation_summary` for older conversation turns, when available.

The helper should be deterministic and should not pass full attachment contents to the
classifier. It should also handle missing or empty previews and conversation fields.
Its output becomes `IntentDecision.query`. Recent messages provide exact wording,
while the summary preserves older intent and facts after turns leave the message window.

### 4. Implement classification separately from orchestration

Status: injectable protocol and `OpenAIIntentClassifier` provider implemented and
covered by focused tests.

Keep the LLM/provider call separate from the LangGraph node function:

- Define a classifier interface that accepts the constructed query and returns structured data.
- Use the existing LangChain/OpenAI dependencies and repository configuration patterns.
- Instruct the model to return only one supported intent and a confidence score.
- Make the model dependency injectable so unit tests do not call an external provider.
- Handle malformed provider output through structured parsing and a clear error path.

Avoid embedding prompt construction, provider setup, and state mutation in one large function.

### 5. Implement the node function

Status: initial node implemented and covered by focused tests.

Add the node entry point under `app/intent/` using the repository's graph-node convention.
The node should:

- Read only `normalized_input`, `messages`, and `conversation_summary`.
- Build the classification query.
- Invoke the injected classifier.
- Validate and construct `IntentDecision`.
- Return only `intent_decision` as its state update.
- Avoid mutating unrelated state fields.

The node should fail clearly when required normalized input is missing rather than silently
classifying an empty request.

### 6. Add focused tests before graph integration

Create tests under `tests/intent-classifier/` covering:

- A government document or service question classified as `document_info`.
- A casual greeting classified as `general_chat`.
- An underspecified request such as "Can you check this?" classified as `ambiguous`.
- A request whose meaning depends on an image or PDF preview.
- Conversation context changing the interpretation of a follow-up request.
- Conversation summary being included when messages are truncated.
- Missing attachments and missing optional conversation context.
- Invalid provider output, unsupported intent values, and out-of-range confidence.
- The node returning only the documented `intent_decision` state update.

Use a fake/injected classifier in unit tests. Keep provider or evaluator tests separate
from deterministic node tests.

### 7. Integrate with graph routing

After the node and tests work in isolation:

- Register the node in `app/graph/graph.py` using the existing graph style.
- Route from the classifier using `intent_decision.intent_type`.
- Confirm `document_info` routes to retrieval, `ambiguous` routes to clarification, and
  `general_chat` routes toward response generation.
- Ensure clarification returns to the classifier with updated `messages`.
- Update routing tests and architecture documentation if the actual graph behavior differs
  from `docs/architecture/state-flow.md`.

Do not implement clarification, retrieval, or response behavior inside the intent module.

### 8. Add evaluation coverage

Restore or coordinate the intent evaluation cases on this branch, then add examples for:

- Each supported intent type.
- Attachment-dependent classification.
- Context-dependent follow-ups.
- Low-confidence or ambiguous requests.

Run the intent evaluator after unit tests and document any known model-dependent limitations.
Do not commit API keys, raw private documents, or `.env` files.

## Suggested Module Layout

```text
app/intent/
|-- __init__.py
|-- classifier.py       # Provider-facing classification interface
|-- query_builder.py    # Deterministic input/context construction
|-- node.py             # LangGraph node orchestration
`-- plan.md
```

Use the project's established naming and import conventions if they differ from this
suggestion. Keep shared schemas in `app/contracts/`, not inside `app/intent/`.

## Validation Order

Run the narrowest check after each stage:

1. Contract/model tests.
2. Query-builder tests.
3. Classifier/node tests with a fake provider.
4. Graph routing tests.
5. Intent evaluator.
6. Full suite with `pytest`.

Before handing off, verify:

- `git status` contains only intended files.
- No secrets or generated artifacts are included.
- `IntentDecision.query` contains the actual constructed classifier query.
- Confidence values are validated.
- All three intent values route as documented.
- The intent evaluation dataset is available or its absence is documented.
