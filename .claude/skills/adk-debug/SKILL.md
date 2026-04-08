---
name: adk-debug
description: Diagnose và fix các vấn đề liên quan đến Google ADK agents, tools, session state, multi-agent communication trong dự án MemRAG.
---

Khi được gọi với `/adk-debug`, thực hiện theo đúng quy trình sau:

## Bước 1 — Xác định loại vấn đề

Hỏi user (hoặc đọc từ context) lỗi thuộc nhóm nào:

| Nhóm | Triệu chứng điển hình |
|------|----------------------|
| **A. Tool không được gọi** | Agent trả lời không dùng data từ Qdrant/mem0 |
| **B. Sub-agent không nhận đúng request** | DocsAgent/MeetingAgent tìm sai thông tin |
| **C. Session state bị mất** | `user_id` undefined, memories không persist |
| **D. 429 RESOURCE_EXHAUSTED** | Gemini API rate limit |
| **E. Context / summary sai** | Summary mất thông tin, truncation không mong muốn |
| **F. AgentTool trả về rỗng** | Sub-agent chạy nhưng Root không nhận được kết quả |

---

## Bước 2 — Diagnose theo nhóm

### Nhóm A: Tool không được gọi

Kiểm tra:
```python
# 1. Tool có đúng signature không? (phải có ToolContext)
async def search_documents(query: str, tool_context: ToolContext) -> dict:

# 2. Tool có trong danh sách của agent không?
agent.tools  # DocsAgent chỉ có search_documents + list_user_documents

# 3. Tool description đủ rõ để LLM biết khi nào gọi không?
# Đọc: backend/app/core/llm_config.yaml → docs_agent_instruction
```

Đọc log để xem tool có được trigger:
```bash
docker compose logs backend -f | grep "qdrant_search_done\|meeting_search_done\|memories_retrieved"
```

### Nhóm B: Sub-agent không nhận đúng request

**Nguyên nhân phổ biến**: Root Agent formulate request quá chung chung.

Kiểm tra system prompt của Root Agent:
```
backend/app/core/llm_config.yaml → prompts.system_instruction
```

Root phải ghi rõ trong request: *thông tin cần gì* + *mục đích để trả lời câu hỏi gì*.

Kiểm tra AgentTool được khai báo đúng:
```python
# backend/app/agents/root_agent.py
AgentTool(agent=get_docs_agent(), skip_summarization=True)
#                                  ^^^^^^^^^^^^^^^^^^^^^
#                                  BẮT BUỘC = True, nếu False ADK sẽ
#                                  summarize mất chi tiết trước khi trả Root
```

### Nhóm C: Session state bị mất

AgentTool copy state từ parent sang sub-agent (confirmed từ ADK source):
```python
state_dict = {k: v for k, v in tool_context.state.to_dict().items()
              if not k.startswith('_adk')}
```

Kiểm tra `user_id` có trong session state khi session được tạo:
```python
# backend/app/services/chat_service.py → _ensure_session()
state={"user_id": user_id, "max_context_messages": max_context_messages}
```

Nếu tool không đọc được `user_id`:
```python
user_id = tool_context.state.get("user_id")  # có thể None nếu session cũ
user_id = tool_context.state.get("user_id", "default_user")  # safe fallback
```

### Nhóm D: 429 RESOURCE_EXHAUSTED

Kiểm tra config:
```bash
# backend/app/core/config.py — không có query_expansion nữa (đã bỏ)
# Nếu vẫn 429, giảm concurrency hoặc kiểm tra model names
```

Model names hợp lệ (cập nhật 2026-04):
```yaml
# backend/app/core/llm_config.yaml
llm:
  model: "gemini-2.5-flash"       # Root Agent
  retrieval_model: "gemini-2.0-flash"  # Sub-agents
  summary_model: "gemini-2.0-flash"    # Summarization
# ⚠️ gemini-2.0-flash-lite đã bị deprecated (404 NOT_FOUND)
```

Retry được implement tự động trong `gemini_utils._with_retry()`:
- Max 3 attempts, exponential backoff 1s/2s/4s + jitter

