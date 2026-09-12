# Milestone 2 - Next.js Frontend and API Integration

## Goal

Create a simple browser UI that can submit text, images, and PDFs to the FastAPI `/chat` endpoint and show clear success, loading, and safe error states.

## Scope

This milestone connects:

```text
Next.js frontend
  -> POST http://localhost:8000/chat
  -> FastAPI
  -> Input Processor
```

The frontend must not call Python modules directly and must not implement its own image/PDF/OCR processing logic.

## Tasks

1. Create the frontend directory at the repository root:

```text
frontend/
```

2. Scaffold a Next.js app inside `frontend/`.

3. Keep Node dependencies inside:

```text
frontend/package.json
frontend/package-lock.json
```

4. Do not add frontend dependencies to Python `requirements.txt`.

5. Confirm the frontend dev server runs on:

```text
http://localhost:3000
```

6. Create a minimal chat screen as the first screen of the app.

7. Include a multiline text input for the user message.

8. Include a file picker that accepts:

```text
.png
.jpg
.jpeg
.pdf
```

9. Allow multiple file selection.

10. Show selected file names before submission.

11. Allow these request shapes:

```text
text only
single image
single PDF
multiple images
multiple PDFs
mixed image/PDF files
text with attachments
attachment only
```

12. Prevent submitting an empty request when there is no text and no selected file.

13. Build a `FormData` request on submit.

14. Append text as:

```text
message
```

15. Append files using the field name expected by the FastAPI route.

16. Send the request to:

```text
http://localhost:8000/chat
```

17. Add a loading state while the request is processing.

18. Disable duplicate submits while processing.

19. Show a success state when the API returns `success: true`.

20. The success state should be simple, for example:

```text
Input processed successfully.
```

21. Do not render the full `NormalizedInput` object in the frontend in this milestone.

22. Show safe attachment-level errors returned by the API.

23. Show a clear complete-failure error when the API returns `success: false`.

24. Show a safe network/server error if FastAPI is not running.

25. Do not show Python stack traces or raw backend exception details.

26. Keep raw files in browser state only long enough to submit them.

27. Clear or preserve the form after success based on the simplest implementation that supports repeated manual testing.

28. Add lightweight frontend structure under `frontend/` only.

29. Avoid modifying existing backend/Input Processor files unless needed to match the agreed `/chat` boundary.

30. Start FastAPI in one terminal:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.api.main:app --reload --host 127.0.0.1 --port 8000
```

31. Start Next.js in another terminal:

```powershell
cd frontend
npm run dev
```

32. Open the browser at:

```text
http://localhost:3000
```

33. Submit a text-only request and confirm the frontend success state appears.

34. Confirm the backend terminal prints the `NormalizedInput`.

35. Submit a valid image and confirm the request reaches the Input Processor.

36. Submit a valid PDF and confirm the request reaches the Input Processor.

37. Submit mixed image/PDF files and confirm the API returns a safe result.

38. Submit an unsupported file type and confirm the frontend shows the safe error.

39. Stop FastAPI and submit once to confirm the frontend shows a safe connection/server error.

## Acceptance Criteria

- `frontend/` exists at the repository root.
- The frontend runs locally on `localhost:3000`.
- The frontend submits multipart requests to FastAPI on `localhost:8000`.
- Text, image, PDF, mixed, and attachment-only requests can be manually tested from the browser.
- Loading, success, complete failure, attachment failure, and network error states are visible.
- The frontend does not render raw `NormalizedInput` in the UI.
- Backend terminal output remains the debugging surface for `NormalizedInput`.
