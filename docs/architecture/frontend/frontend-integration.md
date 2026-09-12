# Frontend Integration

## 1. Purpose

This document defines the agreed architecture and integration boundary for adding a basic frontend to the Government Document Helpdesk Chatbot.

The immediate purpose is to provide a real browser-based way to test the existing Input Processor instead of testing it only through the current manual test runner.

The eventual purpose is to establish the permanent frontend-to-application architecture:

```text
Next.js Frontend
       ↓
FastAPI API
       ↓
LangGraph Application
       ↓
Input Processing / RAG / LLM / Guardrails / etc.
```

For the first implementation milestone, LangGraph is **not connected yet**. The first milestone ends at the Input Processor and `NormalizedInput`.

---

## 2. Decision Status

**Status: Confirmed**

The following decisions have been explicitly agreed upon:

- Frontend framework: **Next.js**
- Backend/API framework: **FastAPI**
- Frontend location: repository root under `/frontend`
- FastAPI location: `/app/api`
- Python environment: existing project `.venv`
- Frontend development server: `localhost:3000`
- FastAPI development server: `localhost:8000`
- CORS: enabled for local frontend-to-API communication
- Authentication: not required for this development milestone
- Upload persistence: no persistent upload storage
- Upload handling: read uploaded files as bytes and construct the existing `Attachment` contract
- API boundary: FastAPI constructs `InputRequest` and calls the public `process_input()` function
- Input Processor internals must not be called directly by the frontend/API layer
- First milestone does not invoke LangGraph
- First milestone returns `NormalizedInput` through the API and prints it in the backend terminal
- Frontend does not display the `NormalizedInput` object in the first milestone
- Input Processor errors are returned through the API and displayed by the frontend
- The architecture is intended to become the permanent application architecture
- Work must be developed on a separate Git branch and submitted through a PR
- Branch name: `feature/frontend-input-processor`

---

## 3. Current Project State

At the start of this work:

- The frontend does not yet exist.
- The `frontend/` directory has not yet been created.
- FastAPI has not yet been installed.
- FastAPI has not yet been added to `requirements.txt`.
- The feature branch has not yet been created.
- LangGraph pipeline implementation beyond the Input Processor does not yet exist.
- The Input Processor already exists and is tested independently.

The Input Processor provides the public boundary:

```text
InputRequest
     ↓
process_input()
     ↓
InputProcessingResult
     ↓
NormalizedInput
```

The API integration must use this public boundary rather than depending on modality-specific processors.

---

## 4. Target Repository Structure

The intended repository structure after the initial integration work is:

```text
govt-document-helpdesk/
│
├── app/
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py
│   │
│   ├── input_processing/
│   │   ├── processors.py
│   │   ├── schemas.py
│   │   ├── errors.py
│   │   ├── image_processor.py
│   │   ├── pdf_processor.py
│   │   ├── ocr_provider.py
│   │   └── preview.py
│   │
│   └── ...
│
├── frontend/
│   ├── package.json
│   ├── ...
│   └── ...
│
├── guardrails/
├── tests/
├── docs/
├── evaluation/
│
├── requirements.txt
├── README.md
└── ...
```

The exact Next.js-generated file structure may vary according to the selected setup, but the frontend must remain isolated under `/frontend`.

---

## 5. Architectural Boundary

The frontend must not communicate directly with Python modules.

The boundary is:

```text
┌─────────────────────────────┐
│          Next.js            │
│        localhost:3000       │
│                             │
│  Chat UI                    │
│  Text input                 │
│  File selection             │
└──────────────┬──────────────┘
               │
               │ HTTP
               │ multipart/form-data
               ▼
┌─────────────────────────────┐
│          FastAPI            │
│        localhost:8000       │
│                             │
│  /chat                      │
│  HTTP validation            │
│  HTTP → InputRequest        │
└──────────────┬──────────────┘
               │
               │ InputRequest
               ▼
┌─────────────────────────────┐
│       Input Processor       │
│                             │
│  Validation                 │
│  Image processing           │
│  PDF processing             │
│  OCR                        │
│  PII masking                │
│  Normalization              │
└──────────────┬──────────────┘
               │
               │ InputProcessingResult
               ▼
┌─────────────────────────────┐
│      NormalizedInput        │
└──────────────┬──────────────┘
               │
               ├── print to backend terminal
               │
               └── return through FastAPI
                       │
                       ▼
                  Next.js frontend
```

