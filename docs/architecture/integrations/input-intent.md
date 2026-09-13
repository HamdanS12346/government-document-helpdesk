# Input Processor To Intent Classifier Integration

## Purpose

This document captures the integration plan for the first workflow slice:

```text
Input Processor
  -> normalized_input
  -> Intent Classifier
  -> intent_decision
```

The goal is to connect the existing Input Processor handoff to the existing Intent Classifier without changing either component's core contract. This slice prepares the graph for later routing, retrieval, clarification, context building, and response generation, but does not implement those later nodes.

## Current Findings

The Input Processor is already the owner of raw user text and upload bytes. Its public boundary is `InputRequest -> InputProcessingResult`, and successful results include one downstream handoff object: `NormalizedInput`.

The Intent Classifier is already implemented as a state-based node. It reads `normalized_input`, optional `messages`, and optional `conversation_summary`, builds a bounded classification query, invokes an injected classifier provider, validates the result, and writes only `intent_decision`.

The shared `GraphState` already has the fields required for this slice:

```text
normalized_input
intent_decision
documents
retrieved_context
messages
conversation_summary
```

The current frontend is already connected to the Input Processor through the FastAPI `/chat` route:

```text
Frontend
  -> FastAPI /chat
  -> process_input()
  -> normalized_input returned/debug printed
```

The next integration target is to keep that same frontend path, but continue from successful input processing into the intent graph:

```text
Frontend
  -> FastAPI /chat
  -> process_input()
  -> normalized_input
  -> input-intent graph
  -> intent_decision
  -> backend terminal prints normalized_input and intent_decision
```

For this development/debug slice, the frontend does not need to change its request shape. It can keep sending the same multipart `FormData` to `/chat`. The backend route should add the graph invocation after successful input processing.

## Boundary Rules

Raw upload bytes must remain outside graph state. API upload objects, temporary paths, OCR providers, PDF internals, and `InputProcessingResult` must not be inserted into `GraphState`.

Only successful input processing should invoke intent classification. If `result.success` is false or `result.normalized_input` is missing, the graph slice should not run.

Partial attachment failures may still produce `success=True` with a valid `normalized_input`. In that case, the graph can classify using the successful user query and successful attachment previews. Failed attachment errors remain in the API/input-processing response metadata, not in graph state.

For the first frontend integration, conversation memory is out of scope. The API should not invent message history or summaries. `messages` and `conversation_summary` can be omitted from graph input, or passed as empty values only if the graph helper requires them. Real message history and summarization should be added later by the memory component.

## State Contract

### Input Processor Write

Use the existing helper:

```python
from app.input_processing.processors import build_graph_state_update

state_update = build_graph_state_update(result)
```

For successful results, this returns:

```python
{"normalized_input": result.normalized_input}
```

For failed results, this returns:

```python
{}
```

### Intent Classifier Read

The classifier reads:

```text
normalized_input.user_query
normalized_input.image_content[*].image_name
normalized_input.image_content[*].preview
normalized_input.pdf_content[*].pdf_name
normalized_input.pdf_content[*].preview
messages
conversation_summary
```

For the first `/chat` integration, only `normalized_input` is expected to be populated. `messages` and `conversation_summary` remain future-ready state fields and should not block this slice.

The classifier intentionally does not read `combined_text`, `image_content[*].extracted_text`, or `pdf_content[*].extracted_text`. It uses previews because intent classification only needs a bounded signal.

### Intent Classifier Write

The classifier writes:

```python
{"intent_decision": IntentDecision(...)}
```

The decision contains:

```text
query
intent_type
confidence_score
```

The `query` field is the exact bounded query constructed by the intent node, not raw upload content and not a provider-specific placeholder.

## Graph Slice

`app/graph/graph.py` now owns the current graph assembly for this slice.

The graph starts from `GraphState` that already contains `normalized_input`:

```text
START
  -> intent_classifier
  -> END
```

This intentionally keeps raw input processing outside LangGraph for now. The API or future application composition layer should:

1. Build `InputRequest` from HTTP input.
2. Call `process_input()`.
3. Return input errors immediately if processing failed.
4. Convert successful results to graph state with `build_graph_state_update()`.
5. Invoke the graph.
6. Print both `normalized_input` and `intent_decision` in the backend terminal for local verification.

The graph slice should not receive raw frontend payloads. It starts after input processing has produced a valid `NormalizedInput`.

## Provider Injection

The graph builder receives an `IntentClassifier` implementation:

```python
graph = build_input_intent_graph(classifier)
```

This keeps the graph independent from a specific model provider. Production can inject `OpenAIIntentClassifier`, while tests can inject a fake classifier.

