# Testing Strategy — MemRAG Chatbot

Dự án MemRAG được trang bị hệ thống test toàn diện bao gồm Unit Tests và Integration Tests cho cả 3 lớp: API, Service và Repository.

> **Cập nhật lần cuối**: 2026-04-21 — **429 tests** (416 logic tests + 2 skipped Google OAuth), coverage ~67%.

---

## 1. Tổng quan hệ thống Test

- **Framework chính**: `pytest` + `pytest-asyncio` (mode=AUTO)
- **Thư viện hỗ trợ**:
  - `pytest-asyncio`: Hỗ trợ test các hàm asynchronous.
  - `httpx` / `starlette.testclient`: Thực hiện các request tới API.
  - `unittest.mock`: Mocking các service bên ngoài (Gemini, Qdrant, mem0, DynamoDB).
  - `pytest-cov`: Coverage reporting.
- **Vị trí**: `backend/tests/`
- **Chạy**: `uv run pytest tests/ -v --cov=app --cov-report=term-missing`

---

## 2. Chiến lược Mocking & Dependency Injection

Hệ thống tận dụng tính năng **Dependency Injection** của FastAPI để swap các service thật bằng Mock objects trong quá trình test mà không cần can thiệp vào logic code.

### 2.1 HTTP Tests — `app.dependency_overrides`

```python
# conftest.py
app.dependency_overrides[get_qdrant_client] = lambda: mock_client
```

Fixtures trong `conftest.py` register overrides tự động. Tests apply chúng qua `pytestmark`:

```python
pytestmark = pytest.mark.usefixtures("mock_qdrant_client")
```

### 2.2 Service Unit Tests — Constructor Injection

```python
service = RAGService(qdrant_repo=MagicMock(spec=QdrantRepository), settings=get_settings())
```

### 2.3 Wiki Service Tests — Real Filesystem, Mock LLM

`WikiRepository` dùng thật với `tmp_path`. Chỉ mock LLM calls (`_with_retry`, `get_genai_client`):

```python
with patch("app.services.wiki_service._with_retry", new=AsyncMock(return_value=mock_resp)):
    result = await service._extract_topics(...)
```

**Quan trọng**: Luôn patch cả `get_genai_client` lẫn `_with_retry` để tránh client initialization thật.

### 2.4 AsyncIO Lock Isolation

Module-level `_page_locks` và `_link_index_locks` trong `wiki_service.py` tồn tại xuyên suốt các tests. Mỗi test dùng event loop riêng nên phải clear locks giữa các tests:

```python
@pytest.fixture(autouse=True)
def clear_wiki_locks():
    import app.services.wiki_service as ws
    ws._page_locks.clear()
    ws._link_index_locks.clear()
    yield
    ws._page_locks.clear()
    ws._link_index_locks.clear()
```

Fixture này đã được thêm vào `test_wiki_service.py` (autouse=True).

### 2.5 Mock Fixtures cần thiết

| Service | Mock pattern |
|---------|-------------|
| Qdrant | `MagicMock(spec=QdrantRepository)`, set `find_by_hash.return_value = None` để tránh duplicate check |
| ADK Runner | `async def fake(**kwargs): yield event` — async generator |
| DynamoDB Session | `get_session` / `create_session` → `AsyncMock` |
| Gemini LLM | `patch("...._with_retry", new=AsyncMock(return_value=mock_resp))` |

---

## 3. Các lớp Test chính

### 3.1. API Layer (Integration Tests)

Kiểm tra các endpoints, xác thực JWT, và xử lý request/response.

| File | Coverage |
|------|---------|
| `test_auth.py` | Đăng ký, đăng nhập, duplicate email, refresh token, token rotation, Google OAuth |
| `test_chat.py` | Luồng chat streaming (SSE), validation message, multimodal image, session persistence |
| `test_documents.py` | Upload PDF, list và delete documents |
| `test_transcription.py` | Luồng transcription realtime (start/audio/stream/stop) |

### 3.2. Service Layer (Unit Tests)

Kiểm tra logic nghiệp vụ phức tạp.

#### `test_wiki_service.py` — 77 tests

Pipeline Wiki (Map-Reduce-Synthesize), bao gồm 2 tính năng mới:

**Context-Aware Extraction** (thêm 2026-04-21):
- `test_get_existing_wiki_context_empty_when_no_wiki` — wiki rỗng → trả về chuỗi rỗng
- `test_get_existing_wiki_context_with_existing_pages` — có pages → trả về context đúng format
- `test_get_existing_wiki_context_caps_at_50_items` — cap tối đa 50 items để tránh context bloat
- `test_extract_topics_receives_wiki_context` — verify wiki_context được inject vào LLM prompt
- `test_process_source_injects_wiki_context_into_extraction` — integration: context injected đúng khi có wiki pages

