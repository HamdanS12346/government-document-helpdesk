# Government Document Helpdesk Development Instructions

This guide explains how the team should work together on the Government Document Helpdesk project.

The goal is to keep development smooth, avoid merge conflicts, protect shared contracts, and make sure `main` stays stable.

## Core Principles

- Keep `main` stable.
- Use `dev` as the shared integration branch.
- Do all implementation work on `feature/*` branches.
- Keep changes small, testable, and reviewable.
- Respect component ownership.
- Coordinate before changing shared contracts, architecture, or another teammate's component.
- Never commit secrets, `.env`, credentials, raw sensitive user data, or private files.

## Branch Model

```text
main
  |
  `-- dev
       |
       |-- feature/input-processing
       |-- feature/intent-classification
       |-- feature/rag
       `-- feature/response-generation
```

### `main`

`main` is the stable product branch.

- Do not develop directly on `main`.
- Do not push directly to `main`.
- Merge to `main` only from a stable `dev` branch through review.

### `dev`

`dev` is the integration branch.

- Completed feature branches merge into `dev`.
- Do not use `dev` as a personal working branch.
- Avoid direct pushes to `dev` unless the team explicitly agrees.

### `feature/*`

Feature branches are where actual work happens.

Examples:

```text
feature/input-processing
feature/pdf-extraction
feature/intent-classifier
feature/rag-retrieval
feature/response-generation
```

Each feature branch should have one clear purpose.

## Project Areas

```text
app/input_processing/   # input normalization
app/intent/             # intent classification and clarification decisions
app/rag/                # retrieval and context building
app/response/           # final response generation
app/memory/             # message history and summaries
app/graph/              # LangGraph state, graph assembly, routing
app/contracts/          # shared schemas between nodes
guardrails/             # safety checks and validation
tests/                  # automated tests
evaluation/             # evaluation data and scripts
docs/                   # architecture and project documentation
```

## Setup

From the project root, create a virtual environment:

```bash
python -m venv .venv
```

Activate it:

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```cmd
:: Windows CMD
.venv\Scripts\activate.bat
```

```bash
# macOS/Linux
source .venv/bin/activate
```

Install dependencies:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Create your local environment file:

```bash
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Fill in `.env` locally. Never commit `.env`.

## Starting a New Task

Always start from the latest `dev`:

```bash
git checkout dev
git pull origin dev
git checkout -b feature/<short-description>
```

Check where you are:

```bash
git branch
git status
```

Do not begin work from an old feature branch unless there is a specific reason.

## Working With Teammates

Good team development means avoiding surprise changes.

Before you start, know which area you are working in and who else may be touching it.

Coordinate with teammates when:

- You need to change `app/contracts/`.
- You need to change `app/graph/state.py` or routing behavior.
- You need to modify another teammate's component.
- You are adding a new dependency.
- You are changing architecture or workflow behavior.
- You are moving files or renaming public functions/classes.
- You are changing test expectations used by other components.

If two people need the same file, discuss the order of work or split the changes.

Do not rewrite another person's code just because it is convenient. If another component needs to change, explain why and agree on the change first.

## Component Contracts

Before implementing a component, answer:

- What does this component receive?
- What does it write back to state?
- Which contract models does it use?
- What errors can happen?
- Which tests should prove it works?

Shared contracts live in:

```text
app/contracts/
```

Architecture docs live in:

```text
docs/architecture/
```

If a contract changes, update the contract code, tests, and docs together.

Do not silently change field names, required fields, enum values, or state keys.

## Normal Development Cycle

Use this flow:

```text
update dev
  -> create feature branch
  -> implement a focused change
  -> run tests
  -> inspect diff
  -> commit
  -> push
  -> open PR to dev
```

Keep commits focused.

Good examples:

```bash
git add app/input_processing tests/input-processor
git commit -m "feat: add PDF input normalization"

