---
name: test-qa
description: |
  Create test cases, run QA/QC checks, and ensure code quality.
  Use when asked to write tests, review code quality, or perform QA.
  Supports: unit tests, integration tests, coverage analysis, linting, type checking.
---

# Test & QA Agent

## Overview
This skill handles test creation, test execution, and quality assurance for the MemRAG project.

## Test Structure

### Backend Tests (pytest)
- Location: `backend/tests/`
- Framework: pytest + pytest-asyncio + pytest-mock
- Config: `backend/pyproject.toml`
- Fixtures: `backend/tests/conftest.py` (uses `app.dependency_overrides`)
- Pattern: Unit tests with mocked external services (Qdrant, mem0, DynamoDB, Gemini)

### Frontend Tests
- Location: `frontend/src/__tests__/` (if exists)
- Framework: (check package.json for test runner)

## Commands

### Run All Backend Tests
```bash
cd /home/minhdd/pet_proj/proj2/backend && uv run pytest tests/ -v
```

### Run with Coverage
```bash
cd /home/minhdd/pet_proj/proj2/backend && uv run pytest tests/ -v --cov=app --cov-report=term-missing --cov-report=html
```

### Run Specific Test File
```bash
cd /home/minhdd/pet_proj/proj2/backend && uv run pytest tests/test_wiki_service.py -v
```

### Run Specific Test Function
```bash
cd /home/minhdd/pet_proj/proj2/backend && uv run pytest tests/test_wiki_service.py::test_slugify_basic -v
```

### Run Tests Matching Pattern
```bash
cd /home/minhdd/pet_proj/proj2/backend && uv run pytest tests/ -k "wiki" -v
```

### Linting & Formatting
```bash
# Backend
cd /home/minhdd/pet_proj/proj2/backend && uv run ruff format . && uv run ruff check .

# Frontend
cd /home/minhdd/pet_proj/proj2/frontend && npm run lint
```

## Test Writing Conventions

### Backend Test Patterns

1. **Use fixtures from conftest.py:**
   - `app` — FastAPI app with dependency overrides
   - `client` — AsyncClient for HTTP tests
   - `mock_qdrant_client` — Mocked Qdrant
   - `mock_mem0_client` — Mocked mem0
   - `mock_dynamo_session_service` — Mocked DynamoDB
   - `mock_runner` — Mocked ADK runner
   - `wiki_dir`, `repo`, `settings`, `service` — For wiki tests

2. **Mock external services via dependency_overrides:**
```python
@pytest.fixture
def mock_qdrant_client(app):
    client = MagicMock()
    client.search.return_value = []
    app.dependency_overrides[get_qdrant_client] = lambda: client
    return client
```

3. **Async tests:**
```python
@pytest.mark.asyncio
async def test_something(service):
    result = await service.some_method()
    assert result is not None
```

4. **Patch LLM calls:**
```python
from unittest.mock import patch as _patch
from unittest.mock import AsyncMock

with _patch("app.services.wiki_service.get_genai_client") as mock_client:
    mock_client.return_value.aio.models.generate_content.side_effect = RuntimeError("LLM down")
    result = await service._extract_topics(text="some text", source_name="paper.pdf")
```

5. **Test structure:**
   - Arrange: Setup mocks and fixtures
   - Act: Call the method under test
   - Assert: Verify expected behavior
   - Use descriptive test names: `test_<method>_<scenario>_<expected_behavior>`

### Test Categories

1. **Unit Tests** (`test_*_service.py`, `test_*_repo.py`)
   - Test individual components in isolation
   - Mock all external dependencies
   - Focus on business logic

2. **Integration Tests** (`test_*.py` for API endpoints)
   - Test HTTP endpoints via `client`
   - Verify request/response flow
   - Use dependency overrides for external services

3. **Edge Cases**
   - Empty inputs
   - Invalid inputs
   - Error handling
   - Disabled features (e.g., `wiki_enabled=False`)

## QA Checklist

When reviewing code or creating tests, ensure:

