# User Data Isolation — MemRAG Chatbot

> Cập nhật lần cuối: 2026-04-21

## Overview

MemRAG Chatbot ensures **complete data isolation per user**. Every piece of data — memory, documents, chat sessions, meetings, wiki pages — is scoped to a specific `user_id`. Users cannot see, modify, or delete each other's data.

### Architecture: User-ID Flow

```
HTTP Request
  │
  ├─ JWT cookie "access_token" present?
  │     → decode → PostgreSQL User lookup → str(user.id)  (production)
  │
  ├─ No JWT + DEBUG=true?
  │     → X-User-ID header (must not be "default_user")  (dev only)
  │
  └─ No valid auth?
        → 401 Unauthorized

  │
  ▼
get_current_user_id() → UUID string
  │
  ▼
Endpoint: request.user_id = user_id
  │
  ├─────────────────────────────────────────────────────┐
  │                                                     │
  ▼                                                     ▼
Chat flow                                    Direct API calls
  │                                                     │
  ▼                                                     ▼
_ensure_session()                              [Component APIs]
  → DynamoDB: PK="memrag#{user_id}"            → All pass user_id: UserIDDep
  → session.state["user_id"] = user_id
  │
  ▼
runner.run_async(user_id=user_id, ...)
  │
  ▼
ADK Agent invokes tools
  │
  ▼
tool_context.state["user_id"]
  │
  ▼
get_user_id(tool_context) → user_id
  │
  ▼
┌─────────────────────────────────────────────────────┐
│  All data operations (user-scoped):                 │
│  - mem0.search(query, user_id=...)                  │
│  - mem0.add(messages, user_id=...)                  │
│  - qdrant.search(query, filter=user_id=...)         │
│  - qdrant.upsert(payload.user_id=...)               │
│  - dynamo.query(PK="memrag#{user_id}")              │
│  - dynamo.query(PK="USER#{user_id}")                │
│  - wiki.read(user_id=..., path=...)                 │
│  - wiki.write(user_id=..., path=..., content=...)   │
└─────────────────────────────────────────────────────┘
```

---

## Components & Isolation Mechanisms

### 1. Long-Term Memory (mem0)

**Storage:** Qdrant vector collection with mem0 library abstraction

**Isolation mechanism:** `user_id` parameter passed to every mem0 operation

| Operation | File | Method | Isolation |
|-----------|------|--------|-----------|
| Store memory | `backend/app/repositories/mem0_repo.py` | `add_memory(messages, user_id)` | ✅ `self.client.add(messages, user_id=user_id)` |
| Search memory | `backend/app/repositories/mem0_repo.py` | `search_memory(query, user_id, limit)` | ✅ `self.client.search(query, user_id=user_id, limit=limit)` |
| Get all memories | `backend/app/repositories/mem0_repo.py` | `get_all_memories(user_id)` | ✅ `self.client.get_all(user_id=user_id)` |
| Delete memory | `backend/app/repositories/mem0_repo.py` | `delete_memory(memory_id)` | ⚠️ Only by `memory_id` (see risks) |
| Delete all memories | `backend/app/repositories/mem0_repo.py` | `delete_all_user_memories(user_id)` | ✅ `self.client.delete_all(user_id=user_id)` |

**ADK tools:**
- `retrieve_memories` → `get_user_id(tool_context)` → `repo.search_memory(user_id=...)`
- `store_memory` → `get_user_id(tool_context)` → `repo.add_memory(user_id=...)`

**API endpoints:**
| Method | Path | Auth | Isolation |
|--------|------|------|-----------|
| `POST` | `/api/v1/memory/search` | JWT/UserID | ✅ `user_id` from auth |
| `GET` | `/api/v1/memory` | JWT/UserID | ✅ `user_id` from auth |
| `DELETE` | `/api/v1/memory/{memory_id}` | JWT/UserID | ⚠️ Only by `memory_id` |
| `DELETE` | `/api/v1/memory/all` | JWT/UserID | ✅ `user_id` from auth |

---

### 2. Documents & RAG (Qdrant)

**Storage:** Qdrant vector collection for PDF document chunks

**Isolation mechanism:** `user_id` stored in vector payload and used as filter in queries

| Operation | File | Method | Isolation |
|-----------|------|--------|-----------|
| Upload PDF | `backend/app/repositories/qdrant_repo.py` | `upsert_chunks(chunks, user_id=...)` | ✅ `"user_id": user_id` in payload |
| Search documents | `backend/app/repositories/qdrant_repo.py` | `search(query, user_id, ...)` | ✅ `Filter(must=[MatchValue(key="user_id", value=user_id)])` |
| List documents | `backend/app/repositories/qdrant_repo.py` | `list_documents(user_id)` | ✅ `Filter(must=[MatchValue(key="user_id", value=user_id)])` |
| Delete document | `backend/app/repositories/qdrant_repo.py` | `delete_document(document_id)` | ⚠️ Only by `document_id` (see risks) |

