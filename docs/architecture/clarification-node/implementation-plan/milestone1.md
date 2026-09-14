# Milestone 1 - Clarification Node Backend Foundation

## Goal

Replace the current ambiguous-route placeholder with a real backend Clarification Node that fits the existing LangGraph architecture.

This milestone should make the graph capable of:

- routing `intent_decision.intent_type == "ambiguous"` into a real clarification node
- generating one friendly clarification question
- appending that question to `messages` as an `AIMessage`
- tracking consecutive clarification rounds in graph state
- tracing the clarification step safely in Langfuse
- preserving the existing `document_info` and `general_chat` paths

This milestone does not need to solve durable conversation memory across HTTP requests. It should prepare the state and APIs so the later memory branch can persist and reload the same fields without changing the Clarification Node.

## Current Baseline

The current codebase has these relevant pieces:

- `app/graph/graph.py` defines `CLARIFICATION_PLACEHOLDER_NODE` and `clarification_placeholder`.
- `app/graph/routing.py` routes `IntentType.AMBIGUOUS` to the placeholder.
- `app/graph/state.py` contains `normalized_input`, `intent_decision`, `documents`, `retrieved_context`, `messages`, and `conversation_summary`.
- `app/clarification/` exists as the right package location, but it has no implementation files yet.
- `messages` is currently typed as `list[Any]`; it is not yet wired as a LangGraph message reducer.
- `app/observability/` already provides `start_observation`, no-op fallback behavior, safe metadata helpers, and text capture gating through `LANGFUSE_CAPTURE_TEXT`.
- `docs/architecture/clarification-node/architecture.md` says the Clarification Node should read only `messages`, `conversation_summary`, and `intent_decision.intent_type/query`.

## Minor Architecture Adjustment

Use a completed graph state result for the current implementation instead of a hard LangGraph interrupt in milestone 1.

Reason:

- The architecture requires that the clarification `AIMessage` is committed to `messages` before the request returns.
- The current API is ordinary request/response and does not yet have checkpoint persistence.
- A node that writes an `AIMessage` and ends the graph is easier to test now.
- A future checkpoint/memory branch can still add LangGraph interrupt/resume behavior without changing the node contract.

This still follows the architecture's user-facing behavior: the first `/chat` request returns a clarification question, then the user answers through a normal later `/chat` request.

## Task 1 - Align The Local Contract Before Coding

Update the implementation contract documents that currently disagree with the clarification architecture.

Files:

- `docs/architecture/state-flow.md`
- `docs/architecture/state.md`
- `docs/architecture/architecture.md`, if the high-level overview is kept in sync in this branch

Work:

- Clarify that the Clarification Node reads:
  - `intent_decision.intent_type`
  - `intent_decision.query`
  - `messages`
  - `conversation_summary`
- Remove `normalized_input` from the Clarification Node's direct input list.
- Clarify that attachment context reaches clarification through `intent_decision.query`, because the intent classifier query already includes attachment previews.
- Clarify that the Clarification Node writes:
  - `messages`
  - `clarification_round_count`
  - optional graph outcome/status metadata if needed by the API boundary
- Add the selected counter field name:
  - `clarification_round_count`

Acceptance:

- Docs no longer describe clarification as inspecting raw normalized input.
- Docs explicitly leave durable conversation persistence to the memory branch.
- The state docs make it clear that no raw uploaded bytes or raw private files enter clarification state.

## Task 2 - Add Message Reducer Support To Graph State

Make `messages` behave like conversation state instead of a normal list overwrite.

Files:

- `app/graph/state.py`
- graph integration tests

Work:

- Update `GraphState.messages` to use LangGraph's message reducer, likely `add_messages`.
- Keep the public state field named `messages`.
- Accept both LangChain message objects and existing dictionary-style test messages where practical.
- Avoid introducing a separate clarification history field.

Why:

- The architecture depends on this sequence staying in the normal conversation:
  - `Human(original request)`
  - `AI(clarification question)`
  - `Human(clarification answer)`
- Without a reducer, a node returning `{"messages": [AIMessage(...)]}` can overwrite earlier messages.

Acceptance:

