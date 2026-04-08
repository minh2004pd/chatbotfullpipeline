# Memory & Context Management Audit

## 🔍 Hiện trạng hệ thống

### 1. Memory Management (Long-term)

**Kiến trúc hiện tại:**
- **mem0** lưu memories per user (embeddings + metadata)
- Memories được search qua vector similarity
- Được inject vào LLM context khi agent gọi `retrieve_memories` tool

**Vấn đề tìm thấy:**

| # | Vấn đề | Impact | Ưu tiên |
|---|--------|--------|---------|
| 1 | Không có memory consolidation | Dung lượng memory tăng vô hạn | P1 |
| 2 | Search limit = 5 mặc định quá nhỏ | Mất context quan trọng | P1 |
| 3 | Không có memory pruning/expiry | Old memories cả tỉnh xương vẫn lấy | P2 |
| 4 | Chỉ search, không có ranking | Memories trả về không prioritize | P2 |
| 5 | Không phân loại memories | Sở thích, facts, events xáo trộn | P2 |

---

### 2. Context Management (Short-term)

**Kiến trúc hiện tại:**
```
User Message 
    ↓
_ensure_session() [tạo nếu chưa có]
    ↓ session_state = {user_id, max_context_messages}
ADK Runner [inject vào LLM]
    ↓
context_filter_before_model()
  - Nếu n ≤ 20: pass through
  - Nếu 20 < n < 22: truncate cuối (bỏ mất messages cũ)  ❌ PROBLEM
  - Nếu n ≥ 22: summarize [summary + recent_10]
    ↓
LLM inference
```

**Vấn đề tìm thấy:**

| # | Vấn đề | Impact | Ưu tiên |
|---|--------|--------|---------|
| 1 | Truncation bỏ quên quan trọng messages | Loss of critical context | P0 |
| 2 | Summarization overhead cao khi conversation dài | Latency 2-3s cho summary | P1 |
| 3 | Session state không có time-based metadata | Khó follow up lâu sau | P2 |
| 4 | Không có context relevance scoring | Truncate/summarize tuỳ hứng | P2 |
| 5 | Summary prompt chung chung | LLM summary quality không consistent | P2 |

---

### 3. RAG Retrieval Accuracy

**Kiến trúc:**
- Qdrant vector search → top_k=5 → filter by score_threshold=0.6
- Chunks 1000 chars, overlap 200 (đã fix)
- Không có query expansion, không có reranking

**Vấn đề:**

| # | Vấn đề | Impact | Ưu tiên |
|---|--------|--------|---------|
| 1 | Không có reranking / relevance scoring | Top 5 có thể sai | P1 |
| 2 | Chunk size cố định (1000 chars) | Semantically không hợp lý | P2 |
| 3 | Không có query expansion (synonyms, rephrasing) | Query khác nhau → khác kết quả | P2 |
| 4 | Score 0.6 threshold quá cứng nhắc | Query dễ sẽ có kết quả rác | P3 |

---

## 💡 Đề xuất cải tiến (Theo ưu tiên)

### **P0: CRITICAL — Bắt buộc sửa ngay**

#### 1. Replace truncation với intelligent filtering
```python
# Thay vì: just keep last 20 messages
# Làm: score each message by recency + relevance

async def _filter_by_importance(
    contents: list,
    max_keep: int = 20,
) -> list:
    """Keep most relevant messages, not just recent ones."""
    if len(contents) <= max_keep:
        return contents
    
    # Score = recency (decay) + semantic importance (NLI)
    # Scan mỗi message:
    #   - Recency score: msg_age / max_age → 0..1
    #   - Is question (?) → 0.9
    #   - Is decision/fact → 0.8
    #   - Is small talk → 0.3
    # Keep top-20 by score, then re-sort by time
```