**Conversation Summary → Wiki Integration** (thêm 2026-04-21):
- `test_assess_summary_relevance_no_prompt_returns_false` — không có prompt → skip
- `test_assess_summary_relevance_returns_should_update_true` — LLM trả về should_update=true
- `test_assess_summary_relevance_returns_should_update_false` — LLM trả về should_update=false (chitchat)
- `test_conversation_wiki_update_skip_when_disabled` — `WIKI_CONVERSATION_UPDATE_ENABLED=false` → noop
- `test_conversation_wiki_update_skip_empty_wiki` — wiki rỗng → không gọi LLM relevance check
- `test_conversation_wiki_update_skip_not_relevant` — LLM says not relevant → pages không đổi
- `test_conversation_wiki_update_enriches_matched_pages` — happy path: page được enrich version mới
- `test_conversation_wiki_update_skip_stub_pages` — stub pages không bị update

#### `test_rag_service.py`

Logic ingest PDF, embedding, chunk, dedup bằng content hash.

#### `test_services_document_service.py`

Xử lý file, chunking văn bản, storage backend (local/S3).

### 3.3. Repository Layer

| File | Coverage |
|------|---------|
| `test_repositories_qdrant_repo.py` | Upsert/Search/Delete vector points |
| `test_repositories_mem0_repo.py` | Lưu trữ và truy xuất facts từ mem0 |
| `test_wiki_repo.py` | Thao tác file hệ thống (hoặc S3) cho Wiki Knowledge Base |
| `test_repositories_meeting_repo.py` | Lưu trữ metadata cuộc họp và utterances vào DynamoDB |

### 3.4. Core & Security

| File | Coverage |
|------|---------|
| `test_core_security.py` | Mã hóa password (bcrypt), tạo/giải mã JWT. **Lưu ý**: bcrypt truncate ở 72 bytes — test dùng password ≤ 71 bytes để tránh false pass |
| `test_core_config.py` | Load cấu hình từ `.env` và YAML, validate security |
| `test_core_indexing_status.py` | In-memory wiki indexing status store, TTL expiry |
| `test_exceptions_handlers.py` | Global exception handlers (400/404/500). Dùng `raise_server_exceptions=False` trong TestClient |
| `test_utils_file_utils.py` | PDF extraction, chunking, file save. `chunk_text()` clamp overlap khi chunk_size nhỏ |
| `test_utils_wiki_utils.py` | Frontmatter parsing, slug extraction, link parsing |

---

## 4. Cách chạy Test

```bash
# Toàn bộ test với coverage
uv run pytest tests/ -v --cov=app --cov-report=term-missing

# Chạy một file
uv run pytest tests/test_wiki_service.py -v

# Chạy một test cụ thể
uv run pytest tests/test_wiki_service.py::test_update_wiki_from_document_creates_page -v

# Chạy group test theo keyword
uv run pytest tests/ -k "conversation_wiki" -v

# Dùng skill
/verify
```

---

## 5. Quy tắc viết Test mới

1. **Async**: Luôn dùng `@pytest.mark.asyncio` cho các test case gọi hàm async.
2. **Không gọi API thật**: Dùng `dependency_overrides` hoặc `unittest.mock.patch` để mock Gemini API và external services.
3. **Fixtures**: Tận dụng fixtures trong `conftest.py` (`client`, `app`, `mock_db`). Wiki tests dùng `tmp_path` cho filesystem isolation.
4. **Isolated Data**: Mỗi test case phải độc lập — không share state. Dùng `autouse` fixture để clear module-level state (ví dụ: lock dicts, in-memory stores).
5. **Mock LLM đúng cách**: Luôn patch cả `get_genai_client` lẫn `_with_retry` khi test wiki methods gọi Gemini.
6. **Bcrypt 72-byte limit**: Test password roundtrip chỉ dùng password ≤ 71 bytes. Password > 72 bytes bị truncate nên `pwd` và `pwd + "x"` có thể hash giống nhau.
7. **TestClient exceptions**: Dùng `TestClient(app, raise_server_exceptions=False)` khi test generic 500 handler — mặc định TestClient re-raise server exceptions.

---

## 6. Known Limitations & CI Notes

- **Google OAuth tests**: 1 test skip khi `GOOGLE_OAUTH_CLIENT_ID` chưa set (expected).
- **Soniox / Transcript RAG**: Coverage thấp (~18-24%) vì cần WebSocket connection thật — không mock được hoàn toàn.
- **Chat Service**: Coverage ~67% — phần streaming và multimodal cần ADK integration test thật.
- **CI env vars required**: `GEMINI_API_KEY`, `DEBUG=true`, `JWT_SECRET_KEY`, `ALLOWED_ORIGINS` — xem `.github/workflows/ci-cd.yml`.