Later:

```text
FastAPI
   ↓
Input Processor
   ↓
NormalizedInput
   ↓
LangGraph
   ↓
ResponsePackage
   ↓
FastAPI
   ↓
Next.js
```

The frontend must not become responsible for orchestrating the AI pipeline.

---

## 6. First Implementation Milestone

The first milestone is intentionally limited.

### Required flow

```text
User
 ↓
Next.js
 ↓
POST /chat
 ↓
FastAPI
 ↓
construct InputRequest
 ↓
process_input()
 ↓
InputProcessingResult
 ↓
print NormalizedInput to terminal
 ↓
return result through HTTP
 ↓
Next.js
```

LangGraph, RAG, LLM generation, conversation memory, and final chatbot response generation are **out of scope for this milestone**.

The purpose is to establish and verify the external boundary around the already-existing Input Processor.

---

## 7. Supported Input

The frontend must expose the capabilities already supported by the Input Processor rather than creating a second, conflicting modality contract.

The frontend/API integration must support:

- text input
- PNG images
- JPEG/JPG images
- PDF files
- multiple attachments
- mixed image/PDF attachments
- text with attachments
- attachment-only requests

The API must not implement its own independent modality-processing logic.

The Input Processor remains responsible for:

- input validation
- supported modality validation
- file-signature validation
- file-size validation
- PDF page-count validation
- image processing
- PDF processing
- OCR
- PII detection/masking
- document-content safety handling
- normalization
- attachment-level failures

---

## 8. Frontend Responsibilities

The initial Next.js frontend is intentionally simple.

It should provide:

1. A basic chat interface.
2. A text input field.
3. A file selection/upload control.
4. Support for the Input Processor's supported image/PDF attachments.
5. Ability to submit text, attachments, or both.
6. A processing/loading state.
7. A success state.
8. An error state.
9. Display of safe backend/Input Processor errors.

The frontend must **not** display the full `NormalizedInput` object in this first milestone.

The backend terminal is the debugging/testing surface for `NormalizedInput`.

Example frontend success state:

```text
Input processed successfully ✓
```

Example frontend failure state:

```text
The selected PDF exceeds the supported page limit.
```

The frontend must not expose internal Python stack traces or implementation details.

---

## 9. FastAPI Responsibilities

FastAPI is the HTTP boundary between the browser and the Python application.

FastAPI responsibilities:

- expose the `/chat` endpoint
- accept text and file uploads
- receive multipart form data
- read uploaded file contents as bytes
- construct the existing `Attachment` objects
- construct the existing `InputRequest`
- call `process_input()`
- print the resulting normalized input to the backend terminal
- convert the processing result into an HTTP response
- return safe structured errors
- configure development CORS

FastAPI must not contain:

- OCR implementation
- PDF parsing logic
- image-processing logic
- PII detection implementation
- RAG logic
- LangGraph orchestration
- LLM generation
- chatbot reasoning

The API layer is an adapter between HTTP and the existing application contract.

---

## 10. InputRequest Construction

The API must translate HTTP upload objects into the existing Input Processor contract.

Conceptually:

```text
HTTP request
    │
    ├── user message
    │
    └── uploaded files
           │
           ▼
      FastAPI upload objects
           │
           ▼
       read bytes
           │
           ▼
Attachment(
    filename=...,
    media_type=...,
    content=...
)
           │
           ▼
InputRequest(
    user_query=...,
    attachments=[...]
)
           │
           ▼
process_input()
```

The API must not pass FastAPI-specific upload objects into the Input Processor.

The API must not pass filesystem paths into the Input Processor.

The Input Processor's existing public contract remains unchanged.

---

## 11. Upload Lifecycle

Uploads are transient.

The intended lifecycle is:

```text
Browser
   ↓
FastAPI
   ↓
read uploaded bytes
   ↓
InputRequest
   ↓
Input Processor
   ↓
processing complete
   ↓
raw upload no longer needed
```