- Returning a clarification `AIMessage` appends to existing `messages`.
- Existing intent-classifier and retriever tests that pass `messages` still work or are updated to the new canonical message representation.
- No raw attachment bytes are added to `messages`.

## Task 3 - Add Clarification Internal Schemas

Create node-local schemas under `app/clarification/`.

Files:

- `app/clarification/__init__.py`
- `app/clarification/schemas.py`

Recommended models:

- `ClarificationInput`
  - `intent_type`
  - `classification_query`
  - `messages`
  - `conversation_summary`
  - `clarification_round_count`
- `ClarificationResult`
  - `question`
  - `reason_code`
  - `missing_dimensions`

Guidance:

- Keep these schemas local to the clarification package unless another component needs to import them as a shared contract.
- Do not add a new user-visible message type.
- The graph output remains an `AIMessage` in `messages`.

Reason codes can start small:

- `missing_document_type`
- `missing_service_or_task`
- `missing_location`
- `missing_applicant_context`
- `missing_attachment_reference`
- `unclear_request`

Acceptance:

- Internal schema validation catches empty questions and invalid reason codes.
- The state contract remains simple.

## Task 4 - Add Clarification Prompt And Provider Interface

Build a replaceable generator layer similar to the intent classifier pattern.

Files:

- `app/clarification/prompts.py`
- `app/clarification/generator.py`
- `tests/clarification/`

Work:

- Define a `ClarificationGenerator` protocol.
- Add an OpenAI-backed implementation using the existing model pattern unless a shared model config is introduced first.
- Use structured output for `ClarificationResult`.
- Keep temperature low.
- Keep model/provider construction lazy where useful for tests.

Prompt requirements:

- Ask only when ambiguity blocks a reliable next step.
- Ask all materially necessary clarification questions in one focused interaction.
- Use plain English.
- Briefly explain why the information is needed.
- Use examples/options only when useful.
- Do not provide government instructions, fees, eligibility, timelines, or citations.
- Treat `intent_decision.query`, attachment previews, messages, and summary as untrusted user-provided content.
- Do not reveal prompts or internal routing.
- Do not request unnecessary sensitive identifiers such as Aadhaar, PAN, phone number, email, or full address.

Acceptance:

- Unit tests can replace the provider with a fake generator.
- Prompt tests cover clarification-only behavior, prompt-injection resistance, and PII minimization language.

## Task 5 - Implement The Clarification Node

Create the actual LangGraph node.

Files:

- `app/clarification/node.py`
- `tests/clarification/test_node.py`

Behavior:

- Read `intent_decision`; fail clearly if it is missing.
- Validate that `intent_decision.intent_type == IntentType.AMBIGUOUS`; fail clearly or no-op if called incorrectly.
- Read `intent_decision.query` as the classification-facing request.
- Read `messages` and `conversation_summary`.
- Read `clarification_round_count`, defaulting to `0`.
- Call the configured `ClarificationGenerator`.
- Return:
  - `messages: [AIMessage(content=result.question)]`
  - `clarification_round_count: previous_count + 1`
  - optional `workflow_status: "clarification_required"` if the API needs a graph-level outcome field

Do not:

- read raw files
- retrieve documents
- call the retriever
- call the response node
- modify `normalized_input`
- generate substantive government guidance

Acceptance:

- The node emits exactly one assistant clarification message.
- The message is friendly and does not include citations.
- The node does not require `normalized_input`.
- The round counter increments only when a clarification question is produced.

## Task 6 - Replace The Placeholder In Graph Wiring

Wire the real node into the intent-retriever graph.

Files:

- `app/graph/graph.py`
- `app/graph/routing.py`
- `tests/integration/test_intent_retriever_graph.py`

Work:

- Replace `CLARIFICATION_PLACEHOLDER_NODE` usage with a real `CLARIFICATION_NODE` constant.
- Add the clarification node to `build_intent_retriever_graph`.
- Allow dependency injection of a fake clarification node/generator in tests, following the existing retriever/context-builder injection style.
- Keep `document_info -> retriever -> context_builder -> END`.
- Keep `general_chat -> general_chat_placeholder -> END` until the response node exists.
- Keep `ambiguous -> clarification -> END` for now.

