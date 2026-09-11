# Government Document Helpdesk — Development Instructions

## 1. Purpose

This document defines the standard workflow for everyone working on the Government Document Helpdesk project.

The goal is simple:

- Work in isolation.
- Keep `main` stable.
- Use `dev` for integration.
- Use feature branches for actual development.
- Avoid unnecessary merge conflicts.
- Keep changes small, testable, and reviewable.
- Never silently change shared contracts or architecture decisions.

---

# 2. Branch Structure

We use this structure:

```text
main
  │
  └── dev
       │
       ├── feature/input-processing
       ├── feature/intent-classification
       ├── feature/rag
       └── feature/response-generation
```

### `main`

- Stable branch.
- Do not develop directly on `main`.
- Do not push directly to `main`.
- Changes reach `main` through reviewed Pull Requests from `dev`.

### `dev`

- Integration branch.
- Do not use `dev` as your personal development branch.
- Do not directly push changes to `dev` unless the team explicitly agrees.
- Completed feature branches are merged into `dev` through Pull Requests.

### `feature/*`

- Personal/team development branches.
- All implementation work happens here.
- A feature branch should normally have one clear purpose.

---

# 3. Before You Start Any Work

Always start from the project root.

## Step 1 — Activate the virtual environment

If the virtual environment already exists:

### Windows PowerShell

```powershell
.venv\Scripts\Activate.ps1
```

### Windows CMD

```cmd
.venv\Scripts\activate
```

### macOS / Linux

```bash
source .venv/bin/activate
```

You should see the environment name in your terminal, for example:

```text
(.venv)
```

## Step 2 — If the virtual environment does not exist

```bash
python -m venv .venv
```

Then activate it using the commands above.

## Step 3 — Install requirements

```bash
pip install -r requirements.txt
```

If `requirements.txt` is empty, that is currently expected.

Do not randomly install packages and commit the resulting dependency changes without discussing them when the dependency affects the shared project.

## Step 4 — Check Git status

```bash
git status
```

You should understand what branch you are on and whether you have uncommitted changes.

---

# 4. Starting a New Task

Never start new work from an old/stale feature branch if you can avoid it.

First update `dev`:

```bash
git checkout dev
git pull origin dev
```

Then create your feature branch:

```bash
git checkout -b feature/<short-description>
```

Example:

```bash
git checkout -b feature/input-processing
```

Another example:

```bash
git checkout -b feature/pdf-extraction
```

Check:

```bash
git branch
```

You should see:

```text
* feature/pdf-extraction
  dev
  main
```

The `*` shows your current branch.

---

# 5. Always Work in Isolation

Your feature branch is your workspace.

Do not develop directly on:

```text
main
dev
```

Instead:

```text
dev
  ↓
your feature branch
  ↓
your implementation
  ↓
tests
  ↓
Pull Request
  ↓
dev
```

Other people's code should not be edited just because it is convenient.

Respect component ownership.

For example:

```text
app/input_processing/
app/intent/
app/rag/
app/response/
```

If you own `app/rag/`, do not casually rewrite `app/intent/` to make your code easier.

If another component must change, discuss it with the owner.

---

# 6. Before Coding: Understand the Contract

Before implementing a component, identify:

1. What does the component receive?
2. What does it produce?
3. What shared state/contract does it use?
4. What errors/failures can happen?
5. What tests are required?
6. Which files are you expected to change?

For example:

```text
Input Processing
      │
      │ NormalizedInput
      ↓
Intent Classification
      │
      │ IntentDecision
      ↓
RAG
      │
      │ RetrievalResult
      ↓
Response Generation
```

Do not change a shared contract silently.

If a contract needs to change, discuss it first.

---

# 7. Normal Development Cycle

Use this cycle:

```text
Update dev
   ↓
Create feature branch
   ↓
Implement small change
   ↓
Run tests
   ↓
Review your changes
   ↓
Commit
   ↓
Push
   ↓
Keep branch synchronized with dev
   ↓
Open Pull Request
   ↓
Review
   ↓
Merge into dev
```

---

# 8. Make Small Commits

Avoid one huge commit such as:

```text
"implemented RAG"
```

Prefer focused commits:

```bash
git add app/rag/
git commit -m "feat: add hybrid retrieval"

git add tests/
git commit -m "test: add hybrid retrieval tests"

git add docs/
git commit -m "docs: document retrieval contract"
```

Use clear prefixes:

```text
feat:     new functionality
fix:      bug fix
test:     tests
docs:     documentation
refactor: code restructuring without behavior change
chore:    maintenance/configuration
```

Examples:

```text
feat: add PDF text extraction
fix: handle empty document input
test: add retrieval edge cases
docs: define retrieval result contract
chore: update development configuration
```

---

# 9. Before Committing

Always inspect what changed.

```bash
git status
git diff
```

Check for:

- Debug prints
- Secrets
- API keys
- Passwords
- Local files
- Large unnecessary files
- `.env`
- Personal data
- Temporary scripts
- Accidental modifications to other components

Then run tests:

```bash
pytest
```

If the project has specific test commands, follow those instead.

Do not commit broken code just because the feature is incomplete.

---

# 10. Push Your Feature Branch

First push:

```bash
git push -u origin feature/pdf-extraction
```

After that:

```bash
git push
```

Never do this for normal feature development:

```bash
git push origin main
```

Do not push another person's branch.

---

# 11. IMPORTANT: `dev` Has Changed While You Were Working

This will happen frequently.

Example:

```text
You created:
dev
 ↓
feature/rag
```

Meanwhile someone else merged:

```text
feature/input-processing
        ↓
       dev
```

Now your branch is behind:

```text
dev:            A──B──C──D
                     your branch:          E──F
```

Before opening/merging your PR, bring the latest `dev` into your branch.

---

# 12. Recommended Way to Synchronize Your Branch

Use rebase to keep your feature branch current.

First make sure your work is committed:

```bash
git status
```

Then:

```bash
git fetch origin
git rebase origin/dev
```

If there are no conflicts, you're done.

Then run:

```bash
pytest
```

Because rebase rewrites your branch history, push using:

```bash
git push --force-with-lease
```

### IMPORTANT

Use:

```bash
git push --force-with-lease
```

NOT:

```bash
git push --force
```

`--force-with-lease` is safer because it checks that the remote branch has not changed unexpectedly.

---

# 13. Rebase Example

Suppose your branch has:

```text
dev:
A ─ B ─ C ─ D

your branch:
A ─ B ─ C ─ E ─ F
```

Someone adds `D` to `dev`.

You run:

```bash
git fetch origin
git rebase origin/dev
```

Your history becomes conceptually:

```text
A ─ B ─ C ─ D ─ E' ─ F'
```

Then:

```bash
pytest
git push --force-with-lease
```

Your branch is now based on the latest `dev`.

---

# 14. If Rebase Has Conflicts

Do not panic.

Git will tell you which files have conflicts.

Run:

```bash
git status
```

Open the conflicted files.

You may see:

```text
<<<<<<< HEAD
version from dev
=======
your version
>>>>>>> your-commit
```

Decide which version is correct, or combine them carefully.

Then:

```bash
git add <resolved-file>
```

Continue:

```bash
git rebase --continue
```

Repeat until the rebase finishes.

Then:

```bash
pytest
git push --force-with-lease
```

---

# 15. If You Get Stuck During Rebase

You can safely cancel the rebase:

```bash
git rebase --abort
```

This returns your branch to its state before the rebase.

If you are unsure what to do, stop and ask the team rather than randomly resolving conflicts.

---

# 16. NEVER Rebase Someone Else's Shared Branch

Rebase your own feature branch.

Good:

```text
feature/rag  ← you own this
     ↓
git rebase origin/dev
```

Avoid rebasing a branch that multiple people are actively using unless the team explicitly agrees.

The safest rule for this project:

> Rebase only your own feature branch.

---

# 17. Scenario: Someone Pushed to `dev`

Suppose you are working on:

```text
feature/rag
```

Someone merges work into:

```text
dev
```

Do:

```bash
git fetch origin
git rebase origin/dev
```

Then:

```bash
pytest
git push --force-with-lease
```

Continue working.

---

# 18. Scenario: Someone Changes the Same File

Example:

You are modifying:

```text
app/contracts/normalized_input.py
```

