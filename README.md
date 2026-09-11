# Govt Doc Helpdesk

Govt Doc Helpdesk is a document-focused assistant architecture for processing user input, classifying intent, retrieving relevant document context, and generating grounded responses.

## Project Structure

```text
.
|-- app/
|-- docs/
|-- evaluation/
|-- guardrails/
|-- tests/
|-- .env.example
|-- .gitignore
|-- requirements.txt
`-- README.md
```

## Setup

### 1. Create a virtual environment

From the project root:

```bash
python -m venv .venv
```

### 2. Activate the virtual environment

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

### 3. Install requirements

Upgrade `pip` first:

```bash
python -m pip install --upgrade pip
```

Then install all project requirements:

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

On Windows PowerShell, you can use:

```powershell
Copy-Item .env.example .env
```

Then fill in the required values in `.env`.

## Requirements

The project currently uses dependencies for:

- API serving: `fastapi`, `uvicorn`
- LLM and graph workflow: `openai`, `langchain`, `langgraph`
- Configuration and validation: `python-dotenv`, `pydantic`, `pydantic-settings`
- Retrieval/vector storage: `chromadb`, `faiss-cpu`
- PDF/image processing: `pypdf`, `pdfplumber`, `pillow`, `pytesseract`
- Testing: `pytest`, `pytest-asyncio`

## Documentation

Architecture notes are available in `docs/architecture/`.

Folder guidance is available in `docs/folder-structure.md`.
