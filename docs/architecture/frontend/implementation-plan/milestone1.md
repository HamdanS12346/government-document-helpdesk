# Milestone 1 - FastAPI Input Processor Boundary

## Goal

Create the backend API boundary that lets the browser send text and uploaded files to the existing Input Processor without changing the Input Processor contract.

## Scope

This milestone stops at:

```text
FastAPI /chat
  -> InputRequest
  -> process_input()
  -> InputProcessingResult
  -> NormalizedInput printed in backend terminal
```

Do not connect LangGraph, RAG, memory, LLM response generation, or chatbot answer generation in this milestone.

## Tasks

1. Confirm the working branch is `feature/frontend-input-processor`.

2. Confirm the working tree is clean or only contains this frontend integration work.

3. Read the current Input Processor contract in `app/input_processing/schemas.py` and `app/input_processing/processors.py`.

4. Keep the API integration limited to the public boundary:

```python
process_input(
    InputRequest(
        user_query=...,
        attachments=[Attachment(...)]
    )
)
```

5. Check `requirements.txt` for backend API dependencies.

6. Ensure these Python dependencies are present:

```text
fastapi
uvicorn
python-multipart
```

7. Install/update backend dependencies from the existing project virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

8. Create the API package:

```text
app/api/
|-- __init__.py
|-- main.py
`-- routes.py
```

9. Define the FastAPI app in `app/api/main.py`.

10. Add local development CORS in the FastAPI app for:

```text
http://localhost:3000
```

11. Define `POST /chat` in `app/api/routes.py`.

12. Make `/chat` accept `multipart/form-data` with:

```text
message: optional text field
files: zero or more uploaded files
```

13. Read each uploaded file into bytes inside the API route.

14. Convert each upload into the existing `Attachment` model:

```python
Attachment(
    filename=upload.filename,
    media_type=upload.content_type,
    content=file_bytes,
)
```

15. Construct the existing `InputRequest` model:

```python
InputRequest(
    user_query=message,
    attachments=attachments,
)
```

16. Call only `process_input(request)` from the API layer.

17. Do not call `image_processor.py`, `pdf_processor.py`, OCR providers, PDF extractors, or guardrail internals directly from API code.

18. Print successful `result.normalized_input` as pretty JSON in the backend terminal for manual testing.

19. If processing fails, print only the safe `InputProcessingResult` JSON.

20. Return a structured JSON response from `/chat` with:

```text
success
message
attachment_statuses
warnings
normalized_input
```

21. Keep `normalized_input` in the API response for integration testing, but do not require the frontend to render it.

22. Convert known Input Processor failures into safe frontend-facing messages.

23. Return internal unexpected exceptions as a generic safe error.

24. Do not expose stack traces, provider paths, raw bytes, raw document text, credentials, or raw PII in the HTTP response.

25. Do not create an upload directory.

26. Do not persist raw uploads on disk.

27. Do not place FastAPI `UploadFile` objects, raw bytes, or file paths into graph state.

28. Add API tests in a new focused test area such as:

```text
tests/api/
```

29. Test that `/chat` accepts text-only input.

30. Test that `/chat` accepts attachment-only input.

31. Test that `/chat` converts uploaded files into `Attachment` objects before calling `process_input()`.

32. Test that multiple uploaded files are preserved in order.

33. Test that mixed image/PDF attachments are accepted at the API boundary.

34. Test that safe Input Processor failures are returned safely.

35. Test that unexpected exceptions do not leak implementation details.

36. Test that CORS allows `http://localhost:3000`.

37. Start the backend locally:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.api.main:app --reload --host 127.0.0.1 --port 8000
```

38. Manually call `/chat` once with text-only input and confirm the backend terminal prints `NormalizedInput`.

39. Run focused backend/API tests.

40. Run the existing Input Processor tests to confirm behavior was not changed.

## Acceptance Criteria

- `app/api/` exists and contains the FastAPI app and `/chat` route.
- `/chat` uses `InputRequest`, `Attachment`, and `process_input()`.
- Uploads are read as transient bytes and are not persisted.
- `NormalizedInput` prints in the backend terminal on success.
- Safe failures return safe frontend-facing JSON.
- API tests cover the HTTP-to-Input-Processor boundary.
- Existing Input Processor tests still pass.
