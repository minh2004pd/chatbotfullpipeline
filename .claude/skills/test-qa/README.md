# MemRAG Test & QA Agent

## Overview
This directory contains tools and documentation for test creation and quality assurance in the MemRAG project.

## Files

- `SKILL.md` - Main skill definition with test creation guidelines and QA procedures
- `../scripts/qa_check.py` - Automated QA checker script

## Quick Start

### Run All Tests
```bash
cd /home/minhdd/pet_proj/proj2/backend && uv run pytest tests/ -v
```

### Run with Coverage
```bash
cd /home/minhdd/pet_proj/proj2/backend && uv run pytest tests/ -v --cov=app --cov-report=term-missing
```

### Run QA Check Script
```bash
cd /home/minhdd/pet_proj/proj2 && python3 scripts/qa_check.py
```

## Test Agent Usage

Invoke the test agent by using:
```
/test-qa Create tests for the wiki service
```

The agent will:
1. Analyze the code to identify testable components
2. Create comprehensive test cases covering:
   - Happy path scenarios
   - Edge cases
   - Error handling
   - Integration with other components
3. Run the tests to verify they pass
4. Report coverage and quality metrics

## Test File Locations

### Backend
- `backend/tests/test_wiki_service.py` - Wiki service unit tests
- `backend/tests/test_wiki_repo.py` - Wiki repository tests
- `backend/tests/test_wiki_tools.py` - Wiki ADK tools tests
- `backend/tests/test_chat.py` - Chat endpoint tests
- `backend/tests/test_documents.py` - Document upload/RAG tests
- `backend/tests/test_transcription.py` - Voice transcription tests
- `backend/tests/test_memory.py` - Memory service tests
- `backend/tests/test_sessions.py` - Session management tests
- `backend/tests/test_auth.py` - Authentication tests
- `backend/tests/test_storage.py` - Storage backend tests

### Fixtures
- `backend/tests/conftest.py` - Shared pytest fixtures

## Test Writing Guidelines

See `SKILL.md` for detailed guidelines on:
- Test structure and naming conventions
- Mocking external services
- Async test patterns
- Edge case coverage
- QA checklist
