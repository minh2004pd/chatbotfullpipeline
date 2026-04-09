# Agent Architecture — MemRAG

## Tổng quan

MemRAG dùng **single agent** với Google ADK, model `gemini-2.5-flash`:

```
Root Agent  (gemini-2.5-flash)
  ├── search_documents          — tìm trong tài liệu PDF/file (Qdrant)
  ├── search_meeting_transcripts— tìm trong transcript cuộc họp (Qdrant)
  ├── list_user_documents       — liệt kê file đã upload
  ├── list_meetings             — liệt kê cuộc họp đã ghi âm
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
    ├── list_user_documents()             → Qdrant (lấy metadata)
    ├── list_meetings()                   → DynamoDB (lấy danh sách meeting)
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

## Tool Strategy

### list_meetings & list_user_documents (Inventory tools)

Khi người dùng hỏi chung chung (không cụ thể):
- **"Tôi có những cuộc họp nào?"** → `list_meetings()` trước → tối ưu được trả lời ngay
- **"Tôi có những file gì?"** → `list_user_documents()` trước → lấy danh sách
- **"Tóm tắt tất cả meetings"** → `list_meetings()` lấy danh sách → sau đó search transcript nếu cần

Khi người dùng hỏi nội dung cụ thể:
- **"Ai nói gì trong meeting về X"** → `search_meeting_transcripts()` (không cần list trước)
- **"Tìm trong báo cáo Q1 về chi phí"** → `search_documents()` (không cần list trước)

Optimization:
- Inventory tools (list_meetings, list_user_documents) **không đi qua embedding** → nhanh, dùng metadata trực tiếp
- Search tools (search_documents, search_meeting_transcripts) **qua Qdrant + embedding** → chậm hơn nhưng tìm nội dung cụ thể

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

Cùng pattern như `search_documents`, search trong collection `meetings` thay vì `rag_documents`.

### list_meetings

```python
def list_meetings(tool_context):
    # Query DynamoDB table memrag-meetings
    # Partition key: USER#{user_id}
    # Returns: title, meeting_id, status, created_at, duration_ms, speakers, utterance_count
    # Sort mới nhất trước (created_at DESC)
```

**Dùng khi:**
- "Tôi có những cuộc họp nào?" → Get inventory nhanh từ metadata
- "Danh sách meetings gần nhất" → Parse created_at từ kết quả
- "Có bao nhiêu recording?" → Count từ results

Không embedding, không vector search — cực nhanh, chỉ metadata query.

### list_user_documents

```python
def list_user_documents(tool_context):
    # Query Qdrant metadata (document collections)
    # Returns: document_id, filename
```

**Dùng khi:**
- "Tôi có những file gì?" → Get danh sách file đã upload
- Verify khi `search_documents()` trả rỗng → "Bạn có upload file Y không?"

### retrieve_memories

```python
def retrieve_memories(query, tool_context):
    # Query mem0 memory store (vector search)
    # Search limit=15 (rộng hơn để không miss) → sort by score → top-7 (cân bằng giữa quality vs brevity)
    raw = repo.search_memory(query, user_id, limit=15)
    ranked = sorted(raw, key=lambda m: m.get("score", 0), reverse=True)
    return ranked[:7]
```

**Dùng khi:**
- "Bạn có nhớ không..." → Cá nhân hóa phong cách
- Hỏi lại thông tin đã share trước → Kéo context từ mem0
- Tuy nhiên, **không phải source duy nhất** cho sự kiện cụ thể — kết hợp với search_documents/search_meeting_transcripts

### store_memory

```python
def store_memory(content, tool_context):
    # Lưu fact mới vào mem0
    # Agent gọi tự động khi người dùng share thông tin cá nhân có giá trị
    repo.add_memory(messages=[{"role": "user", "content": content}], user_id=user_id)
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
  plugins/
    context_filter_plugin.py  Context summarization callback
  tools/
    qdrant_search_tool.py     search_documents tool
    meeting_search_tool.py    search_meeting_transcripts, list_meetings tools
    mem0_tools.py             retrieve_memories, store_memory
    files_retrieval_tool.py   list_user_documents

backend/app/core/
  llm_config.yaml        Model names, temperatures, system prompt
  llm_config.py          Pydantic models cho config

backend/app/utils/
  gemini_utils.py        get_query_embedding (cached), _with_retry (backoff 429)
```
