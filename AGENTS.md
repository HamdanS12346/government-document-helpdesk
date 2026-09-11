# AGENTS.md

Guidelines for AI coding agents working on the Government Document Helpdesk project.

## Project Goal

Build a document-focused helpdesk assistant that can normalize user input, classify intent, retrieve relevant government document context, and generate grounded responses.

## Read First

Before making changes, review the relevant docs:

- `README.md`: setup and project overview.
- `INSTRUCTIONS.md`: team workflow, branching, commits, and PR rules.
- `docs/folder-structure.md`: what belongs in each folder.
- `docs/architecture/state-flow.md`: node inputs, outputs, and routing.
- `docs/architecture/state.md`: shared state definition.
- `docs/architecture/schema/`: schema documentation.

## Repository Map

```text
app/
|-- config/             # Settings and environment loading
|-- contracts/          # Shared schemas between nodes
|-- graph/              # LangGraph state, graph setup, routing
|-- input_processing/   # User input and attachment normalization
|-- intent/             # Intent classification and clarification
|-- memory/             # Message history and summaries
|-- rag/                # Retrieval and context building
`-- response/           # Final answer generation

docs/                   # Project documentation
evaluation/             # Evaluation datasets and scripts
guardrails/             # Safety and validation logic
tests/                  # Automated tests
```

## Core Rules

- Keep changes small, focused, and easy to review.
- Do not silently change shared contracts in `app/contracts/`.
- Do not change architecture without updating the relevant docs.
- Keep node-specific logic inside the matching `app/` folder.
- Keep graph wiring in `app/graph/`.
- Keep reusable safety checks in `guardrails/`.
- Never commit secrets, `.env`, credentials, raw private data, or large temporary files.

## Before Editing

1. Understand the component contract:
   - What does it receive?
   - What does it write?
   - Which state fields does it use?
   - Which schema does it depend on?
2. Check nearby docs and tests.
3. Preserve existing naming and structure unless there is a clear reason to change it.

## Implementation Guidance

- Prefer Pydantic models for shared data contracts.
- Keep contracts explicit and stable.
- Keep prompts, parsing, retrieval, and response formatting separated by component.
- Avoid putting business logic directly in graph routing files.
- Avoid broad refactors while implementing a narrow task.
- Add comments only when they clarify non-obvious behavior.

## Testing Guidance

Add or update tests when changing behavior.

Use the matching test folder:

- `tests/input-processor/`
- `tests/intent-classifier/`
- `tests/clarification/`
- `tests/rag/`
- `tests/context-builder/`
- `tests/response/`

Run tests before handing off:

```bash
pytest
```

If tests cannot be run, clearly say why.

## Dependencies

- Do not add dependencies casually.
- Check whether an existing package already solves the problem.
- If a dependency is needed, update `requirements.txt` and mention why.
- Be careful with packages that affect deployment, security, OCR, vector storage, or model providers.

## Documentation

Update docs when changing:

- Shared state.
- Data contracts.
- Workflow routing.
- Node responsibilities.
- Setup or dependency requirements.
- Guardrail behavior.

## Git Safety

Follow `INSTRUCTIONS.md` for branching and PR flow.

Expected flow:

```text
dev -> feature/<task> -> PR -> dev -> main
```

Do not work directly on `main` or `dev` unless explicitly instructed.

## Handoff Checklist

Before finishing, report:

- What changed.
- Which files were touched.
- What tests were run.
- Any known limitations or follow-up work.

