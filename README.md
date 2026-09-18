# Government Document Helpdesk

Government Document Helpdesk is a document-focused chat assistant for helping users ask questions about government forms, PDFs, images, and spreadsheets. The backend normalizes the user input, classifies the intent, retrieves relevant document evidence when needed, builds a grounded context, generates a response, applies response guardrails, and stores conversation memory when memory credentials are configured.

The project has a FastAPI backend and a Next.js frontend:

```text
Frontend chat UI
  -> FastAPI /chat
  -> Input Processor
  -> Intent Classifier
  -> document_info: Retriever -> Context Builder -> Response -> Guardrails
  -> general_chat: Response -> Guardrails
  -> ambiguous: Clarification -> Guardrails
  -> Memory load/save when conversation memory is available
```

## Main Folders

```text
app/
|-- api/              # FastAPI routes, auth, and public response serialization
|-- config/           # Settings and .env loading
|-- contracts/        # Shared Pydantic schemas between nodes
|-- graph/            # LangGraph state, graph setup, and routing
|-- input_processing/ # Text, image, PDF, and spreadsheet normalization
|-- intent/           # Intent classification and query shaping
|-- memory/           # Conversation threads, summaries, and persistence
|-- rag/              # Retrieval, reranking, metadata, and context building
`-- response/         # Final answer generation and response guardrail adapter

frontend/             # Next.js chat interface
docs/                 # Architecture and folder documentation
evaluation/           # Evaluation data and scripts
guardrails/           # Safety and validation checks
tests/                # Backend tests grouped by feature area
```

## What Works Now

- `POST /chat` accepts a message, optional attachments, and an optional `conversation_id`.
- Input processing supports plain text plus PDF, image, and `.xlsx` attachment normalization.
- Intent classification routes requests as `document_info`, `general_chat`, or `ambiguous`.
- Document questions run through retrieval, context building, response generation, and response guardrails.
- General chat requests go directly to response generation and response guardrails.
- Ambiguous requests return a clarification-style assistant message with `status: "clarification_required"`.
- Conversation memory is connected. It uses Supabase when configured and falls back to in-memory storage for local development.
- The frontend can send chat messages and attachments, display assistant responses, and use Supabase auth/thread history when configured.

## Prerequisites

### If Running with Docker (Recommended)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (includes Docker Compose v2)
- Cloud API credentials in `.env` (OpenAI, Supabase, Chroma Cloud)
*(No need to install Python, Node.js, Tesseract OCR, or Poppler on your host machine—Docker bundles all native C-binaries and runtimes automatically).*

### If Running Locally without Docker
- Python 3.11+ with `venv`
- Node.js (v20+ or v22+) and npm
- Tesseract OCR installed locally (with English and Hindi models) and added to system `PATH`
- Poppler utilities (for PDF parsing)
- API credentials for the services you want to use locally

## Environment Variables

Backend environment variables live in the project root:

```text
.env.example  # committed template
.env          # local secrets, do not commit
```

Create `.env` from the template:

```powershell
Copy-Item .env.example .env
```

On macOS/Linux:

```bash
cp .env.example .env
```

Fill in the values you need:

| Variable | Needed for | Notes |
| --- | --- | --- |
| `OPENAI_API_KEY` | Required for intent classification, metadata extraction, query rewriting, embeddings, and response generation | Main credential needed for normal chat behavior. |
| `COHERE_API_KEY` | Optional reranking | Used only if the reranker path is enabled. |
| `CHROMA_API_KEY`, `CHROMA_TENANT`, `CHROMA_DATABASE`, `CHROMA_COLLECTION_NAME` | Optional Chroma Cloud retrieval | Without cloud credentials, retrieval can fall back to local/in-memory behavior depending on available data. |
| `SUPABASE_URL`, `SUPABASE_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET` | Optional backend memory/auth persistence | Without Supabase credentials, backend memory falls back to in-memory storage for the running process. |
| `LANGFUSE_ENABLED`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` | Optional tracing and evaluation reporting | `.env.example` keeps tracing disabled by default for local setup. |
| `LANGFUSE_CAPTURE_TEXT` | Optional tracing detail | Controls whether trace metadata may include text previews. |
| `CHAT_DEBUG_PRINTS` | Optional local debugging | Set `true` to print normalized input, intent, and assistant output in the backend terminal. |
| `UPLOAD_MAX_ATTACHMENT_COUNT`, `UPLOAD_MAX_TOTAL_SIZE_BYTES` | Optional upload limits | Defaults are already provided in `.env.example`. |

Frontend environment variables are read by Next.js. Create a local frontend env file from the frontend template:

```powershell
Copy-Item frontend/.env.local.example frontend/.env.local
```

On macOS/Linux:

```bash
cp frontend/.env.local.example frontend/.env.local
```

The template contains:

```text
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
```

`NEXT_PUBLIC_API_URL` defaults to `http://localhost:8000`. Supabase frontend values are only needed for login and thread history in the UI.

Never commit `.env`, `frontend/.env.local`, API keys, access tokens, or private user documents.

## Option 1: Running with Docker (Recommended)

Docker packages both the FastAPI backend (including native Tesseract OCR, Poppler C-libraries, and Python dependencies) and Next.js frontend into isolated containers managed by `docker-compose.yml`.

### 1. Start the Containers

**Standard Production Stack** (builds and runs both services in background):
```bash
docker compose up --build -d
```

**Development Mode with Live Code Sync** (uses bind mounts so edits to `app/` and `frontend/` reflect immediately):
```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

### 2. Access the Application

- **Frontend Chat UI**: [http://localhost:3000](http://localhost:3000)
- **FastAPI Interactive Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Next.js API Proxy**: Next.js automatically rewrites `/api/py/:path*` to the internal backend container (`http://backend:8000/:path*`). Test this at [http://localhost:3000/api/py/docs](http://localhost:3000/api/py/docs).

### 3. Docker Management Commands

| Task | Command |
| --- | --- |
| **Check container health** | `docker compose ps` |
| **Stream live logs across services** | `docker compose logs -f` |
| **Run tests inside backend container** | `docker compose exec backend pytest` |
| **Stop and remove containers** | `docker compose down` |

---

## Option 2: Running Locally without Docker (Manual Setup)

### Backend Setup

From the project root, create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Install Tesseract OCR if you need image OCR. On Windows, make sure this folder is on `PATH`:

```text
C:\Program Files\Tesseract-OCR
```

Verify OCR setup:

```powershell
where.exe tesseract
tesseract --version
python -c "import pytesseract; print(pytesseract.get_tesseract_version())"
```

Start the backend:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.api.main:app --reload --host 127.0.0.1 --port 8000
```

The API runs at:

```text
http://localhost:8000
```

### Frontend Setup

In a second terminal:

```powershell
cd frontend
npm install
npm.cmd run dev
```

Open:

```text
http://localhost:3000
```

The frontend sends multipart chat requests to the backend, including uploaded files and an optional `conversation_id`.

## Tests

### Running Tests with Docker

Run the backend test suite inside the containerized Linux environment:

```bash
docker compose exec backend pytest
```

### Running Tests Locally without Docker

Run the backend test suite from the project root:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

On macOS/Linux:

```bash
pytest
```

Run frontend lint and frontend tests:

```powershell
cd frontend
npm.cmd run lint
npm.cmd test
```

## Useful Docs

- `INSTRUCTIONS.md`: team workflow, branches, commits, and PRs
- `docs/folder-structure.md`: what belongs in each folder
- `docs/architecture/state-flow.md`: node inputs, outputs, and routing
- `docs/architecture/state.md`: shared graph state
- `docs/architecture/schema/`: shared schema documentation
