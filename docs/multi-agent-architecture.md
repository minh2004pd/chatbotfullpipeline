# Multi-Agent Architecture — MemRAG

## Tổng quan

MemRAG dùng **Google ADK multi-agent pattern** với 3 agents phân tầng theo trách nhiệm:

```
Root Agent  (gemini-2.5-flash)   — reasoning, orchestration, tổng hợp
  ├── DocsAgent    (gemini-2.0-flash)  — tra cứu tài liệu PDF/file
  └── MeetingAgent (gemini-2.0-flash)  — tra cứu transcript cuộc họp
```

Memory và context được xử lý trực tiếp bởi Root Agent (không qua sub-agent):
- `retrieve_memories` / `store_memory` — mem0 long-term memory
- `ContextFilterPlugin` — session context management

---

## Kiến trúc chi tiết

### Request Flow

```
POST /api/v1/chat/stream
    ↓
ChatService.chat_stream()
    ↓
_ensure_session()           ← tạo session + inject user_id vào state
    ↓
Runner.run_async()
    ↓
ContextFilterPlugin         ← before_model_callback, chỉ chạy trên Root
    ↓
Root Agent (gemini-2.5-flash)
    │
    │ Phân tích query → formulate specific requests
    │
    ├──[parallel]── AgentTool(DocsAgent)
    │                   ↓
    │               DocsAgent (gemini-2.0-flash)
    │                   ↓ search_documents (async → asyncio.to_thread → Qdrant)
    │                   ↓ list_user_documents (nếu cần)
    │                   ↓ extract + format kết quả
    │                   → trả structured text về Root
    │
    ├──[parallel]── AgentTool(MeetingAgent)
    │                   ↓
    │               MeetingAgent (gemini-2.0-flash)
    │                   ↓ search_meeting_transcripts (async → asyncio.to_thread → Qdrant)
    │                   ↓ retry nếu rỗng
    │                   ↓ extract + format kết quả
    │                   → trả structured text về Root
    │
    └── retrieve_memories (direct tool)
            ↓ mem0 search (limit=15) → rerank by score → top-7
            → trả memories về Root
    ↓
Root Agent tổng hợp → stream response về client
```

### Tại sao chọn AgentTool thay vì ParallelAgent/SequentialAgent?

| | AgentTool | ParallelAgent |
|--|-----------|---------------|
| **Control** | Root tự quyết định khi nào gọi agent nào | Luôn chạy cả hai dù không cần |
| **Cost** | Chỉ tốn khi được gọi | Tốn cả hai mọi request |
| **Retry** | Mỗi agent tự retry query | Khó retry selective |
| **Context** | Request cụ thể từ Root | Không rõ ràng |
| **Parallel** | Gemini native parallel function calls | Cũng parallel |

---

## AgentTool — Cơ chế giao tiếp (xác nhận từ source code)

### Input: Root → Sub-agent

Root Agent gọi sub-agent với một `request` string. ADK chuyển thành:

```python
# agent_tool.py (ADK source)
content = Content(role='user', parts=[Part.from_text(text=args['request'])])
```

Sub-agent nhận request như **user message** — hoàn toàn như user gõ vào.

Root Agent **phải** formulate request rõ ràng, ví dụ:
```
"Tìm thông tin về ngân sách Q1 2024: số tiền phê duyệt, hạng mục chi tiêu,
 người phụ trách. Mục đích: trả lời câu hỏi budget Q1 được duyệt bao nhiêu."
```

### Session State

```python
# AgentTool copy toàn bộ parent state sang sub-agent (lọc bỏ _adk internal)
state_dict = {k: v for k, v in parent_state.items() if not k.startswith('_adk')}
# → sub-agent có user_id, max_context_messages, v.v.

# State delta từ sub-agent được propagate ngược về parent
if event.actions.state_delta:
    tool_context.state.update(event.actions.state_delta)
```

### Output: Sub-agent → Root

```python
# AgentTool lấy last_content từ sub-agent
merged_text = '\n'.join(p.text for p in last_content.parts
                        if p.text and not p.thought)
# → trả raw text về Root (với skip_summarization=True)
```

**`skip_summarization=True` là bắt buộc** — nếu False, ADK summarize output trước khi trả Root, mất chi tiết.

### Sub-agent Session

Sub-agents dùng `InMemorySessionService` (ephemeral per-invocation), **không** dùng DynamoDB. Chỉ Root Agent session mới được persist.

