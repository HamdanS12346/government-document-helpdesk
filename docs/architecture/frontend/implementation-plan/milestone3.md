# Milestone 3 - Verification, Documentation, and PR Readiness

## Goal

Verify the full local development flow end to end, document the exact commands that worked, and prepare the branch for review into `dev`.

## Scope

This milestone proves:

```text
Browser
  -> Next.js
  -> FastAPI /chat
  -> InputRequest
  -> process_input()
  -> NormalizedInput
  -> backend terminal output
  -> frontend success/error state
```

LangGraph, RAG, LLM generation, streaming, auth, persistent storage, and production deployment remain out of scope.

## Tasks

1. Start from a clean working understanding of the completed Milestone 1 and Milestone 2 changes.

2. Confirm no unrelated teammate-owned components were modified.

3. Confirm the Input Processor public contract was not changed.

4. Confirm any shared contract or architecture changes were documented.

5. Run the full backend test suite:

```powershell
.\.venv\Scripts\python.exe -m pytest
```

6. Run focused API tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/api
```

7. Run the existing manual Input Processor runner once as a baseline comparison:

```powershell
.\.venv\Scripts\python.exe tests\input-processor\test_full.py
```

8. Start FastAPI:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.api.main:app --reload --host 127.0.0.1 --port 8000
```

9. Start the frontend:

```powershell
cd frontend
npm run dev
```

10. Manually test text-only input from the browser.

11. Confirm the frontend shows success.

12. Confirm the backend terminal prints normalized input JSON.

13. Manually test image-only input with a known fixture.

14. Manually test PDF-only input with a known fixture.

15. Manually test text plus one image.

16. Manually test text plus one PDF.

17. Manually test multiple attachments.

18. Manually test mixed image/PDF attachments.

19. Manually test attachment-only requests.

20. Manually test an unsupported file type.

21. Manually test a signature mismatch or corrupt file.

22. Manually test a PDF over the current page limit.

23. Confirm safe Input Processor errors appear in the frontend.

24. Confirm partial attachment failures do not discard successful attachments.

25. Confirm complete failures are shown clearly in the frontend.

26. Confirm the backend terminal does not log raw uploaded bytes.

27. Confirm the API does not persist uploaded files.

28. Confirm the API response does not expose stack traces, provider paths, raw bytes, credentials, or raw PII.

29. Confirm CORS works from `localhost:3000`.

30. Confirm the frontend shows a safe error when the backend is unavailable.

31. Inspect the final diff:

```powershell
git status
git diff
```

32. Check the diff for `.env`, secrets, raw private documents, large generated files, or accidental edits outside the frontend/API integration.

33. Update `README.md` only after the commands above have been verified.

34. Add a README section for the backend API setup.

35. Document the verified backend command:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.api.main:app --reload --host 127.0.0.1 --port 8000
```

36. Add a README section for the frontend setup.

37. Document the verified frontend commands:

```powershell
cd frontend
npm install
npm run dev
```

38. Document that local development uses two servers:

```text
FastAPI: http://localhost:8000
Next.js: http://localhost:3000
```

39. Document the current integration flow:

```text
Next.js
  -> FastAPI /chat
  -> InputRequest
  -> Input Processor
  -> NormalizedInput
```

40. Document that the current frontend integration stops at the Input Processor.

41. Document that LangGraph, RAG, and LLM response generation will be connected later.

42. Update `docs/folder-structure.md` if new permanent folders such as `frontend/`, `app/api/`, or `tests/api/` are added.

43. Add or update frontend/API architecture docs only where the implemented behavior differs from `frontend-integration.md`.

44. Run the full backend test suite again after documentation and cleanup.

45. Run any frontend checks provided by the generated Next.js setup.

46. Record test commands and results for the PR description.

47. Commit only focused frontend/API integration changes.

48. Push the branch:

```powershell
git push -u origin feature/frontend-input-processor
```

49. Open a PR from:

```text
feature/frontend-input-processor -> dev
```

50. Include in the PR:

```text
what changed
why it changed
component ownership
contract/input/output impact
tests run
manual test cases
known limitations
```

## Manual Test Checklist

Use safe fixtures from `tests/input-processor/fixtures/`.

```text
[ ] Text only
[ ] Image only
[ ] PDF only
[ ] Text + image
[ ] Text + PDF
[ ] Multiple attachments
[ ] Mixed image/PDF attachments
[ ] Attachment-only request
[ ] Unsupported file type
[ ] Corrupt/signature mismatch file
[ ] Over-page-limit PDF
[ ] Backend unavailable
```

For each successful request, confirm:

```text
[ ] Frontend shows success
[ ] Backend terminal prints NormalizedInput
[ ] API response is safe
[ ] No raw upload is persisted
```

For each failure request, confirm:

```text
[ ] Frontend shows a safe error
[ ] No Python stack trace is shown
[ ] No raw bytes or raw PII are logged
[ ] Partial successes are preserved when applicable
```

## Acceptance Criteria

- Full backend tests pass.
- Focused API tests pass.
- Frontend checks pass or any skipped check is explained.
- Manual browser testing covers the checklist above.
- README contains verified backend and frontend setup/run steps.
- `docs/folder-structure.md` reflects new permanent folders if needed.
- The final diff is focused on frontend/API integration.
- The branch is ready for PR into `dev`.
