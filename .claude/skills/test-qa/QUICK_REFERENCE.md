# Test Agent Quick Reference

## How to Use

### 1. Create Tests for New Code
```
/test-qa Create comprehensive tests for [feature/file name]
```

### 2. Run Full Test Suite
```
/test-qa Run all tests with coverage
```

### 3. Run Specific Tests
```
/test-qa Run wiki service tests
/test-qa Run chat tests
/test-qa Run tests matching "wiki"
```

### 4. QA Check
```
/test-qa Perform full QA check on the codebase
```

## Test Creation Checklist

When creating tests, the agent will:

✅ **Analyze the code** to identify:
   - Public methods and functions
   - Input/output contracts
   - Error handling paths
   - Dependencies that need mocking

✅ **Create test cases** covering:
   - Happy path (normal usage)
   - Edge cases (empty inputs, max values, etc.)
   - Error cases (invalid inputs, service failures)
   - Integration points (API endpoints, database operations)

✅ **Follow conventions**:
   - Use existing fixtures from `conftest.py`
   - Mock external services (Qdrant, mem0, DynamoDB, Gemini)
   - Use descriptive test names: `test_<method>_<scenario>_<expected>`
   - Add assertions with clear messages

✅ **Verify quality**:
   - Run tests to ensure they pass
   - Check coverage impact
   - Ensure no regressions

## Common Test Patterns

### Unit Test (Service)
```python
@pytest.mark.asyncio
async def test_method_happy_path(service, mock_dependency):
    result = await service.method(param="value")
    assert result == expected
```

### Unit Test (Error Handling)
```python
@pytest.mark.asyncio
async def test_method_handles_error(service):
    with patch.object(service, "dependency", side_effect=RuntimeError("fail")):
        await service.method()  # Should not raise
```

### Integration Test (API)
```python
@pytest.mark.asyncio
async def test_endpoint_success(client):
    response = await client.post("/api/v1/endpoint", json={"key": "value"})
    assert response.status_code == 200
```

### Wiki Service Test
```python
@pytest.mark.asyncio
async def test_wiki_synthesis(service, repo):
    topics = [{"slug": "test", "category": "topics", "title": "Test"}]
    synthesized = "---\ntitle: Test\nsources: [doc-1]\n---\n# Test"

    with (
        patch.object(service, "_extract_topics", new=AsyncMock(return_value=topics)),
        patch.object(service, "_synthesize_page", new=AsyncMock(return_value=synthesized)),
    ):
        await service.update_wiki_from_document(...)

    page = repo.read_page(...)
    assert page is not None
```

## QA Script Options

```bash
# Full QA check
python3 scripts/qa_check.py

# Backend only
python3 scripts/qa_check.py --backend-only

# Frontend only
python3 scripts/qa_check.py --frontend-only

# Wiki tests only
python3 scripts/qa_check.py --wiki-only

# Verbose output
python3 scripts/qa_check.py -v
```

## Debugging Failed Tests

1. **Read the error message** - Look for the failing assertion
2. **Check mocks** - Ensure all dependencies are properly mocked
3. **Run with verbose** - `pytest tests/test_file.py::test_name -v -s`
4. **Use debugger** - Add `import pytest; pytest.set_trace()` in test
5. **Check fixtures** - Verify fixtures are returning expected values

## Coverage Targets

- **New code**: >80% coverage
- **Critical paths**: >90% coverage (auth, data access, wiki synthesis)
- **Overall project**: Maintain or improve existing coverage

## CI/CD Integration

Tests run automatically on push to `main`:
1. Lint (ruff)
2. Test (pytest with coverage)
3. Build (Docker)
4. Deploy (ECS)