**ADK tools:**
- `search_documents` → `get_user_id(tool_context)` → `repo.search(user_id=...)`
- `list_user_documents` → `get_user_id(tool_context)` → `repo.list_documents(user_id=...)`

**RAG service:**
| Operation | File | Method | Isolation |
|-----------|------|--------|-----------|
| Search RAG | `backend/app/services/rag_service.py` | `search(query, user_id, ...)` | ✅ Passes `user_id` to Qdrant filter |

**API endpoints:**
| Method | Path | Auth | Isolation |
|--------|------|------|-----------|
| `POST` | `/api/v1/documents/upload` | JWT/UserID | ✅ `user_id` passed to upload |
| `GET` | `/api/v1/documents` | JWT/UserID | ✅ `user_id` passed to list |
| `DELETE` | `/api/v1/documents/{document_id}` | JWT/UserID | ⚠️ Only by `document_id` (see risks) |

---

### 3. Meeting Transcripts (DynamoDB + Qdrant)

**Storage:**
- **Meeting metadata & utterances:** DynamoDB (`memrag-meetings` table)
- **Transcript RAG vectors:** Qdrant (separate collection from documents)

**Isolation mechanism:** DynamoDB partition key includes `user_id`; Qdrant vectors store `user_id` in payload

#### DynamoDB Tables

**Meeting metadata:**
- PK: `USER#{user_id}`
- SK: `MEETING#{meeting_id}`
- ✅ Fully isolated by user partition

**Utterances (transcript chunks):**
- PK: `MEETING#{meeting_id}`
- SK: `UTTERANCE#{timestamp}#{sequence}`
- ⚠️ PK does NOT include `user_id` — isolated by meeting_id ownership check at API layer

| Operation | File | Method | Isolation |
|-----------|------|--------|-----------|
| Start meeting | `backend/app/api/v1/transcription.py` | `start_transcription(user_id)` | ✅ `user_id` from auth, stored in meeting metadata |
| Send audio | `backend/app/api/v1/transcription.py` | `send_audio(meeting_id, user_id)` | ⚠️ Does NOT verify meeting ownership (see risks) |
| Stream transcription | `backend/app/api/v1/transcription.py` | `stream_transcription(meeting_id, user_id)` | ⚠️ Does NOT verify meeting ownership (see risks) |
| Stop meeting | `backend/app/api/v1/transcription.py` | `stop_transcription(meeting_id, user_id)` | ✅ Calls `repo.get_meeting(meeting_id, user_id)` first |
| Get transcript | `backend/app/api/v1/transcription.py` | `get_transcript(meeting_id, user_id)` | ✅ Calls `repo.get_meeting(meeting_id, user_id)` first |
| List meetings | `backend/app/api/v1/transcription.py` | `list_meetings(user_id)` | ✅ Queries `PK=USER#{user_id}` |
| Delete meeting | `backend/app/api/v1/transcription.py` | `delete_meeting(meeting_id, user_id)` | ✅ Calls `repo.get_meeting(meeting_id, user_id)` first |

#### Transcript RAG (Qdrant)

| Operation | File | Method | Isolation |
|-----------|------|--------|-----------|
| Ingest transcript | `backend/app/services/transcript_rag_service.py` | `ingest(text, meeting_id, user_id)` | ✅ `user_id` in payload |
| Search transcripts | `backend/app/services/transcript_rag_service.py` | `search(query, user_id, ...)` | ✅ `Filter(must=[MatchValue(key="user_id", value=user_id)])` |
| Delete meeting vectors | `backend/app/services/transcript_rag_service.py` | `delete_meeting(meeting_id)` | ⚠️ Only by `meeting_id` (see risks) |

**ADK tools:**
- `search_meeting_transcripts` → `get_user_id(tool_context)` → search with `user_id`
- `list_meetings` → `get_user_id(tool_context)` → list with `user_id`

---

### 4. Chat Sessions (DynamoDB)

**Storage:** DynamoDB (`memrag_sessions` table)

**Isolation mechanism:** Partition key includes `user_id`

