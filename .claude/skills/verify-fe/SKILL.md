---
name: verify-fe
description: Verify frontend is clean before commit or deploy — runs TypeScript type-check, ESLint, and Vite production build from frontend/
---

Run the following from `frontend/` in order. Stop and report on the first failure.

1. **Type-check:** `npx tsc --noEmit`
   - Catches type errors that ESLint doesn't cover
   - Report all errors with file:line

2. **Lint:** `npm run lint`
   - ESLint with 0 warnings allowed
   - Report all violations

3. **Build:** `npm run build`
   - Full `tsc && vite build` — catches import errors, missing env vars, bundle issues
   - Report any build failures

If all 3 pass, confirm with a single line: "✓ Frontend verified — types, lint, build all pass."

If anything fails, show the exact error output and stop. Do not suggest fixes unless asked.
