# Folder Structure

Quick reference for what belongs in each project folder.

## Tree

```text
.
|-- app/
|   |-- config/
|   |-- contracts/
|   |-- graph/
|   |-- input_processing/
|   |-- intent/
|   |-- memory/
|   |-- rag/
|   `-- response/
|-- docs/
|   `-- architecture/
|       `-- schema/
|-- evaluation/
|-- guardrails/
|-- tests/
|   |-- clarification/
|   |-- context-builder/
|   |-- input-processor/
|   |-- intent-classifier/
|   |-- rag/
|   `-- response/
|-- .env.example
|-- .gitignore
|-- README.md
`-- requirements.txt
```

## Folders

| Folder | Purpose |
| --- | --- |
| `app/` | Main application source code. |
| `app/config/` | Environment loading, settings, model/provider config. |
| `app/contracts/` | Shared schemas passed between workflow nodes. |
| `app/graph/` | LangGraph state, graph construction, and routing. |
| `app/input_processing/` | Raw user input and attachment normalization. |
| `app/intent/` | Intent classification and clarification decisions. |
| `app/memory/` | Message history and conversation summary logic. |
| `app/rag/` | Retrieval, query optimization, and context building. |
| `app/response/` | Final answer generation and response formatting. |
| `docs/` | Project documentation. |
| `docs/architecture/` | Architecture notes, flows, and design decisions. |
| `docs/architecture/schema/` | Documentation for shared state and data schemas. |
| `evaluation/` | Evaluation datasets, scripts, and quality checks. |
| `guardrails/` | Safety checks, policy rules, and validation helpers. |
| `tests/` | Automated tests grouped by workflow area. |

## Root Files

| File | Purpose |
| --- | --- |
| `.env.example` | Documents required environment variables. |
| `.gitignore` | Excludes local, generated, and sensitive files. |
| `requirements.txt` | Python dependencies. |
| `README.md` | Project overview and setup instructions. |

## Guidelines

- Keep shared schemas in `app/contracts/`.
- Keep graph wiring in `app/graph/`.
- Keep node-specific logic in the matching `app/` subfolder.
- Keep tests in `tests/` and evaluations in `evaluation/`.
- Do not commit secrets. Use `.env` locally.