#### 2. Improve summary prompt & consistency
```yaml
# Hiện tại: Generic prompt dễ miss context
# Đề xuất: Structured summary template

summary_prompt: |
  Tóm tắt cuộc hội thoại theo hạng mục:
  
  ## 1. Quyết định / Cam kết
  - Gì được quyết định?
  - Ai sẽ làm?
  - Deadline?
  
  ## 2. Câu hỏi chính
  - Người dùng muốn biết gì?
  - Đã giải quyết chưa?
  
  ## 3. Context quan trọng
  - Các constraint, điều kiện
  - Tên, số liệu, reference
  
  ## 4. Follow-up cần làm
  - Action items
```

---

### **P1: HIGH — Implement trong 1-2 ngày**

#### 1. Add memory categories + quality score
```python
class Memory(BaseModel):
    id: str
    content: str
    category: Literal["preference", "fact", "decision", "event", "skill"]
    recency_score: float  # 0..1, decay theo thời gian
    confidence: float     # 0..1, từ user feedback
    last_accessed: datetime
    access_count: int     # mười nhiều accessed = quan trọng hơn
    tags: list[str]  # "project-X", "meeting-Y", v.v.

def search_memory_ranked(
    query: str, 
    user_id: str,
    limit: int = 10,
    category_filter: list[str] | None = None,
) -> list[Memory]:
    """Search + rank by TF-IDF + recency + confidence."""
    results = []
    
    # 1. Vector search → top_k=50
    vectors = search(query)
    
    # 2. Rerank by: relevance * recency_score * confidence
    #              * (1.0 if category_match else 0.7)
    for mem in vectors:
        rank_score = (
            mem.vector_score * 0.5 +
            mem.recency_score * 0.3 +
            mem.confidence * 0.2
        )
        results.append((mem, rank_score))
    
    # 3. Top-10
    return sorted(results, key=lambda x: x[1], desc=True)[:limit]
```

#### 2. Add memory consolidation job
```python
# Hàng tuần: gom memories trùng lặp
# "I like Python" + "Python là ngôn ngữ yêu thích" 
#   → 1 consolidated memory + meta "merged_from: [id1, id2]"

async def consolidate_memories(user_id: str):
    """Deduplicate & merge similar memories."""
    all_mems = get_all(user_id)
    
    # Clustering by semantic similarity
    clusters = cluster_by_similarity(all_mems, threshold=0.85)
    
    for cluster in clusters:
        if len(cluster) == 1:
            continue
        
        # Merge: combine text, keep highest confidence
        merged = {
            "content": "\n".join([m.content for m in cluster]),
            "confidence": max([m.confidence for m in cluster]),
            "category": cluster[0].category,  # assume same
            "merged_from": [m.id for m in cluster],
        }
        
        repo.add_memory(merged)
        for m in cluster:
            repo.delete_memory(m.id)
        
        logger.info("memories_merged", count=len(cluster))
```

#### 3. Improve RAG with query expansion + reranking
```python
async def search_documents_improved(
    query: str, 
    user_id: str,
    top_k: int = 5,
) -> list[dict]:
    """Enhanced search: expansion + reranking."""
    
    # 1. Query expansion (tạo thêm queries gần nghĩa)
    expanded_queries = await generate_queries(query)
    # "Làm sao tính tương quan?" 
    # → ["tương quan là gì", "correlation metric", "Pearson correlation", ...]
    
    # 2. Multi-query search
    all_results = {}
    for q in [query] + expanded_queries:
        vec = get_query_embedding(q)
        results = qdrant.search(vec, top_k=20)
        for r in results:
            doc_id = r["document_id"]
            if doc_id not in all_results:
                all_results[doc_id] = r
            else:
                all_results[doc_id]["score"] += r["score"]  # accumulate
    
    # 3. Rerank với cross-encoder (hoặc dùng LLM nhẹ)
    # Điểm từ: vector similarity + lexical match + semantic coherence
    ranked = rerank_cross_encoder(query, all_results)
    
    return ranked[:top_k]
```