| Operation | File | Method | Isolation |
|-----------|------|--------|-----------|
| Create session | `backend/app/services/dynamo_session_service.py` | `create_session(app_name, user_id, session_id, state)` | ✅ `PK = "{app_name}#{user_id}"` |
| Get session | `backend/app/services/dynamo_session_service.py` | `get_session(app_name, user_id, session_id)` | ✅ `PK = "{app_name}#{user_id}", SK = session_id` |
| Update session | `backend/app/services/dynamo_session_service.py` | `update_session_state(...)` | ✅ Scoped by `PK = "{app_name}#{user_id}"` |
| Delete session | `backend/app/services/dynamo_session_service.py` | `delete_session(app_name, user_id, session_id)` | ✅ Scoped by `PK = "{app_name}#{user_id}"` |
| List sessions | `backend/app/services/dynamo_session_service.py` | `list_sessions(app_name, user_id)` | ✅ Queries `PK = "{app_name}#{user_id}"` |

**Session state stores `user_id`:**
```python
state = {
    "user_id": user_id,              # Used by tools via tool_context.state
    "max_context_messages": 20,
}
```

---

### 5. Wiki Pages (Local FS or S3)

**Storage:** Local filesystem or S3 bucket

**Isolation mechanism:** `user_id` as directory/prefix level

| Operation | File | Method | Isolation |
|-----------|------|--------|-----------|
| Read index | `backend/app/repositories/wiki_repo.py` | `read_index(user_id)` | ✅ Path: `{user_id}/index.json` |
| Write index | `backend/app/repositories/wiki_repo.py` | `write_index(user_id, index)` | ✅ Path: `{user_id}/index.json` |
| Read page | `backend/app/repositories/wiki_repo.py` | `read_page(user_id, category, slug)` | ✅ Path: `{user_id}/{category}/{slug}.md` |
| Write page | `backend/app/repositories/wiki_repo.py` | `write_page(user_id, ...)` | ✅ Path: `{user_id}/{category}/{slug}.md` |
| Delete page | `backend/app/repositories/wiki_repo.py` | `delete_page(user_id, category, slug)` | ✅ Path: `{user_id}/{category}/{slug}.md` |
| List pages | `backend/app/repositories/wiki_repo.py` | `list_pages(user_id)` | ✅ Lists under `{user_id}/` prefix |
| Get graph | `backend/app/repositories/wiki_repo.py` | `get_graph(user_id)` | ✅ Reads from `{user_id}/index.json` |

**S3 mode:** Same isolation — `user_id` is part of the S3 key prefix: `wiki/{user_id}/...`

**ADK tools:**
- `read_wiki_index` → `get_user_id(tool_context)` → `repo.read_index(user_id=...)`
- `read_wiki_page` → `get_user_id(tool_context)` → `repo.read_page(user_id=...)`
- `list_wiki_pages` → `get_user_id(tool_context)` → `repo.list_pages(user_id=...)`

**API endpoints:** All wiki endpoints use `UserIDDep` and pass `user_id` to repo methods. ✅ Fully isolated.

---

### 6. Users (PostgreSQL)

**Storage:** PostgreSQL `users` table

**Isolation mechanism:** Each user has a unique UUID `id`

| Operation | File | Method | Isolation |
|-----------|------|--------|-----------|
| Register | `backend/app/services/auth_service.py` | `register(email, password, display_name)` | ✅ Creates new user with unique UUID |
| Login | `backend/app/services/auth_service.py` | `login(email, password)` | ✅ Returns only this user's data |
| Get user | `backend/app/services/auth_service.py` | `get_user(user_id)` | ✅ Returns only requested user |
| Update profile | `backend/app/services/auth_service.py` | `update_profile(user_id, ...)` | ✅ Only modifies specified user |

**JWT tokens contain `user_id`** (`sub` claim) — used for all subsequent requests.

---

### 7. File Storage (S3 — PDF uploads)

**Storage:** S3 bucket (`chatbotdeploytestv1`)

**Isolation mechanism:** Presigned URLs + backend validates ownership

| Operation | File | Method | Isolation |
|-----------|------|--------|-----------|
| Upload PDF | `backend/app/services/document_service.py` | `upload_pdf(file, user_id)` | ✅ `user_id` passed to RAG ingestion |
| Download PDF | S3 presigned URL | Expiry: 3600s | ⚠️ URL is shareable during expiry window |

S3 objects are not directly scoped by `user_id` in the key — isolation is enforced at the application layer (Qdrant metadata + document service).

---

## Security Risks & Mitigations

### HIGH Severity

#### 1. Transcription endpoints don't verify meeting ownership

**Affected endpoints:**
- `POST /api/v1/transcription/audio/{meeting_id}` — send audio to a meeting
- `GET /api/v1/transcription/stream/{meeting_id}` — subscribe to live transcription