The API must not establish a permanent upload directory or document store.

The API should read file contents into memory and pass the bytes through the existing `Attachment.content` field.

If an internal processing provider requires temporary filesystem access, that must remain inside the appropriate processing/lifecycle boundary and must follow the existing cleanup requirements.

The API itself must not persist user uploads.

---

## 12. Privacy Boundary

Uploaded government documents may contain PII.

The frontend/API integration must preserve the Input Processor privacy architecture.

The API must not:

- log raw uploaded bytes
- log full extracted documents
- print raw uploaded documents to telemetry
- persist uploaded files
- place raw upload objects into GraphState
- place raw uploads into long-term memory
- place raw uploads into vector storage
- place raw uploads into the authoritative knowledge base

For the first milestone, printing `NormalizedInput` to the local development terminal is explicitly required for testing. This must continue to respect the Input Processor's privacy behavior; raw upload bytes and unmasked sensitive content must not be introduced by the API layer.

The Input Processor remains responsible for PII masking and normalized-content privacy behavior.

---

## 13. Error Handling

Input Processor failures are expected application outcomes and must cross the API boundary safely.

Examples include:

```text
INVALID_INPUT
UNSUPPORTED_FORMAT
SIGNATURE_MISMATCH
FILE_TOO_LARGE
PDF_PAGE_LIMIT_EXCEEDED
OCR_FAILURE
EXTRACTION_FAILURE
UNREADABLE_CONTENT
PII_PROCESSING_FAILURE
SAFETY_REJECTION
INTERNAL_PROCESSING_ERROR
```

The exact existing error taxonomy remains the source of truth.

The API must return safe error information to the frontend.

The API must not expose:

- Python stack traces
- internal exception details
- provider paths
- credentials
- raw document contents
- raw PII
- internal implementation information

Expected flow:

```text
Input Processor
      ↓
safe structured failure
      ↓
FastAPI
      ↓
HTTP error/result payload
      ↓
Next.js
      ↓
user-readable error
```

Partial attachment failures must preserve the Input Processor's existing behavior. A successful attachment must not be discarded simply because another attachment failed.

---

## 14. `/chat` Endpoint

The initial API must expose:

```text
POST /chat
```

The endpoint must accept:

```text
multipart/form-data
```

Conceptually:

```text
message = "Please explain these documents."

files =
    document.pdf
    image.jpg
    another.pdf
```

The precise HTTP request and response schema must be finalized during implementation planning before coding.

The API response for the first milestone should expose the processing result/normalized input sufficiently for integration testing.

The backend terminal must also print the normalized input.

The API response should not require the frontend to understand the internal Input Processor implementation.

---

## 15. NormalizedInput Boundary

The existing normalized contract is:

```text
NormalizedInput
├── user_query: str
├── image_content: list[ImageContent]
├── pdf_content: list[PDFContent]
└── combined_text: str
```

The API must not recreate or transform this contract unnecessarily.

The Input Processor remains responsible for constructing it.

The API receives the result and exposes it through the HTTP response for this development milestone.

Later, LangGraph will consume `NormalizedInput`.

The intended long-term boundary is:

```text
API
 ↓
Input Processor
 ↓
NormalizedInput
 ↓
LangGraph
```

The downstream graph must not depend on:

- FastAPI `UploadFile`
- raw uploaded bytes
- filesystem paths
- OCR provider objects
- PDF provider objects
- image libraries
- API-specific request classes

---

## 16. LangGraph Boundary

LangGraph is not part of the first implementation milestone.

Current:

```text
FastAPI
   ↓
Input Processor
   ↓
NormalizedInput
```

Future:

```text
FastAPI
   ↓
Input Processor
   ↓
NormalizedInput
   ↓
GraphState
   ↓
LangGraph
```

When LangGraph is introduced, only the agreed normalized handoff should enter graph state.

The API should not need to change its frontend-facing contract merely because the internal application begins executing the LangGraph pipeline.

---

## 17. CORS

The initial local development setup uses two servers:

```text
Next.js
http://localhost:3000

FastAPI
http://localhost:8000
```

Because these are different origins, FastAPI must include CORS middleware allowing the development frontend origin.

