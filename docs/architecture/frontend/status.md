# Frontend Integration Status

## Current Branch

```text
feature/frontend-input-processor
```

This branch follows the `feature/*` workflow from `INSTRUCTIONS.md`.

## Current Goal

Integrate the existing Input Processor with a browser-facing frontend/API path.

Current milestone:

```text
Milestone 1 - FastAPI Input Processor Boundary
```

The milestone stops at:

```text
FastAPI /chat
  -> InputRequest
  -> process_input()
  -> InputProcessingResult
  -> NormalizedInput printed in backend terminal
```

LangGraph, RAG, LLM response generation, memory, and final chatbot answers are still out of scope.

## Completed So Far

Milestone 1 tasks completed:

```text
1. Confirmed branch is feature/frontend-input-processor.
2. Checked working tree scope during the task flow.
3. Reviewed Input Processor public contract.
4. Confirmed API must use only the public Input Processor boundary.
5. Checked requirements.txt for API dependencies.
6. Added python-multipart to requirements.txt.
7. Confirmed fastapi, uvicorn, and python-multipart are installed in .venv.
8. Created app/api package.
9. Defined FastAPI app in app/api/main.py.
10. Added local CORS for http://localhost:3000.
11. Added POST /chat route.
12. Made /chat accept multipart form data.
13. Read uploaded files into transient bytes.
14. Converted uploads into Attachment models.
15. Constructed InputRequest.
16. Called process_input(request).
17. Confirmed no direct API calls to image/PDF/OCR internals.
18. Printed successful NormalizedInput to backend terminal.
19. Printed safe InputProcessingResult JSON for failures.
20. Returned structured JSON from /chat.
21. Kept normalized_input in API response for integration testing.
22. Converted known failures into safe frontend-facing messages.
23. Returned unexpected exceptions as generic safe errors.
24. Confirmed no stack traces, raw bytes, provider paths, credentials, or raw PII are exposed by the API response.
25. Confirmed no upload directory is created.
26. Confirmed raw uploads are not persisted on disk.
27. Confirmed UploadFile/raw bytes/file paths are not placed into graph state.
28. Added tests/api test area.
29. Tested text-only input.
30. Tested attachment-only input.
31. Tested upload-to-Attachment conversion.
32. Tested multiple uploaded files preserve order.
33. Tested mixed image/PDF uploads at the API boundary.
34. Tested safe Input Processor failures cross the API boundary safely.
35. Tested unexpected exceptions do not leak implementation details.
36. Tested CORS allows http://localhost:3000.
37. Started backend locally with Uvicorn.
38. Manually called /chat and confirmed backend terminal prints NormalizedInput.
39. Ran focused API tests.
40. Ran existing Input Processor tests.
```

## Files Added Or Changed

```text
app/api/__init__.py
app/api/main.py
app/api/routes.py
tests/api/test_chat.py
requirements.txt
docs/architecture/frontend/implementation-plan/milestone1.md
docs/architecture/frontend/implementation-plan/milestone2.md
docs/architecture/frontend/implementation-plan/milestone3.md
docs/architecture/frontend/frontend-integration.md
docs/architecture/frontend/status.md
```

Note: the frontend docs folder was already being worked on in this branch. Keep future changes scoped to frontend/API integration unless explicitly approved.

## Current API Behavior

Endpoint:

```text
POST /chat
```

Accepted request:

```text
multipart/form-data
message: optional text field
files: optional repeated upload field
```

Current flow:

```text
UploadFile
  -> await file.read()
  -> Attachment(filename, media_type, content)
  -> InputRequest(user_query, attachments)
  -> process_input(request)
  -> InputProcessingResult
  -> JSON response
```

The API response includes:

```text
success
message
attachment_statuses
warnings
normalized_input
```

`normalized_input` is intentionally returned for integration testing in Milestone 1, but the frontend should not display the full raw object in Milestone 2.

## Safety Boundaries Preserved

- The API calls only `process_input()` plus `Attachment` and `InputRequest`.
- The API does not call image processor, PDF processor, OCR provider, or guardrail internals.
- Uploads are read as transient bytes.
- No upload directory is created.
- Raw uploads are not persisted.
- No graph state is written in this milestone.
- Unexpected exceptions return a generic safe error.
- Stack traces and internal details are not exposed in HTTP responses.

## Verified Commands

Focused API tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\api
```

Result:

```text
8 passed, 1 warning
```

Existing Input Processor tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\input-processor
```

Result:

```text
393 passed, 2 skipped
```

Backend manual run:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.api.main:app --host 127.0.0.1 --port 8000
```

Verified:

```text
GET /docs -> 200
POST /chat text-only -> 200
backend terminal printed NormalizedInput JSON
```

## Current Git Notes

Latest local commits at the time of this status update:

```text
dd48c7d feat: add FastAPI input processor boundary
077352d feat: add FastAPI input processor boundary
3f2c0b2 docs: create the implementation-plan for frontend integration
```

There are two commits with the same message. This is not a functional problem, but the history can be cleaned up later if desired.

## Next Recommended Work

Start Milestone 2:

```text
Next.js Frontend and API Integration
```

Next tasks should begin with:

```text
1. Create frontend/ at the repository root.
2. Scaffold a Next.js app inside frontend/.
3. Keep Node dependencies under frontend/.
4. Build the minimal chat/upload UI.
5. Connect the UI to POST http://localhost:8000/chat.
```

Before starting the next milestone, check:

```powershell
git status --short --branch
```

Keep implementation scoped to:

```text
frontend/
app/api/
tests/api/
requirements.txt only if backend dependency changes are needed
README/docs only when documenting verified behavior
```
