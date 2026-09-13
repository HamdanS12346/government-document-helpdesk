# Milestone 2: Frontend-To-Intent Terminal Debug Flow

## Goal

Extend the existing frontend-backed `/chat` flow so a user can submit a message or file from the browser, the backend processes it, runs intent classification, and prints both the normalized input and intent decision in the FastAPI terminal.

This milestone connects:

```text
Frontend
  -> FastAPI /chat
  -> Input Processor
  -> input-intent graph
  -> terminal debug output
```

The frontend request shape should not change.

## Target Flow

```text
Next.js frontend sends multipart FormData
  -> app/api/routes.py reads message/files
  -> InputRequest
  -> process_input()
  -> if failed: return current safe input response
  -> if successful: invoke input-intent graph
  -> print normalized_input JSON
  -> print intent_decision JSON
  -> return current API response shape unless debug response is approved
```

## Tasks

### 1. Confirm The Existing Frontend/API Boundary

Review the current `/chat` route in `app/api/routes.py`.

It currently:

- Accepts `message` as form text.
- Accepts `files` as uploaded files.
- Reads file bytes at the HTTP boundary.
- Builds `InputRequest`.
- Calls `process_input(request)`.
- Prints `normalized_input` or the failed input result.
- Returns the input-processing response payload.

Keep this request path unchanged so the frontend can continue working without UI changes.

### 2. Construct The Real Intent Provider At The API Boundary

For local frontend testing, the API needs to use the real classifier:

```python
OpenAIIntentClassifier()
```

Construction should happen at the API/composition boundary, not inside `classify_intent()`.

The implementation must not:

- Hardcode `OPENAI_API_KEY`.
- Print the API key.
- Put provider objects into graph state.
- Put credentials into API responses.

The provider should rely on environment loading already available to the running process. Local testing requires `OPENAI_API_KEY` in `.env` or the shell environment.

### 3. Invoke The Graph Only After Successful Input Processing

After:

```python
result = process_input(request)
```

check:

```text
result.success is true
result.normalized_input is not None
```

Only then invoke the input-intent graph.

If input processing fails, keep the current safe input-processing response and do not call OpenAI.

### 4. Keep Message History Out For Now

For this milestone, do not add real conversation memory.

When invoking the graph from `/chat`, pass only the successful input result and classifier. Leave `messages` and `conversation_summary` omitted unless a helper requires explicit empty values.

This means the first integrated classifier decision is based only on:

- `normalized_input.user_query`
- image previews
- PDF previews

Conversation memory can be added later by the memory component.

### 5. Print Debug Output In The Backend Terminal

For successful input processing and successful intent classification, print both objects clearly:

```text
Normalized input:
{ ... }

Intent decision:
{ ... }
```

Use Pydantic JSON output for readability.

Do not print:

- raw upload bytes
- API keys
- provider request headers
- stack traces as user-facing responses

### 6. Decide The Temporary API Response Shape

The safest first implementation is to keep the existing response body mostly unchanged:

```text
success
message
attachment_statuses
warnings
normalized_input
```

If the team wants frontend-visible debug output, add:

```text
intent_decision
```

If `intent_decision` is added to the JSON response, update API tests to lock that shape. Otherwise, keep intent visible only in the terminal for this milestone.

### 7. Handle Intent Provider Failures Safely

Intent classification can fail because of:

- missing `OPENAI_API_KEY`
- invalid credentials
- network errors
- rate limits
- model/provider errors
- malformed structured output

For this milestone, return a controlled safe response if classification fails. Recommended user-facing message:

```text
The request could not be classified right now. Please try again.
```

Do not expose provider tracebacks or sensitive request details through HTTP responses.

### 8. Add API Tests Without Real OpenAI Calls

Update or add API tests for the `/chat` route.

Tests should use monkeypatching or fake classifier behavior so they stay offline.

Coverage should prove:

- Successful input processing invokes intent classification.
- Failed input processing does not invoke intent classification.
- The route prints or reaches both normalized input and intent decision behavior.
- Provider failure returns a safe response.
- Existing attachment status and warning behavior is preserved.
- The frontend request format remains `message` plus `files`.

Tests must not require `.env`, `OPENAI_API_KEY`, or network access.

### 9. Run The Full Local Flow

Start the backend:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.api.main:app --reload --host 127.0.0.1 --port 8000
```

Start the frontend:

```powershell
cd frontend
npm.cmd run dev
```

Submit a message from the browser.

Expected backend terminal output:

```text
Normalized input:
{
  "user_query": "...",
  "image_content": [],
  "pdf_content": [],
  "combined_text": "..."
}

Intent decision:
{
  "query": "...",
  "intent_type": "general_chat | document_info | ambiguous",
  "confidence_score": ...
}
```

For file uploads, the intent query should use the attachment previews, while `combined_text` remains available in `normalized_input`.

### 10. Run Automated Verification

Run focused API tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/api -q
```

Run graph integration tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_input_intent_graph.py -q
```

Run the full backend suite:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## Done Criteria

Milestone 2 is complete when:

- The frontend can submit the same current request to `/chat`.
- `/chat` still processes input through the Input Processor.
- Successful input processing invokes the input-intent graph.
- Backend terminal prints both `normalized_input` and `intent_decision`.
- Failed input processing does not call the classifier.
- Classification failures produce safe behavior.
- API tests pass without real OpenAI calls.
- Full backend tests pass.

## Out Of Scope

- Building final assistant responses.
- Routing to RAG or response generation.
- Adding conversation memory.
- Adding frontend UI for intent decisions.
- Changing the `IntentDecision` or `NormalizedInput` contracts.
- Deciding permanent API response shape.
