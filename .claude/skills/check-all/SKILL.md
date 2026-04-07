---
name: check-all
description: Run the full pre-push verification sequence — backend lint+format, backend tests, frontend types+lint+build. Stop and report on first failure.
---

Run the following steps **in order**. Stop and report as soon as any step fails.

## Step 1 — Backend lint & format (`/lint-fix`)

From `backend/`:
1. `uv run ruff format .` — auto-reformat all Python files
2. `uv run ruff check --fix .` — fix auto-fixable lint issues
3. `uv run ruff check .` — verify no remaining lint errors

If step 3 has errors, stop and report them.

## Step 2 — Backend tests (`/verify`)

From `backend/`:
```
uv run pytest tests/ -v --cov=app --cov-report=term-missing
```

Report: passed/failed counts and coverage %. If any test fails, stop and show the failures.

## Step 3 — Frontend verification (`/verify-fe`)

From `frontend/`:
1. `npx tsc --noEmit` — type-check
2. `npm run lint` — ESLint (0 warnings allowed)
3. `npm run build` — full tsc + vite build

If any step fails, stop and show the exact error output.

## Final report

If all steps pass:
```
✓ All checks passed — ready to push.
  Backend: lint clean, N tests passed, X% coverage
  Frontend: types OK, lint clean, build OK
```
