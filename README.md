# Govt Doc Helpdesk

Govt Doc Helpdesk is a document-focused assistant architecture for processing user input, classifying intent, retrieving relevant document context, and generating grounded responses.

## Project Structure

```text
.
|-- app/
|   |-- api/              # FastAPI HTTP boundary
|   |-- config/           # Settings and environment loading
|   |-- contracts/        # Shared schemas between nodes
|   |-- graph/            # LangGraph state, graph setup, routing
|   |-- input_processing/ # User input and attachment normalization
|   |-- intent/           # Intent classification and clarification
|   |-- memory/           # Message history and summaries
|   |-- rag/              # Retrieval and context building
|   `-- response/         # Final answer generation
|-- docs/
|-- evaluation/
|-- frontend/             # Next.js browser frontend
|-- guardrails/
|-- tests/
|-- .env.example
|-- .gitignore
|-- requirements.txt
`-- README.md
```

## Current Local Flow

The current frontend integration runs the Input Processor and the first intent graph slice:

```text
Next.js frontend
  -> FastAPI /chat
  -> InputRequest
  -> Input Processor
  -> NormalizedInput
  -> input-intent graph
  -> IntentDecision
```

The API response still returns the input-processing payload. For local debugging,
the FastAPI terminal prints `NormalizedInput` first, then `IntentDecision` after
classification. RAG, routing, memory, and final response generation will be
connected later.

Local development uses two servers:

```text
FastAPI: http://localhost:8000
Next.js: http://localhost:3000
```

## Prerequisites

- Python with `venv`
- Node.js and npm
- Tesseract OCR for real image OCR

## Backend Setup

### 1. Create A Virtual Environment

From the project root:

```bash
python -m venv .venv
```

### 2. Activate The Virtual Environment

On Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

On Windows Command Prompt:

```cmd
.venv\Scripts\activate.bat
```

On macOS/Linux:

```bash
source .venv/bin/activate
```

### 3. Install Python Requirements

Upgrade `pip` first:

```bash
python -m pip install --upgrade pip
```

Then install all project requirements:

```bash
pip install -r requirements.txt
```

### 4. Install OCR System Dependency

Image OCR uses `pytesseract`, which is a Python wrapper around the external Tesseract OCR executable. Installing `requirements.txt` is not enough for OCR; Tesseract must also be installed on the machine and available on `PATH`.

On Windows, install Tesseract OCR and make sure this folder is on `PATH`:

```text
C:\Program Files\Tesseract-OCR
```

Verify from an activated virtual environment:

```powershell
where.exe tesseract
tesseract --version
python -c "import pytesseract; print(pytesseract.get_tesseract_version())"
```

All three commands should succeed before real OCR integration is expected to work.

### 5. Configure Environment Variables

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

On Windows PowerShell, you can use:

```powershell
Copy-Item .env.example .env
```

Then fill in the required values in `.env`. The backend loads this file at
startup for local development. Intent classification requires `OPENAI_API_KEY`.
Langfuse tracing is optional. To enable it locally, set `LANGFUSE_ENABLED=true`
and provide `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and
`LANGFUSE_BASE_URL`.

## Frontend Setup

Install the frontend dependencies from the isolated Next.js app:

```powershell
cd frontend
npm install
```

## Run The Application

Start the backend API from the project root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.api.main:app --reload --host 127.0.0.1 --port 8000
```

In a second terminal, start the frontend:

```powershell
cd frontend
npm.cmd run dev
```

Open the browser at:

```text
http://localhost:3000
```

Submit a message, supported document attachment, or both. The frontend sends a multipart request to FastAPI, and the backend prints the `NormalizedInput` JSON and then the `IntentDecision` JSON in the terminal for local verification.

## Test Commands

Run the full backend test suite from the project root:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

Run focused API tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/api
```

Run the existing manual Input Processor baseline:

```powershell
.\.venv\Scripts\python.exe tests\input-processor\test_full.py
```

Run frontend lint:

```powershell
cd frontend
npm.cmd run lint
```

## Requirements

The project currently uses dependencies for:

- API serving: `fastapi`, `uvicorn`
- Multipart upload handling: `python-multipart`
- LLM and graph workflow: `openai`, `langchain`, `langgraph`
- Observability: `langfuse`
- Configuration and validation: `python-dotenv`, `pydantic`, `pydantic-settings`
- Retrieval/vector storage: `chromadb`, `faiss-cpu`
- PDF/image processing: `pypdf`, `pdfplumber`, `pillow`, `pytesseract`
- Testing: `pytest`, `pytest-asyncio`
- Frontend: Next.js, React, TypeScript, ESLint in `frontend/package.json`

## Documentation

Architecture notes are available in `docs/architecture/`.

Folder guidance is available in `docs/folder-structure.md`.