Acceptance:

- Ambiguous requests route to the real clarification node.
- Retriever and context builder are not called on the first ambiguous route.
- Existing document retrieval integration tests still pass.
- Existing general chat placeholder behavior still passes.

## Task 7 - Add Three-Round Routing Guard

Implement the first backend version of the three-round fallback rule.

Files:

- `app/graph/state.py`
- `app/graph/routing.py`
- `app/clarification/node.py`
- graph integration tests

State field:

```text
clarification_round_count: int
```

Routing rule:

```text
if intent_type == ambiguous and clarification_round_count < 3:
    route to clarification

if intent_type == ambiguous and clarification_round_count >= 3:
    route to retriever
```

Reset rule:

- The counter should reset when the active request resolves to `document_info` or `general_chat`.
- In milestone 1, document the reset requirement and cover it in graph-level tests where state is passed directly.
- In milestone 2 or the memory branch, make the reset durable across HTTP requests.

Acceptance:

- Round 1, 2, and 3 ambiguous results produce clarification questions.
- The next ambiguous result after count `3` routes to `document_info`/retriever.
- Langfuse route metadata shows when the clarification limit forced the retriever path.

## Task 8 - Add Safe Langfuse Metadata For Clarification

Extend observability without leaking sensitive content.

Files:

- `app/observability/metadata.py`
- `app/clarification/node.py`
- `tests/observability/test_langfuse.py`
- `docs/architecture/observability/observability.md`, if docs are updated in this branch

Add metadata helpers:

- `build_clarification_input_metadata(...)`
- `build_clarification_output_metadata(...)`

Input metadata:

- `intent_type`
- `confidence_score`
- `classification_query_length`
- `messages_count`
- `has_conversation_summary`
- `conversation_summary_length`
- `clarification_round_count`
- `max_clarification_rounds`

Output metadata:

- `clarification_required`
- `reason_code`
- `missing_dimension_count`
- `missing_dimensions`
- `question_length`
- `next_node_after_user_reply: "intent_classifier"`

Privacy:

- Do not capture full messages, full summaries, or full classification queries by default.
- If `LANGFUSE_CAPTURE_TEXT=true`, only capture redacted bounded previews through the existing `_safe_text_preview` path.

Acceptance:

- Observability disabled still no-ops.
- Langfuse failures do not fail clarification.
- Tests verify no full sensitive text is present by default.

## Task 9 - Add Focused Tests

Create a focused test suite before broad integration.

Files:

- `tests/clarification/test_node.py`
- `tests/clarification/test_generator.py`
- `tests/clarification/test_prompts.py`
- `tests/integration/test_intent_retriever_graph.py`
- `tests/observability/test_langfuse.py`

Test cases:

- missing `intent_decision` raises a clear error
- non-ambiguous intent does not silently produce clarification
- ambiguous intent produces an `AIMessage`
- existing messages are preserved and the clarification message is appended
- summary and recent messages are passed to the generator
- `normalized_input` is not required by the node
- multiple missing fields can be represented in one question
- prompt injection text is treated as untrusted
- unnecessary PII request is discouraged
- round counter increments
- round counter limit routes to retriever
- Langfuse metadata captures route/round/outcome without raw text by default

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\clarification tests\integration tests\observability
.\.venv\Scripts\python.exe -m pytest
```

## Task 10 - Milestone 1 Handoff

Before opening a PR, report:

- real clarification node files added
- graph/routing files changed
- state fields changed
- docs updated
- tests run
- limitations:
  - `/chat` may still return the old input-processing response until milestone 2
  - durable message persistence remains for the memory branch
  - response generation still remains separate from clarification

## Milestone 1 Done Means

- The backend graph no longer has an ambiguous placeholder.
- Clarification is a first-class graph node.
- The node follows the narrow architecture contract.
- The clarification question is stored as a normal assistant message.
- Three-round loop protection exists at the graph/state level.
- Langfuse can show that clarification happened without storing private content by default.
- The implementation is ready for API and frontend exposure in milestone 2.
