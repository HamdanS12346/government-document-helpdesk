# Frontend Summary

The frontend integration currently provides a local Next.js chat screen for testing the existing Input Processor through the FastAPI `/chat` endpoint.

Completed frontend work:

- Created `frontend/` as an isolated Next.js app.
- Kept Node dependencies in `frontend/package.json` and `frontend/package-lock.json`.
- Built a simple document chat UI as the first screen.
- Added a multiline message input.
- Added a file picker for `.png`, `.jpg`, `.jpeg`, and `.pdf`.
- Supported multiple attachments and mixed image/PDF uploads.
- Supported text-only, attachment-only, and text-with-attachment requests.
- Sends multipart `FormData` to `http://localhost:8000/chat`.
- Shows loading, success, complete-failure, warning, attachment-error, and backend-unavailable states.
- Prevents empty submissions and duplicate submits while processing.
- Does not render the raw `NormalizedInput` object in the browser.
- Sanitizes displayed backend messages to avoid exposing Python stack traces or internal details.

Current local frontend command:

```powershell
cd frontend
npm.cmd run dev
```

Frontend runs at:

```text
http://localhost:3000
```