### Nhóm E: Context / summary sai

Kiểm tra các thresholds:
```python
# backend/app/core/config.py
max_context_messages: int = 20   # n <= 20: pass through
summary_threshold: int = 22      # n > 20: luôn summarize (không truncate)
summary_keep_recent: int = 10    # giữ 10 messages gần nhất
```

Background summarization (lần re-summary):
- Lần đầu chưa có summary → **blocking** (phải chờ)
- Lần sau đã có summary → **fire-and-forget** (không block LLM)

Kiểm tra summary được lưu đúng:
```python
# Trong session state (persist DynamoDB):
callback_context.state["conversation_summary"]   # nội dung summary
callback_context.state["summary_covered_count"]  # số messages đã cover
```

### Nhóm F: AgentTool trả về rỗng

Từ source code ADK `agent_tool.py:266-275`:
```python
if last_content is None or last_content.parts is None:
    return ''  # ← trả rỗng nếu sub-agent không emit content
merged_text = '\n'.join(p.text for p in last_content.parts
                        if p.text and not p.thought)
```

Nguyên nhân thường gặp:
1. Sub-agent chỉ gọi tool nhưng không generate text response cuối
2. Sub-agent raise exception → bị catch và trả `''`
3. `skip_summarization=False` → ADK overwrite content với summary rỗng

Fix: đảm bảo sub-agent instruction yêu cầu nó **luôn trả lời bằng text** sau khi dùng tool.

---

## Bước 3 — Kiểm tra nhanh toàn bộ agent stack

```bash
cd /home/minhdd/pet_proj/proj2/backend

# 1. Import check — phát hiện circular import, syntax error
uv run python -c "
from app.agents.root_agent import get_root_agent
agent = get_root_agent()
tools = [(t.__class__.__name__, getattr(t, 'agent', None) and t.agent.name or getattr(t, '__name__', '?')) for t in agent.tools]
print('Root tools:', tools)
print('Root model:', agent.model)
from app.agents.docs_agent import get_docs_agent
da = get_docs_agent()
print('DocsAgent model:', da.model)
print('DocsAgent tools:', [t.__name__ for t in da.tools])
from app.agents.meeting_agent import get_meeting_agent
ma = get_meeting_agent()
print('MeetingAgent model:', ma.model)
print('MeetingAgent tools:', [t.__name__ for t in ma.tools])
"

# 2. Test suite
uv run pytest tests/ -v --tb=short

# 3. Lint
uv run ruff check .
```

---

## Bước 4 — Files quan trọng cần đọc khi debug

| Vấn đề | File |
|--------|------|
| Agent tools, model config | `backend/app/core/llm_config.yaml` |
| Agent prompts (system, docs, meeting) | `backend/app/core/llm_config.yaml` |
| Root / Docs / Meeting agent setup | `backend/app/agents/{root,docs,meeting}_agent.py` |
| Context filter & summarization | `backend/app/agents/plugins/context_filter_plugin.py` |
| Qdrant search tool | `backend/app/agents/tools/qdrant_search_tool.py` |
| Meeting search tool | `backend/app/agents/tools/meeting_search_tool.py` |
| Memory tools | `backend/app/agents/tools/mem0_tools.py` |
| Gemini utils + retry | `backend/app/utils/gemini_utils.py` |
| Session state setup | `backend/app/services/chat_service.py → _ensure_session()` |

---

## ADK Gotchas quan trọng (từ source code)

1. **AgentTool tạo `InMemorySessionService` mới** cho mỗi invocation — sub-agent sessions là ephemeral, KHÔNG lưu DynamoDB.

2. **State sharing**: Parent state được copy sang sub-agent. State delta từ sub-agent được propagate ngược về parent.

3. **`skip_summarization=True` là bắt buộc** — nếu False, ADK tự summarize output sub-agent trước khi trả Root, có thể mất chi tiết.

4. **Một agent chỉ có thể là `sub_agents` của một parent** — nhưng `AgentTool` là pattern khác, không có giới hạn này.

5. **Model deprecated**: `gemini-2.0-flash-lite` → 404. Dùng `gemini-2.0-flash`.