git add app/contracts docs/architecture/schema
git commit -m "docs: update normalized input contract"
```

Suggested commit prefixes:

```text
feat:      new functionality
fix:       bug fix
test:      tests
docs:      documentation
refactor:  code restructuring without behavior change
chore:     maintenance/config
```

## Before Committing

Inspect your work:

```bash
git status
git diff
```

Check for:

- Debug prints.
- Secrets or credentials.
- `.env` files.
- Temporary files.
- Large generated files.
- Accidental edits in another component.
- Silent schema or architecture changes.

Run tests:

```bash
pytest
```

If only part of the suite is relevant during development, run focused tests first, then run the broader suite before PR when practical.

## Keeping Your Branch Updated

When `dev` changes, update your feature branch:

```bash
git fetch origin
git rebase origin/dev
pytest
git push --force-with-lease
```

Use `--force-with-lease`, not `--force`.

Rebase only your own feature branch.

If rebase has conflicts:

```bash
git status
```

Open the conflicted files, resolve them carefully, then continue:

```bash
git add <resolved-file>
git rebase --continue
```

If you are unsure how to resolve a conflict, ask the teammate who owns the affected component.

To cancel a rebase:

```bash
git rebase --abort
```

## Pull Requests

Open PRs from:

```text
feature/<your-branch> -> dev
```

Before opening a PR:

```bash
git fetch origin
git rebase origin/dev
pytest
git push --force-with-lease
```

Your PR should include:

- What changed.
- Why it changed.
- Which component owns the change.
- Contract/input/output impact.
- Tests run.
- Known limitations or follow-up work.

Reviewers should check:

- The change solves the stated problem.
- Component boundaries are respected.
- Shared contracts are still compatible.
- Tests cover the behavior.
- Failure cases are handled.
- No secrets or sensitive data are included.
- No unnecessary dependencies were added.
- Docs were updated where needed.

## If You Need a Teammate's Change

Do not block silently.

Tell the teammate:

- What you need.
- Why you need it.
- Which file or contract is affected.
- Whether your branch is blocked or can continue with a placeholder.

If possible, agree on the contract first, then implement independently.

## If Someone Changes Your Area

Assume good intent first.

Check:

- Does the change affect your current branch?
- Does it change a shared contract?
- Is the behavior still correct?
- Are tests updated?

If there is a conflict, discuss it before overwriting their work.

## Dependencies

Do not add dependencies casually.

Before adding one, check:

- Why is it needed?
- Is an existing dependency enough?
- Does it affect deployment?
- Does it affect security, licensing, or cost?
- Which component needs it?

If the dependency is accepted, update:

```text
requirements.txt
README.md, if setup changes
```

Then run:

```bash
pip install -r requirements.txt
pytest
```

## Documentation

Update docs when changing:

- Shared state.
- Data contracts.
- Workflow routing.
- Node responsibilities.
- Setup steps.
- Dependencies.
- Guardrail behavior.

Useful docs:

```text
docs/folder-structure.md
docs/architecture/state-flow.md
docs/architecture/state.md
docs/architecture/schema/
```

## Testing Expectations

Use the matching test folder:

```text
tests/input-processor/
tests/intent-classifier/
tests/clarification/
tests/rag/
tests/context-builder/
tests/response/
```

Add tests for:

- New behavior.
- Bug fixes.
- Contract changes.
- Edge cases.
- Failure handling.

If a change affects multiple components, add integration-style coverage where possible.

## Handling Bugs in Another Component

Do not silently rewrite another team's area.

First:

- Reproduce the bug.
- Identify the failing behavior.
- Add or propose a failing test.
- Tell the owner or teammate working in that area.
- Agree who will fix it.

Urgent fixes are fine, but still communicate clearly.

## Incomplete Work

Do not merge unfinished behavior into `dev`.

Options:

- Keep working on the feature branch.
- Push a checkpoint commit if helpful.
- Open a Draft PR for early feedback.

Clearly label incomplete behavior.

## Secrets and Sensitive Data

Never commit:

- `.env`
- API keys
- Passwords
- Tokens
- Private documents
- Raw sensitive user data
- Local-only files

If a secret is committed by mistake:

- Stop.
- Tell the team.
- Rotate or revoke the credential.
- Clean the Git history properly.

Deleting the secret in a later commit is not enough.

## Quick Commands

Create a feature branch:

```bash
git checkout dev
git pull origin dev
git checkout -b feature/my-feature
```

Save work:

```bash
git add .
git commit -m "feat: describe the change"
```

Push first time:

```bash
git push -u origin feature/my-feature
```

Update branch from `dev`:

```bash
git fetch origin
git rebase origin/dev
```

After rebase:

```bash
pytest
git push --force-with-lease
```

Check changes:

```bash
git status
git diff
```

## Golden Rules

- Work on feature branches.
- Start from latest `dev`.
- Keep `dev` integration-ready.
- Keep `main` stable.
- Respect teammate ownership.
- Coordinate contract and architecture changes.
- Run tests before PR.
- Keep commits focused.
- Never commit secrets.