The initial configuration should permit:

```text
http://localhost:3000
```

The production origin must later be configuration-driven rather than relying on the development origin.

CORS configuration is an API concern and should not be implemented in the frontend as a workaround.

---

## 18. Authentication

Authentication is out of scope for this initial development milestone.

The local development setup does not require user authentication.

This is a development decision only and must not be interpreted as the final production security model.

Authentication and authorization must be addressed before production deployment.

---

## 19. Dependency Management

The Python backend uses the existing project `.venv`.

FastAPI and its required Python dependencies must be added to the project's Python dependency configuration.

`requirements.txt` must be updated as part of the implementation.

The dependency workflow is:

```text
requirements.txt
       ↓
Python environment / .venv
       ↓
FastAPI + required backend dependencies
```

The frontend uses a separate Node dependency environment:

```text
frontend/
├── package.json
├── package-lock.json
└── node_modules/
```

Next.js dependencies belong to the frontend's package configuration and must not be added to Python `requirements.txt`.

At the start of this work:

```text
FastAPI: not installed
Next.js frontend: not created
frontend/: not created
feature branch: not created
```

No dependency installation or branch creation has yet occurred.

---

## 20. Git and Collaboration

This work must be isolated from the other contributors' work.

Feature branch:

```text
feature/frontend-input-processor
```

The branch must be created before implementation work begins.

The branch should contain only changes relevant to:

- FastAPI API boundary
- Next.js frontend
- frontend/API integration
- associated tests
- dependency changes
- documentation required for this integration

Do not modify the Input Processor implementation unnecessarily.

The existing Input Processor public contract must remain unchanged unless an explicit project decision requires a change.

The final work should be submitted through a pull request.

---

## 21. Testing Strategy

Testing must be added at the API boundary without replacing the existing Input Processor tests.

Existing Input Processor tests remain responsible for validating the Input Processor itself.

The new integration tests should verify:

### API contract

- `/chat` exists.
- valid text input reaches the Input Processor.
- valid image uploads reach the Input Processor.
- valid PDF uploads reach the Input Processor.
- multiple attachments are supported.
- mixed attachments are supported.
- attachment-only requests are supported.
- text + attachments are supported.

### Boundary conversion

Verify:

```text
HTTP upload
   ↓
Attachment
   ↓
InputRequest
   ↓
process_input()
```

### Result handling

Verify:

- successful processing returns the expected normalized result.
- partial attachment failure is represented safely.
- complete processing failure is represented safely.
- safe Input Processor errors reach the frontend-facing API response.
- internal exceptions are not leaked.

### Privacy

Verify:

- raw upload objects do not enter the Input Processor contract.
- filesystem paths are not passed to the Input Processor.
- API logging does not expose raw document content.
- API logging does not expose raw PII.
- raw uploads are not persisted by the API.

### CORS

Verify that the configured local frontend origin is permitted.

### Frontend integration

At minimum, manually verify:

```text
Next.js
   ↓
FastAPI
   ↓
Input Processor
   ↓
NormalizedInput
```

using representative:

- text input
- image input
- PDF input
- multiple attachments
- text + attachment
- invalid/unsupported attachment
- processing failure

The first milestone's primary debugging output is the backend terminal.

---

## 22. Development Run Model

The intended local development setup is:

### Terminal 1 — FastAPI

```text
localhost:8000
```

### Terminal 2 — Next.js

```text
localhost:3000
```

### Browser

```text
http://localhost:3000
```

Request flow:

```text
Browser
   ↓
localhost:3000
   ↓
POST localhost:8000/chat
   ↓
FastAPI
   ↓
Input Processor
   ↓
terminal output
```

The exact command used to launch FastAPI and the exact Next.js development command should be recorded in the implementation documentation and README after the implementation is verified.

---

## 23. README Update

The implementation must include a later documentation step to update `README.md`.

The README update should be performed **after the frontend/API integration is working**, so the documented commands and architecture reflect the verified implementation rather than assumptions.

The README update should cover at least:

### Project structure

Explain:

```text
frontend/
app/api/
app/input_processing/
```

### Prerequisites

Document required:

- Python environment
- Node.js/npm requirements for Next.js
- existing OCR/PDF prerequisites where applicable

### Python setup

Document:

```text
.venv
requirements.txt
FastAPI installation/dependency setup
```

### Frontend setup

Document:

```text
cd frontend
npm install
```

and the verified development command.

### Backend setup

Document the verified FastAPI/ASGI development command.

### Running the application

Explain that local development requires:

```text
FastAPI → localhost:8000
Next.js → localhost:3000
```

### Chat flow

Document:

```text
Next.js
  ↓
FastAPI /chat
  ↓
InputRequest
  ↓
Input Processor
  ↓
NormalizedInput
```

### Current milestone limitation

Explicitly state that the current frontend integration stops at the Input Processor and that LangGraph/RAG/LLM response generation will be connected later.

---

## 24. Documentation Changes

The following documentation work should be considered part of the implementation plan:

1. Add/update API architecture documentation.
2. Document the `/chat` HTTP boundary.
3. Document frontend/API responsibilities.
4. Document local development setup.
5. Update `README.md` after verification.
6. Ensure stale project-status references are not silently changed as part of implementation.

The Input Processor handoff and architecture documents remain the source of truth for the Input Processor contract.

---

## 25. Non-Goals for This Milestone

The first frontend integration does **not** implement:

- LangGraph execution
- RAG
- vector database integration
- LLM response generation
- conversation memory
- long-term user memory
- authentication
- authorization
- production deployment
- streaming responses
- production observability
- persistent document storage
- document knowledge-base ingestion
- chatbot answer generation
- final citation generation
- production UI design
- advanced frontend state management
- production-grade design system

These can be addressed in later milestones.

---

## 26. Future Architecture

Once LangGraph and the remaining application pipeline exist, the intended architecture becomes:

```text
                         USER
                           │
                           ▼
                  ┌─────────────────┐
                  │     Next.js     │
                  │    Frontend     │
                  └────────┬────────┘
                           │
                           │ HTTP
                           ▼
                  ┌─────────────────┐
                  │     FastAPI     │
                  │   API Boundary  │
                  └────────┬────────┘
                           │
                           │ InputRequest
                           ▼
                  ┌─────────────────┐
                  │ Input Processor │
                  └────────┬────────┘
                           │
                           │ NormalizedInput
                           ▼
                  ┌─────────────────┐
                  │    LangGraph    │
                  └────────┬────────┘
                           │
             ┌─────────────┼─────────────┐
             ▼             ▼             ▼
          Intent          RAG       Other Nodes
                           │
                           ▼
                         LLM
                           │
                           ▼
                    Output Guardrails
                           │
                           ▼
                    ResponsePackage
                           │
                           ▼
                       FastAPI
                           │
                           ▼
                       Next.js
                           │
                           ▼
                          USER
```

The frontend remains a presentation/client layer.

FastAPI remains the external application boundary.

LangGraph remains the internal orchestration layer.

The Input Processor remains the normalized multimodal input boundary.

---

## 27. Implementation Sequence

The detailed implementation plan should be created from this document.

Recommended sequence:

```text
1. Create feature branch
        ↓
2. Inspect current dependency/setup files
        ↓
3. Add FastAPI/ASGI dependencies to requirements.txt
        ↓
4. Install/update Python dependencies in existing .venv
        ↓
5. Create app/api/
        ↓
6. Define FastAPI application and /chat boundary
        ↓
7. Define HTTP → InputRequest translation
        ↓
8. Add CORS middleware
        ↓
9. Add API tests
        ↓
10. Create frontend/ Next.js application
        ↓
11. Build minimal chat/upload UI
        ↓
12. Connect Next.js → POST /chat
        ↓
13. Verify text input
        ↓
14. Verify image/PDF/multiple-attachment input
        ↓
15. Verify partial and complete failures
        ↓
16. Verify terminal NormalizedInput output
        ↓
17. Verify privacy/error boundaries
        ↓
18. Update README and relevant docs
        ↓
19. Run full test suite
        ↓
20. Review diff
        ↓
21. Commit cleanly
        ↓
22. Push branch
        ↓
23. Open pull request
```

Do not begin LangGraph integration as part of this milestone.

---

