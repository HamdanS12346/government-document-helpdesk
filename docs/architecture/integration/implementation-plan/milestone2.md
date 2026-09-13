# Milestone 2: API, Frontend, and Live Terminal Verification

## Goal

Create the second implementation phase for making a real frontend request flow
through the new intent-to-retriever graph and show retrieved documents in the
backend terminal.

By the end of this milestone, a developer can submit a document-info request
from the Next.js frontend, the FastAPI backend can make real live calls through
the classifier and retriever stack, and the terminal can show:

```text
Normalized input
Intent decision
Documents
```

The workflow still stops after documents for now. Response generation,
clarification, memory, and context building remain placeholders or later work.

## Starting State

This milestone starts after Milestone 1:

```text
Frontend chat
  -> FastAPI /chat
  -> Input Processor
  -> normalized_input
  -> Intent Classifier
  -> intent_decision
  -> routing
  -> Retriever, only for document_info
  -> documents
  -> END
```

The graph supports all three intent branches:

```text
document_info -> retriever -> END
general_chat  -> general_chat_placeholder -> END
ambiguous     -> clarification_placeholder -> END
```

Automated tests use fakes and do not make live provider calls.

## Target State

A local manual run should support this flow:

```text
Next.js frontend
  -> multipart request to FastAPI /chat
  -> process_input(request)
  -> print Normalized input
  -> invoke_intent_retriever_graph(...)
  -> print Intent decision
  -> print Documents when present
  -> return current public API response shape
```

For this phase, the frontend does not need to display retrieved documents in
the browser. The backend terminal is the verification surface.

## Phase Tasks

### 1. Switch FastAPI to the New Graph Bridge

Update the `/chat` route to import and call:

```python
invoke_intent_retriever_graph
```

instead of:

```python
invoke_input_intent_graph
```

Keep the current input-processing response shape unless a separate API contract
change is intentionally planned.

Continuity note: the route boundary owns debug printing. Keep graph nodes free
of terminal logging.

### 2. Keep Input Processing as the First Boundary

The route should continue to:

- Build the input-processing request from frontend text/files.
- Run `process_input(request)`.
- Stop with the existing input-processing error behavior if input processing
  fails.
- Pass the successful `InputProcessingResult` into the graph bridge.

Continuity note: the graph still starts after input processing, so raw frontend
multipart details should not leak into graph node code.

### 3. Print Normalized Input

After successful input processing, print the normalized input in the backend
terminal.

Use the existing project JSON/Pydantic dump style so the output is readable and
safe for local debugging.

Expected section:

```text
Normalized input:
...
```

Continuity note: this confirms the exact text and attachment extraction passed
into the graph.

### 4. Print Intent Decision

After graph execution, print the final `intent_decision`.

Expected section:

```text
Intent decision:
...
```

Continuity note: this confirms which branch the graph selected before checking
whether retrieval ran.

### 5. Print Documents for Document-Info Requests

When the final graph state contains `documents`, print them in the backend
terminal.

Expected section:

```text
Documents:
...
```

For `general_chat` and `ambiguous`, either do not print `Documents` or print a
clear empty placeholder. Prefer not printing the section unless the key exists.

Continuity note: this is the temporary endpoint for the integrated slice until
Context Builder and Response Node are available.

### 6. Preserve Error Behavior

If graph classification or routing fails, keep returning the existing
classification error payload from `/chat`.

API tests should cover this by patching the graph bridge to raise an error.

Continuity note: users should not receive raw stack traces or partial internal
state from this milestone.

### 7. Add API Integration Tests

Add or update tests under `tests/integration/` and `tests/api/` as appropriate.

Use patched/fake components. Do not make live calls in automated tests.

Coverage should include:

- `/chat` calls `invoke_intent_retriever_graph()` after successful input
  processing.
- `/chat` still returns the current public response shape.
- A fake final state with `documents` does not expose raw retrieved documents
  unless the current API contract already does so.
- Graph bridge errors return the existing classification error payload.
- Non-document branches complete without a `documents` state requirement.

Continuity note: API tests protect the public contract while terminal output is
used for temporary local verification.

### 8. Add Manual Live Verification Checklist

Document the local commands and expected terminal sections for a live run.

Backend:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.api.main:app --reload --host 127.0.0.1 --port 8000
```

Frontend:

```powershell
cd frontend
npm.cmd run dev
```

Open:

```text
http://localhost:3000
```

Submit:

```text
What documents are required for PAN application?
```

Expected route:

```text
document_info -> retriever -> END
```

Expected backend terminal sections:

```text
Normalized input:
Intent decision:
Documents:
```

Continuity note: this checklist is for intentional live verification with real
configured providers and local environment variables.

### 9. Verify Placeholder Branches Manually

Submit a general-chat request:

```text
Hello, how are you?
```

Expected route:

```text
general_chat -> general_chat_placeholder -> END
```

Expected terminal sections:

```text
Normalized input:
Intent decision:
```

Submit an ambiguous request:

```text
Can you check this?
```

Expected route:

```text
ambiguous -> clarification_placeholder -> END
```

Expected terminal sections:

```text
Normalized input:
Intent decision:
```

Continuity note: these branches prove routing is ready without pretending that
response or clarification behavior exists.

### 10. Run Final Test Pass

Run integration tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration
```

Run API tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/api
```

Run the full backend suite:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Run frontend lint if the frontend request path changed:

```powershell
cd frontend
npm.cmd run lint
```

Continuity note: live manual verification complements tests but does not replace
deterministic automated coverage.

## Done Criteria

Milestone 2 is complete when:

- `/chat` uses `invoke_intent_retriever_graph()`.
- A frontend request can trigger real Input Processor, Intent Classifier, and
  Retriever calls in local development.
- The backend terminal prints `Normalized input`, `Intent decision`, and
  `Documents` for a `document_info` request.
- The workflow intentionally stops after retrieved documents.
- `general_chat` and `ambiguous` route to placeholders and end cleanly.
- Automated tests cover API integration using fakes.
- Live provider calls are kept out of automated tests.

## Out of Scope

- Do not make the browser render final assistant answers from retrieved
  documents.
- Do not add Context Builder.
- Do not add Response Node.
- Do not add Clarification Node behavior.
- Do not add Memory behavior.
- Do not change shared contracts unless a concrete field is required and the
  matching docs/tests are updated.