### Code Quality
- [ ] All new code has corresponding tests
- [ ] Tests cover happy path, error cases, and edge cases
- [ ] Mock dependencies properly (no real API calls in tests)
- [ ] Test names are descriptive and follow conventions
- [ ] Code passes linting: `ruff check .` and `ruff format .`
- [ ] No unused imports or variables
- [ ] Type hints are present where applicable

### Test Coverage
- [ ] Run `pytest --cov=app --cov-report=term-missing` to check coverage
- [ ] Target: >80% coverage for new code
- [ ] Missing lines identified and addressed

### Integration
- [ ] Tests pass locally: `uv run pytest tests/ -v`
- [ ] No regressions in existing tests
- [ ] CI/CD pipeline will pass (lint → test → build)

### Documentation
- [ ] Docstrings explain complex logic
- [ ] Test comments explain "why", not "what"
- [ ] Edge cases documented

## Creating New Tests

When asked to create tests:

1. **Identify what to test:**
   - New features/functions
   - Bug fixes (add regression tests)
   - Untested code paths

2. **Choose test type:**
   - Unit test: Single function/class
   - Integration test: API endpoint or workflow
   - Edge case test: Error handling, invalid inputs

3. **Write the test:**
   - Use existing fixtures from `conftest.py`
   - Mock external services appropriately
   - Follow naming conventions
   - Add clear assertions with descriptive messages

4. **Verify:**
   - Run the test: `uv run pytest tests/test_file.py::test_name -v`
   - Check coverage impact
   - Ensure no regressions

## Debugging Failed Tests

When tests fail:

1. **Read the error message carefully**
2. **Check if it's a mock issue:**
   - Missing fixture
   - Incorrect mock return value
   - Async vs sync mock mismatch
3. **Check if it's a logic issue:**
   - Wrong assertion
   - Changed behavior
4. **Run with verbose output:**
   ```bash
   uv run pytest tests/test_file.py::test_name -v -s
   ```
5. **Use pytest debugger:**
   ```python
   import pytest; pytest.set_trace()
   ```

## Common Patterns

### Testing Async Methods
```python
@pytest.mark.asyncio
async def test_async_method(service):
    result = await service.async_method()
    assert result == expected
```

### Testing Error Handling
```python
@pytest.mark.asyncio
async def test_method_handles_error(service):
    with patch.object(service, "dependency", side_effect=RuntimeError("fail")):
        await service.method()  # Should not raise
```

### Testing HTTP Endpoints
```python
@pytest.mark.asyncio
async def test_endpoint(client):
    response = await client.post("/api/v1/chat", json={"message": "hello"})
    assert response.status_code == 200
    assert "response" in response.json()
```

### Testing Wiki Service
```python
@pytest.mark.asyncio
async def test_wiki_synthesis(service, repo):
    topics = [{"slug": "test-topic", "category": "topics", "title": "Test"}]
    synthesized = "---\ntitle: Test\nsources: [doc-1]\n---\n# Test"

    with (
        patch.object(service, "_extract_topics", new=AsyncMock(return_value=topics)),
        patch.object(service, "_synthesize_page", new=AsyncMock(return_value=synthesized)),
    ):
        await service.update_wiki_from_document(
            user_id=USER,
            document_id="doc-1",
            filename="test.pdf",
            full_text="content",
        )

    page = repo.read_page(user_id=USER, rel_path="pages/topics/test-topic.md")
    assert page is not None
```

## Running Full QA Suite

Before marking a task complete:

```bash
# 1. Lint & format
cd /home/minhdd/pet_proj/proj2/backend && uv run ruff format . && uv run ruff check .

# 2. Run tests with coverage
cd /home/minhdd/pet_proj/proj2/backend && uv run pytest tests/ -v --cov=app --cov-report=term-missing

# 3. Frontend lint (if frontend changed)
cd /home/minhdd/pet_proj/proj2/frontend && npm run lint
```

Report results:
- Number of tests passed/failed
- Coverage percentage
- Any linting issues
- Recommendations for improvements