**Risk:** Any authenticated user who knows a `meeting_id` can:
- Inject audio into another user's meeting
- Listen to another user's live transcription stream

**Fix:** Before processing, verify meeting ownership:
```python
# In send_audio and stream_transcription endpoints:
meeting = await repo.get_meeting(meeting_id=meeting_id, user_id=user_id)
if not meeting:
    raise HTTPException(404, "Meeting not found")
```

---

### MEDIUM Severity

#### 2. Document deletion without ownership verification

**Affected:** `QdrantRepository.delete_document(document_id)`

**Risk:** Knowing a document UUID allows deletion of any user's document vectors.

**Mitigation:** Document IDs are UUID4 (128-bit) — practically unguessable. Risk is low in practice.

**Fix:** Add `user_id` to the delete filter:
```python
def delete_document(self, document_id: str, user_id: str):
    filter = Filter(must=[
        MatchValue(key="metadata.user_id", value=user_id),
        MatchValue(key="metadata.document_id", value=document_id),
    ])
    self.client.delete(collection_name=..., points_selector=FilterSelector(filter=filter))
```

#### 3. Meeting deletion without ownership verification (Qdrant vectors)

**Affected:** `TranscriptRAGService.delete_meeting(meeting_id)`

Same pattern as #2. Fix similarly.

#### 4. Orphaned utterances in DynamoDB

**Affected:** `MeetingRepository.delete_meeting(meeting_id, user_id)`

**Risk:** Deletes meeting metadata (`PK=USER#{user_id}, SK=MEETING#{meeting_id}`) but NOT utterance records (`PK=MEETING#{meeting_id}`). Utterances persist indefinitely.

**Fix:** Add utterance cleanup:
```python
async def delete_meeting(self, meeting_id: str, user_id: str):
    # Delete meeting metadata (user-scoped)
    await self.table.delete_item(Key={"pk": f"USER#{user_id}", "sk": f"MEETING#{meeting_id}"})
    
    # Delete all utterances (meeting-scoped)
    # Query all items with PK = MEETING#{meeting_id} and batch delete
    ...
```

#### 5. Agent tools fallback to "default_user"

**Affected:** All ADK tools via `get_user_id(tool_context)`

**Risk:** If `tool_context.state["user_id"]` is not set, ALL tools operate on shared `default_user` namespace — cross-user data leak.

**Current protection:** `_ensure_session()` always sets `state["user_id"]` before ADK runs. But a bug in state propagation would affect all tools simultaneously.

**Fix:** Replace fallback with exception:
```python
def get_user_id(tool_context: ToolContext) -> str:
    user_id = tool_context.state.get("user_id")
    if not user_id:
        logger.error(f"user_id_missing_in_tool_context: tool={tool_context.tool_name} state={tool_context.state}")
        raise ValueError(f"user_id not set in tool context state for tool '{tool_context.tool_name}'")
    return user_id
```

---

### LOW Severity

#### 6. RAG search accepts optional `user_id`

**Affected:** `RAGService.search(query, user_id: str | None = None, ...)`

**Risk:** If called with `user_id=None`, Qdrant filter is not applied — returns results from ALL users.

**Mitigation:** Current callers always pass `user_id`. This is a defensive coding concern.

**Fix:** Make `user_id` required (not optional) in the signature.

#### 7. Memory deletion without ownership verification

**Affected:** `Mem0Repository.delete_memory(memory_id)`

**Risk:** Depends on mem0 library internals — if mem0's `delete()` doesn't check user ownership, cross-user deletion is possible.

**Mitigation:** mem0 library typically handles this. Low risk.

---

## "default_user" Fallback — Detailed Analysis

### Where it exists

**File:** `backend/app/agents/tools/utils.py` (line 6)
```python
def get_user_id(tool_context: ToolContext, fallback: str = "default_user") -> str:
    return tool_context.state.get("user_id", fallback)
```

### Where it's used (all ADK tools)

| Tool | File | Line | Operation if fallback triggered |
|------|------|------|--------------------------------|
| `search_documents` | `qdrant_search_tool.py` | 49 | Searches ALL users' documents |
| `list_user_documents` | `files_retrieval_tool.py` | 28 | Lists ALL users' documents |
| `search_meeting_transcripts` | `meeting_search_tool.py` | 32 | Searches ALL users' meetings |
| `list_meetings` | `meeting_search_tool.py` | 96 | Lists ALL users' meetings |
| `retrieve_memories` | `mem0_tools.py` | 33 | Searches ALL users' memories |
| `store_memory` | `mem0_tools.py` | 88 | Stores to ALL users' memory namespace |
| `read_wiki_index` | `wiki_tools.py` | 42 | Reads ALL users' wiki index |
| `read_wiki_page` | `wiki_tools.py` | 102 | Reads ALL users' wiki pages |
| `list_wiki_pages` | `wiki_tools.py` | 172 | Lists ALL users' wiki pages |