The intent node should continue not to read environment variables, create API clients, or store provider details in state. Provider construction belongs at the application composition boundary.

## Current Implementation Shape

The graph module exposes:

```python
build_input_intent_graph(classifier)
```

Builds and compiles the LangGraph slice from `normalized_input` to `intent_decision`.

```python
invoke_input_intent_graph(
    result,
    classifier,
    messages=None,
    conversation_summary=None,
)
```

Bridges from a successful `InputProcessingResult` into the graph. This is useful for tests, local scripts, and a future API integration path. It rejects failed input results before the classifier can run.

## Frontend And API Integration Plan

The existing browser flow is already useful for this slice:

```text
Next.js frontend
  -> POST http://localhost:8000/chat
  -> FastAPI reads message/files
  -> InputRequest
  -> process_input()
```

The next backend change should extend `app/api/routes.py` after `process_input(request)` succeeds:

```text
if input processing failed:
  return the current safe input-processing response

if input processing succeeded:
  build/invoke the input-intent graph
  print normalized_input JSON
  print intent_decision JSON
  return the current response payload, optionally including intent_decision for debug
```

For the immediate goal, terminal visibility is the main requirement. When running the frontend locally and submitting text/files, the backend terminal should show:

```text
Normalized input:
{ ... }

Intent decision:
{ ... }
```

The route can keep returning the existing `normalized_input` response to the frontend until the team decides the API response contract. If adding `intent_decision` to the JSON response is useful during local development, it should be treated as an explicit temporary/debug response shape and covered by API tests.

The frontend request does not need to change for this slice. It should continue to send:

```text
message
files
```

The backend owns the integration from `normalized_input` to `intent_decision`.

### Provider Construction

For local frontend testing with real model calls, the API composition layer needs a real classifier:

```python
classifier = OpenAIIntentClassifier()
```

`OpenAIIntentClassifier` reads model credentials through the environment used by LangChain/OpenAI, including `OPENAI_API_KEY` from local `.env`. The key must not be printed, returned, or inserted into graph state.

For automated API tests, use a fake classifier or monkeypatch the graph invocation. Tests should not require `OPENAI_API_KEY` and should not make network calls.

### Error Behavior

If input processing fails, do not call the intent classifier.

If intent classification fails during this debug slice, the backend should return a safe generic error or a controlled debug response. Do not expose provider stack traces, API keys, raw upload bytes, or full private document text.

Recommended safe message:

```text
The request could not be classified right now. Please try again.
```

## Future-Ready Handoff

Later graph work can extend the graph after `intent_classifier` with conditional routing:

```text
intent_decision.intent_type == "document_info"
  -> retriever
  -> context_builder
  -> response

intent_decision.intent_type == "ambiguous"
  -> clarification
  -> intent_classifier

intent_decision.intent_type == "general_chat"
  -> response
```

This slice should not add placeholder state fields or fake outputs for future nodes. The existing `GraphState` already contains the future fields: `documents`, `retrieved_context`, `messages`, and `conversation_summary`.

## Testing Plan

The integration tests should stay offline and deterministic by injecting a fake classifier.

Coverage for this slice:

- A compiled graph accepts `normalized_input` and returns `intent_decision`.
- The graph can run with only `normalized_input`; `messages` and `conversation_summary` are optional future context.
- The classifier query includes attachment previews and excludes full extracted text.
- The bridge rejects failed `InputProcessingResult` objects and does not call the classifier.
- The `/chat` route invokes the graph only after successful input processing.
- The `/chat` route prints both `normalized_input` and `intent_decision` for successful requests.
- API tests use fake classifier behavior and do not call OpenAI.
- Full test suite should pass after wiring.

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_input_intent_graph.py -q
.\.venv\Scripts\python.exe -m pytest
```

## API Response Contract Decision

The `/chat` route can be wired for terminal debugging now, but the final response contract still needs a team decision:

- Should `/chat` continue returning the input-processing debug payload?
- Should it return `intent_decision` alongside `normalized_input` during the integration phase?
- Should provider failures become safe HTTP responses before final response generation exists?
- Where should the real `OpenAIIntentClassifier` be constructed and reused?

Until those decisions are made, the safest implementation is:

- Keep the frontend request unchanged.
- Keep the existing input-processing response mostly unchanged.
- Add backend terminal printing for `intent_decision`.
- Add `intent_decision` to the JSON response only if the team explicitly wants frontend-visible debug output.

## Prompt Note For Later

The intent prompt should eventually mention the supported knowledge-base document families, but unsupported government-document questions should still classify as `document_info`, not `general_chat`. Whether the knowledge base can answer a request should be handled by retrieval/response behavior, not by changing the broad intent meaning.