---

## Model Hierarchy

```
gemini-2.5-flash        Root Agent
  ↳ reasoning phức tạp, tổng hợp nhiều nguồn, điều phối

gemini-2.0-flash        DocsAgent, MeetingAgent, Summarization
  ↳ retrieval + extraction (không cần reasoning sâu)
  ↳ ⚠️ gemini-2.0-flash-lite đã deprecated (404 NOT_FOUND)
```

Config tại: `backend/app/core/llm_config.yaml`

---

## Context Management

### ContextFilterPlugin (`agents/plugins/context_filter_plugin.py`)

Chạy như `before_model_callback` **chỉ trên Root Agent**, không ảnh hưởng sub-agents.

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
SUMMARY_THRESHOLD=22       # = max_context + 2, đóng gap
SUMMARY_KEEP_RECENT=10     # messages gần nhất giữ lại
```

---

## RAG Retrieval Pipeline

### search_documents (DocsAgent)

```python
async def search_documents(query, tool_context):
    # 1. Embed query với RETRIEVAL_QUERY task type (cache LRU 256 entries)
    query_vector = list(get_query_embedding(query))
    
    # 2. Qdrant search trong asyncio.to_thread (không block event loop)
    results = await asyncio.to_thread(_search, repo, query, user_id, settings)
    
    # 3. Score threshold = 0.6 (loại kết quả không liên quan)
    # 4. Top-k = 5
```

### search_meeting_transcripts (MeetingAgent)

Cùng pattern, search trong collection `meetings` thay vì `rag_documents`.

### retrieve_memories (Root Agent)

```python
def retrieve_memories(query, tool_context):
    # Search limit=15 (rộng hơn) → sort by score → top-7
    raw = repo.search_memory(query, user_id, limit=15)
    ranked = sorted(raw, key=lambda m: m.get("score", 0), reverse=True)
    return ranked[:7]
```

---

## Files liên quan

```
backend/app/agents/
  root_agent.py          Root Agent definition + AgentTool wiring
  docs_agent.py          DocsAgent (search_documents, list_user_documents)
  meeting_agent.py       MeetingAgent (search_meeting_transcripts)
  plugins/
    context_filter_plugin.py  Context summarization callback
  tools/
    qdrant_search_tool.py     search_documents tool
    meeting_search_tool.py    search_meeting_transcripts tool
    mem0_tools.py             retrieve_memories, store_memory
    files_retrieval_tool.py   list_user_documents

backend/app/core/
  llm_config.yaml        Model names, temperatures, system prompts cho cả 3 agents
  llm_config.py          Pydantic models cho config

backend/app/utils/
  gemini_utils.py        get_query_embedding (cached), _with_retry (backoff 429)
```

---

## Retry & Rate Limiting

```python
# gemini_utils._with_retry()
# Tự động retry khi gặp 429 RESOURCE_EXHAUSTED
# Max 3 attempts, exponential backoff với jitter

attempt=1 → delay ~1.0s
attempt=2 → delay ~2.x s (+ random jitter)
attempt=3 → delay ~4.x s (capped at 10s)
```

Áp dụng cho: `expand_query()`, `_generate_summary()`.

---

## Thêm Sub-agent mới

1. Tạo `backend/app/agents/<name>_agent.py`:
```python
@lru_cache
def get_<name>_agent() -> LlmAgent:
    config = get_llm_config()
    return LlmAgent(
        name="<name>_agent",
        model=config.llm.retrieval_model,
        description="...",  # Root dùng description để quyết định khi nào gọi
        instruction=config.prompts.<name>_agent_instruction,
        tools=[...],
        generate_content_config=GenerateContentConfig(temperature=0.1, ...),
    )
```

2. Thêm instruction vào `backend/app/core/llm_config.yaml`:
```yaml
prompts:
  <name>_agent_instruction: |
    ## VAI TRÒ
    ...
    ## QUY TRÌNH
    ...
    ## RÀNG BUỘC
    ...
```

3. Thêm `PromptsSettings.<name>_agent_instruction` vào `llm_config.py`.

4. Đăng ký trong `root_agent.py`:
```python
AgentTool(agent=get_<name>_agent(), skip_summarization=True),
```

5. Cập nhật `system_instruction` của Root Agent để biết khi nào delegate cho agent mới.
