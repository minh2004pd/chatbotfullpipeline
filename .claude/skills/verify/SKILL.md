---
name: verify
description: Run the full test suite with coverage. Use before marking a task done.
---

Run the full test suite with coverage from the `backend/` directory:

```bash
cd /home/minhdd/pet_proj/proj2/backend && uv run pytest tests/ -v --cov=app --cov-report=term-missing
```

Report the results: number of tests passed/failed, coverage percentage, and any failures with their tracebacks. If tests fail, diagnose the root cause before suggesting fixes.