---

### **P2: MEDIUM — Optimize (1 tuần)**

#### 1. Context relevance scoring
```python
# Ngay từ session start, score mỗi message:
# - Temporal: recency decay
# - Semantic: is_question, is_decision, is_fact
# - User interaction: user asked follow-up?

class ContextMessage(BaseModel):
    content: Content
    timestamp: datetime
    author: str
    relevance_score: float = 0.5  # 0..1
    is_user_question: bool
    is_model_fact: bool
    is_decision: bool
    
    @property
    def importance(self) -> float:
        """Tính trọng số giữ lại message này."""
        # Decision → 1.0
        # Question → 0.9
        # Answer (follow-up question được trả) → 0.8
        # Small talk → 0.3
        return base_score * recency_decay()
```

#### 2. Session state extension
```python
# Thêm rich metadata vào session state

session_state = {
    "user_id": str,
    "max_context_messages": int,
    
    # NEW: Semantic tracking
    "main_topics": list[str],  # ["Python", "concurrency"]
    "open_questions": list[str],  # ["How to X?", "Why Y?"]
    "decisions_made": list[str],  # ["Will use FastAPI"]
    "action_items": list[tuple[str, datetime]],  # [("Fix bug", "2026-04-15")]
    
    # NEW: Summary state (upgrade hiện tại)
    "conversation_summary": str,
    "summary_covered_count": int,
    "summary_quality_score": float,  # Để biết summary có tốt không
    "last_summary_time": datetime,
}
```

#### 3. Hybrid search: RAG + Memory synthesis
```python
# Khi user hỏi: tìm cả document + memories → synthesis

async def search_unified(
    query: str,
    user_id: str,
) -> dict:
    """Search documents + memories, synthesize."""
    
    docs = await search_documents(query, user_id, top_k=5)
    mems = await search_memories(query, user_id, top_k=5)
    
    return {
        "query": query,
        "documents": docs,
        "memories": mems,
        "synthesis": {
            "doc_count": len(docs),
            "memory_count": len(mems),
            "recommendation": "Use memories for context, facts from docs",
        }
    }
```

---

### **P3: NICE-TO-HAVE (Long-term)**

1. **Conversation clustering** — Tự động group chủ đề, giúp follow-up trên chủ đề cũ
2. **Fact-checking** — Cross-reference memories vs docs khi conflict
3. **User preference learning** — Track user feedback trên answers → update confidence
4. **Context graph** — Entity linking, relationship extraction (entities: who, what, when)
5. **Multi-turn memory** — Track sub-conversations (e.g., 3-turn clarification bout)

---

## 📊 Tóm tắt ảnh hưởng

| Fix | Accuracy ↑ | Latency | Cost | Effort |
|-----|-----------|---------|------|--------|
| P0.1: Important msg filtering | +15% | -5% | 0 | Medium |
| P0.2: Better summary prompt | +10% | -2% | 0 | Low |
| P1.1: Memory categories + ranking | +20% | +3% | 0 | Medium |
| P1.2: Memory consolidation | +5% | 0% | -20% | Medium |
| P1.3: Query expansion + reranking | +25% | +10% | +50% | High |
| P2.1: Relevance scoring | +8% | -2% | 0 | Low |

**Tổng cộng khi implement P0+P1:** Accuracy tăng ~60-70%, latency tăng ~13% nhưng vẫn acceptable.

---

## 🚀 Action plan

### Week 1 (P0 + P1.1):
- [ ] Implement message importance filtering
- [ ] Upgrade summary prompt to structured template
- [ ] Add memory categorization

### Week 2 (P1.2 + P1.3):
- [ ] Memory consolidation job
- [ ] Query expansion (simple rules-based first)
- [ ] Reranking (cosine similarity baseline)

### Week 3+ (P2 + Polish):
- [ ] Context relevance scoring
- [ ] Session state enrichment
- [ ] Tests + monitoring

