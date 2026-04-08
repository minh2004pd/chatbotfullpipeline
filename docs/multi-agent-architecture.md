# Agent Architecture — MemRAG

## Tổng quan

MemRAG dùng **single agent** với Google ADK, model `gemini-2.5-flash`:

```
Root Agent  (gemini-2.5-flash)
  ├── search_documents          — tìm trong tài liệu PDF/file (Qdrant)
  ├── search_meeting_transcripts— tìm trong transcript cuộc họp (Qdrant)
  ├── list_user_documents       — liệt kê file đã upload
  ├── retrieve_memories         — mem0 long-term memory (search limit=15, top-7)
  └── store_memory              — lưu vào mem0
```

Context được xử lý bởi `ContextFilterPlugin` chạy như `before_model_callback`.

> **Lý do không dùng multi-agent**: Multi-agent (DocsAgent + MeetingAgent chạy song song) tạo nhiều LLM calls đồng thời, dễ hit 429 RESOURCE_EXHAUSTED ở Paid Tier 1. Single agent với direct tools đơn giản hơn, ít calls hơn, và gemini-2.5-flash đủ mạnh để tự quyết định khi nào gọi tool nào.

---

## Request Flow

```
POST /api/v1/chat/stream
    ↓
ChatService.chat_stream()
    ↓
_ensure_session()           ← tạo session + inject user_id vào state
    ↓
Runner.run_async()
    ↓
ContextFilterPlugin         ← before_model_callback
    ↓
Root Agent (gemini-2.5-flash)
    │
    │ Phân tích query → quyết định tool nào cần gọi
    │
    ├── search_documents(query)           → Qdrant (asyncio.to_thread)
    ├── search_meeting_transcripts(query) → Qdrant (asyncio.to_thread)
    ├── list_user_documents()             → Qdrant
    ├── retrieve_memories(query)          → mem0 (limit=15, top-7)
    └── store_memory(content)             → mem0
    ↓
Agent tổng hợp → stream response về client
```

---

## Model

```
gemini-2.5-flash    Root Agent (reasoning, tool calling, tổng hợp)
gemini-2.0-flash    Summarization (summary_model trong ContextFilterPlugin)
```

Config tại: `backend/app/core/llm_config.yaml`

---

## Context Management

### ContextFilterPlugin (`agents/plugins/context_filter_plugin.py`)

Chạy như `before_model_callback` trên Root Agent.

```
n = len(conversation_history)

n ≤ 20 (max_context_messages)
  → Pass through, không thay đổi

n > 20
  → Summarization path:
    Lần đầu (chưa có summary):
      → Blocking: gọi Gemini tóm tắt, chờ kết quả
      → Inject [summary + ack] + recent-10 vào LLM context
    
    Lần sau (đã có summary):
      → Inject summary cũ ngay (không block LLM)
      → Fire-and-forget: re-summarize ở background
      → Summary mới sẵn sàng cho turn tiếp theo
```

Summary format có cấu trúc 4 sections:
1. Quyết định & Cam kết
2. Câu hỏi & Giải đáp chính
3. Ngữ cảnh kỹ thuật
4. Follow-up chưa giải quyết

Config (tunable qua `.env`):
```
MAX_CONTEXT_MESSAGES=20    # threshold để bắt đầu summarize
SUMMARY_THRESHOLD=22       # = max_context + 2
SUMMARY_KEEP_RECENT=10     # messages gần nhất giữ lại
```

---

## RAG Retrieval Pipeline

### search_documents

```python
async def search_documents(query, tool_context):
    # 1. Embed query với RETRIEVAL_QUERY task type (cache LRU 256 entries)
    query_vector = list(get_query_embedding(query))
    
    # 2. Qdrant search trong asyncio.to_thread (không block event loop)
    results = await asyncio.to_thread(_search, repo, query, user_id, settings)
    
    # 3. Score threshold = 0.6 (loại kết quả không liên quan)
    # 4. Top-k = 5
```

### search_meeting_transcripts

Cùng pattern, search trong collection `meetings` thay vì `rag_documents`.

### retrieve_memories

```python
def retrieve_memories(query, tool_context):
    # Search limit=15 (rộng hơn) → sort by score → top-7
    raw = repo.search_memory(query, user_id, limit=15)
    ranked = sorted(raw, key=lambda m: m.get("score", 0), reverse=True)
    return ranked[:7]
```

---

## Retry & Rate Limiting

### Chat stream retry (chat_service.py)

```python
# Tự động retry khi gặp 429 RESOURCE_EXHAUSTED
# Chỉ retry nếu chưa yield gì (tránh duplicate content)
# Max 3 attempts, exponential backoff với jitter

attempt=0 → fail → delay ~2s
attempt=1 → fail → delay ~4s
attempt=2 → fail → yield error message
```

### Gemini utils retry (gemini_utils._with_retry)

Áp dụng cho `_generate_summary()` (summarization):
```
attempt=1 → delay ~1.0s
attempt=2 → delay ~2.x s (+ random jitter)
attempt=3 → delay ~4.x s (capped at 10s)
```

---

## Files liên quan

```
backend/app/agents/
  root_agent.py          Root Agent definition + tools wiring
  docs_agent.py          (không dùng — giữ lại cho tham khảo)
  meeting_agent.py       (không dùng — giữ lại cho tham khảo)
  plugins/
    context_filter_plugin.py  Context summarization callback
  tools/
    qdrant_search_tool.py     search_documents tool
    meeting_search_tool.py    search_meeting_transcripts tool
    mem0_tools.py             retrieve_memories, store_memory
    files_retrieval_tool.py   list_user_documents

backend/app/core/
  llm_config.yaml        Model names, temperatures, system prompt
  llm_config.py          Pydantic models cho config

backend/app/utils/
  gemini_utils.py        get_query_embedding (cached), _with_retry (backoff 429)
```