## 28. Acceptance Criteria

The first frontend integration is complete when:

### Repository

- `feature/frontend-input-processor` exists.
- `frontend/` exists at the repository root.
- `app/api/` exists.
- Python dependencies are correctly represented in `requirements.txt`.
- Next.js dependencies are correctly represented in `frontend/package.json`.

### API

- FastAPI starts successfully.
- `/chat` is available.
- CORS permits the local Next.js frontend.
- API constructs `InputRequest`.
- API calls only the public `process_input()` boundary.
- API does not call modality-specific processor internals.
- API does not persist uploads.

### Input Processor integration

- Text input works.
- Images work.
- PDFs work.
- Multiple attachments work.
- Mixed attachments work.
- Text + attachments work.
- Attachment-only requests work.
- Existing Input Processor behavior remains unchanged.

### Result

- `NormalizedInput` is produced by the existing Input Processor.
- `NormalizedInput` is printed in the backend terminal.
- The API returns the processing result/normalized input for integration testing.
- The frontend does not display the raw `NormalizedInput` object in this milestone.

### Errors

- Input Processor failures reach the frontend safely.
- Internal stack traces are not exposed.
- Partial attachment failures remain partial failures.
- Complete processing failure is represented correctly.

### Privacy

- Raw uploads are transient.
- Raw upload objects do not cross the Input Processor boundary.
- The API does not create persistent upload storage.
- Raw PII is not introduced into logs by the API layer.

### Frontend

- A user can enter text.
- A user can select supported files.
- A user can submit the request.
- A processing/loading state is visible.
- Success is visible.
- Safe errors are visible.

### Documentation

- API/frontend architecture is documented.
- Local development setup is documented.
- `README.md` is updated with verified setup/run instructions.
- Current milestone limitations are documented.

### Verification

- API tests pass.
- Existing Input Processor tests continue to pass.
- Frontend/API integration has been manually verified.
- Full project test suite is run before PR creation.

---

## 29. Architectural Constraints

The following constraints must be preserved throughout implementation:

1. Do not change the existing Input Processor public contract unnecessarily.
2. Do not make the Input Processor depend on Next.js.
3. Do not make the Input Processor depend on FastAPI-specific classes.
4. Do not pass filesystem paths across the Input Processor public boundary.
5. Do not persist raw uploads in the API.
6. Do not place raw upload bytes into GraphState.
7. Do not expose raw PII through API logs or traces.
8. Do not call image/PDF processor internals directly from API code.
9. Do not put LangGraph orchestration logic into the frontend.
10. Do not put RAG or LLM logic into the frontend.
11. Keep frontend and Python dependency management separate.
12. Keep the API boundary thin.
13. Preserve attachment-level partial-success behavior.
14. Preserve safe structured error behavior.
15. Do not silently resolve unrelated open project decisions.
16. Do not expand the first milestone into the full chatbot implementation.

---

## 30. Source Contract

The Input Processor integration must follow the existing public contract:

```python
process_input(
    InputRequest(
        user_query=...,
        attachments=[
            Attachment(
                filename=...,
                media_type=...,
                content=...,
            )
        ],
    )
)
```

The result is:

```text
InputProcessingResult
```

with successful processing producing:

```text
NormalizedInput
```

The normalized contract remains:

```text
NormalizedInput
├── user_query
├── image_content
├── pdf_content
└── combined_text
```

The API/frontend work must adapt to this contract rather than redesigning it.

---

## 31. Final Integration Principle

The core design is:

```text
Frontend is a client.
FastAPI is the HTTP boundary.
Input Processor is the multimodal normalization boundary.
LangGraph is the application orchestration boundary.
```

For the current milestone:

```text
Next.js
   ↓
FastAPI
   ↓
InputRequest
   ↓
Input Processor
   ↓
NormalizedInput
```

For the eventual application:

```text
Next.js
   ↓
FastAPI
   ↓
Input Processor
   ↓
NormalizedInput
   ↓
LangGraph
   ↓
RAG / LLM / Guardrails / Response
   ↓
FastAPI
   ↓
Next.js
```

The frontend must remain replaceable, the API must remain thin, and the existing Input Processor contract must remain stable.