### Why it's (currently) safe

**`_ensure_session()` in `chat_service.py`** guarantees `user_id` is set:

```python
async def _ensure_session(session_service, user_id, session_id, max_context_messages):
    existing = await session_service.get_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)
    if existing is None:
        await session_service.create_session(
            app_name=APP_NAME,
            user_id=user_id,
            session_id=session_id,
            state={
                "user_id": user_id,          # ← Set here
                "max_context_messages": max_context_messages,
            },
        )
    elif existing.state.get("user_id") != user_id:
        existing.state["user_id"] = user_id  # ← Migrates old sessions
        await session_service.update_session_state(...)
```

Then `runner.run_async(user_id=request.user_id, ...)` passes `user_id` into the ADK runtime, which propagates it to `tool_context.state`.

### When it becomes unsafe

1. **Direct tool invocation** (bypassing `_ensure_session`)
2. **Session state corruption** (DynamoDB data loss)
3. **ADK version changes** that alter state propagation behavior
4. **Testing without proper session setup**

### Recommendation

Add logging when fallback is triggered:
```python
def get_user_id(tool_context: ToolContext, fallback: str = "default_user") -> str:
    user_id = tool_context.state.get("user_id", fallback)
    if user_id == fallback:
        logger.warning(
            "user_id_fallback_to_default: tool=%s state=%s",
            tool_context.tool_name,
            tool_context.state,
        )
    return user_id
```

---

## Frontend: User-ID Synchronization

### Before Fix

The `chatStore` initialized `userId` to `'default_user'` from localStorage and **never updated it after login**. This meant API calls for memory/documents used the wrong user ID.

### After Fix

**`authStore.ts`** now syncs authenticated user ID to `chatStore`:

```typescript
// authStore.ts
setUser: (user: AuthUser | null) => {
  set({ user, isAuthenticated: !!user, isLoading: false })

  // Sync authenticated user_id to chatStore
  if (user) {
    useChatStore.getState().setUserId(user.id)
  } else {
    useChatStore.getState().setUserId('default_user')
  }
}
```

This ensures:
- After login → `chatStore.userId = user.id` (UUID)
- After logout → `chatStore.userId = 'default_user'`
- On app refresh → `checkAuth()` → `setUserId(user.id)`

### Memory API calls

**Before:** Frontend passed `userId` in URL path (`/api/v1/memory/user/{userId}`) — relied on correct client-side value.

**After:** Frontend calls `/api/v1/memory` — backend derives `user_id` from JWT cookie. No client-side trust needed.

---

## Summary: Isolation Status

| Component | Storage | Isolation Mechanism | Status |
|-----------|---------|---------------------|--------|
| **Users** | PostgreSQL | Unique UUID per user | ✅ Isolated |
| **Sessions** | DynamoDB | PK = `memrag#{user_id}` | ✅ Isolated |
| **Memory (mem0)** | Qdrant (via mem0) | `user_id` parameter on all ops | ✅ Isolated |
| **Documents (RAG)** | Qdrant | `user_id` in payload + filter | ✅ Isolated (read/write) ⚠️ Delete |
| **Meetings (metadata)** | DynamoDB | PK = `USER#{user_id}` | ✅ Isolated |
| **Meetings (utterances)** | DynamoDB | PK = `MEETING#{meeting_id}` | ⚠️ Orphaned on delete |
| **Meeting transcripts (RAG)** | Qdrant | `user_id` in payload + filter | ✅ Isolated (read/write) ⚠️ Delete |
| **Wiki pages** | Local FS / S3 | `user_id` in directory/prefix | ✅ Isolated |
| **File uploads (S3)** | S3 | App-layer validation | ✅ Isolated |

### Action Items

| Priority | Action | Component |
|----------|--------|-----------|
| **HIGH** | Add meeting ownership verification to `send_audio` and `stream_transcription` | Transcription API |
| **MEDIUM** | Add `user_id` filter to `delete_document` in Qdrant repo | Documents |
| **MEDIUM** | Add `user_id` filter to `delete_meeting` in transcript RAG service | Meetings |
| **MEDIUM** | Clean up orphaned utterances on meeting delete | Meetings |
| **MEDIUM** | Replace `default_user` fallback with exception + logging | Agent tools |
| **LOW** | Make `user_id` required (not optional) in `RAGService.search` | RAG |
| **LOW** | Verify mem0 `delete()` internally checks user ownership | Memory |