Someone else is also modifying it.

STOP.

Do not blindly overwrite their work.

Discuss:

- Why does each person need the change?
- Can the change be separated?
- Is the contract actually changing?
- Does the architecture need updating?
- What tests are affected?

Shared contracts are integration boundaries.

---

# 19. Scenario: You Need a New Dependency

Do not simply install a package and assume it is okay.

Example:

```bash
pip install some-package
```

First determine:

- Why is it needed?
- Is there already a dependency that solves the problem?
- Is it compatible with the project?
- Does it affect deployment?
- Does it introduce security/licensing concerns?
- Which component needs it?

If approved, update `requirements.txt`.

Then:

```bash
pip install -r requirements.txt
pytest
```

Commit the dependency change separately if practical:

```bash
git add requirements.txt
git commit -m "chore: add <package> dependency"
```

If the dependency changes the architecture or a major technology choice, discuss it before implementation.

---

# 20. Scenario: New Requirement Appears

Do not immediately code it.

First classify it:

```text
Small implementation detail
        ↓
Can usually proceed

New feature
        ↓
Check requirements + architecture

Architecture change
        ↓
Discuss with team before implementation

Shared contract change
        ↓
Discuss with affected component owners

New external service/dependency
        ↓
Review security + architecture + cost
```

For significant changes, record the decision according to the project's decision-management process.

Never silently change an existing confirmed project decision.

---

# 21. Scenario: You Discover a Bug in Someone Else's Component

Do not silently rewrite their component.

First:

1. Reproduce the issue.
2. Add/identify a failing test.
3. Tell the component owner.
4. Decide who should fix it.
5. Make the fix in the appropriate branch.

If it is urgent, coordinate with the owner before touching their area.

---

# 22. Scenario: Your Feature Is Incomplete

Do not merge unfinished behavior into `dev` just because the branch exists.

Options:

### Option A — Keep working

```text
feature/rag
```

and push incremental commits.

### Option B — Open a Draft PR

Use a Draft Pull Request when you want early review/discussion.

Clearly label unfinished work.

Do not pretend a Draft PR is production-ready.

---

# 23. Pull Request Rules

When your feature is ready:

```bash
git fetch origin
git rebase origin/dev
pytest
git push --force-with-lease
```

Then create:

```text
feature/<your-branch>
        ↓
       dev
```

Your PR should explain:

```text
## What changed

...

## Why

...

## Contract

Inputs:
...

Outputs:
...

## Tests

...

## Integration impact

...

## Known limitations

...
```

The reviewer should be able to understand what changed without reading your entire branch.

---

# 24. PR Review Rules

Before approving a PR, check:

- Does it solve the stated problem?
- Does it respect the component boundary?
- Does it follow the agreed contract?
- Are tests included?
- Are failure cases handled?
- Does it introduce unnecessary dependencies?
- Does it leak PII/secrets?
- Does it affect logging/tracing?
- Does it affect retrieval/citations/guardrails?
- Does it silently change architecture?
- Does it break another component?

If the PR changes a shared contract, treat it as an architectural/integration change rather than an ordinary code change.

---

# 25. After Your PR Is Merged

Once your PR is merged into `dev`:

Do not continue using the old branch indefinitely.

For the next task:

```bash
git checkout dev
git pull origin dev
git checkout -b feature/<new-task>
```

If the old branch is no longer needed, delete it locally:

```bash
git branch -d feature/old-task
```

And delete the remote branch if your team does so:

```bash
git push origin --delete feature/old-task
```

---

# 26. Scenario: You Have Uncommitted Work and Need to Switch Branches

Check:

```bash
git status
```

If you have unfinished changes, do not blindly switch branches.

If the work is meaningful, commit it:

```bash
git add .
git commit -m "wip: checkpoint input processing"
```

If you are not ready to commit, use stash:

```bash
git stash
```

Switch branches:

```bash
git checkout dev
```

Later:

```bash
git checkout feature/input-processing
git stash pop
```

Use stash carefully. A commit is usually easier to understand and recover from.

---

# 27. Scenario: You Accidentally Worked on `dev`

Check:

```bash
git status
git branch
```

If you have not committed yet:

```bash
git stash
git checkout -b feature/<correct-branch>
git stash pop
```

Now your changes are on your feature branch.

If you already committed to `dev`, STOP before pushing.

Tell the team or fix the branch history carefully. Do not randomly reset shared history.

---

# 28. Scenario: You Accidentally Committed a Secret

Examples:

```text
API key
password
.env file
private credential
token
```

Do not simply delete it in a later commit and assume it is safe.

STOP.

Tell the team immediately and rotate/revoke the credential if applicable.

Then clean the Git history appropriately.

Prevention is better:

```text
.env
.venv/
__pycache__/
*.pyc
```

should normally be covered by `.gitignore`.

Never place real secrets in source code.

---

# 29. Scenario: You Need to Change Architecture

Examples:

- Changing vector database
- Changing orchestration approach
- Adding a new major service
- Changing memory architecture
- Changing retrieval strategy
- Changing a shared state contract
- Adding a major external API

Do not quietly implement the change.

First discuss:

```text
Existing decision
New information
Conflict
Potential impact
Recommended resolution
```

Then update the appropriate project documentation if the team confirms the change.

---

# 30. Scenario: `dev` Is Broken

If a PR causes integration failures:

1. Identify the failing change.
2. Tell the relevant owner.
3. Reproduce the failure.
4. Fix forward if practical.
5. Revert the problematic PR if necessary.

Do not keep stacking unrelated changes onto a broken integration branch.

`dev` should remain usable.

---

# 31. Main Branch Release Flow

When `dev` is stable:

```text
dev
 ↓
full tests
 ↓
evaluation
 ↓
review
 ↓
PR
 ↓
main
```

Do not merge to `main` simply because individual feature branches pass their own unit tests.

The integrated system must be tested.

---

# 32. Daily Git Checklist

Before starting:

```bash
git checkout dev
git pull origin dev
git checkout -b feature/<task>
```

While working:

```bash
git status
git diff
pytest
```

Before PR:

```bash
git fetch origin
git rebase origin/dev
pytest
git push --force-with-lease
```

After merge:

```bash
git checkout dev
git pull origin dev
```

---

# 33. Golden Rules

### Rule 1

**Never work directly on `main`.**

### Rule 2

**Do your implementation work on a feature branch.**

### Rule 3

**Feature branches start from the latest `dev`.**

### Rule 4

**Keep your feature branch synchronized with `dev`.**

### Rule 5

**Rebase only your own feature branch.**

### Rule 6

**After rebase, use `--force-with-lease`, not `--force`.**

### Rule 7

**Do not silently change shared contracts.**

### Rule 8

**Do not modify another component's internals without coordination.**

### Rule 9

**Run tests before pushing/creating a PR.**

### Rule 10

**Never commit secrets or raw sensitive user data.**

### Rule 11

**Keep commits focused and understandable.**

### Rule 12

**If you are unsure, stop and ask before changing shared architecture.**

---

# 34. Quick Command Reference

## Create a feature branch

```bash
git checkout dev
git pull origin dev
git checkout -b feature/my-feature
```

## Save work

```bash
git add .
git commit -m "feat: describe the change"
```

## Push first time

```bash
git push -u origin feature/my-feature
```

## Push later

```bash
git push
```

## Update feature branch from dev

```bash
git fetch origin
git rebase origin/dev
```

## After rebase

```bash
pytest
git push --force-with-lease
```

## Cancel rebase

```bash
git rebase --abort
```

## Check branch

```bash
git branch
```

## Check changes

```bash
git status
git diff
```

## Update local dev

```bash
git checkout dev
git pull origin dev
```

---

# 35. The Mental Model

Always think:

```text
                 STABLE
                   │
                 main
                   │
              integration
                   │
                  dev
                   │
       ┌───────────┼───────────┐
       ↓           ↓           ↓
    feature A   feature B   feature C
       │           │           │
       └───────────┼───────────┘
                   ↓
                  PR
                   ↓
                  dev
                   ↓
            integrated tests
                   ↓
                 main
```

Your branch is your isolated workspace.

`dev` is the team's shared integration area.

`main` is the stable product baseline.

Do not bypass these boundaries unless the team explicitly agrees.
