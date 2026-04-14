# Wiki Knowledge Base — MemRAG

> Hệ thống tự động xây dựng và duy trì structured knowledge base từ documents và meeting transcripts.
> Cập nhật lần cuối: 2026-04-09

---

## 1. Tổng quan

Wiki là **tầng tri thức tổng hợp** (cross-source knowledge base) của MemRAG. Sau mỗi ingestion event (PDF upload hoặc transcript stop), hệ thống tự động:

1. Trích xuất entities, topics, summary từ nội dung
2. Tổng hợp thành Markdown pages có cấu trúc
3. Liên kết các pages với nhau qua wiki links `[[pages/entities/slug.md]]`
4. Rebuild index và graph

Agent (Gemini) **đọc wiki trước tiên** khi trả lời câu hỏi — wiki là nguồn sự thật chính, RAG search là fallback.

---

## 2. Kiến trúc 3 tầng

```
┌─────────────────────────────────────────────────────────────────┐
│  TẦNG 3: HIẾN PHÁP (wiki_schema.md)                             │
│  Quy tắc phân loại, format, liên kết — LLM tuân theo file này   │
│  Thay đổi schema → thay đổi hành vi LLM, không cần restart       │
└─────────────────────────────┬───────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────┐
│  TẦNG 2: TRI THỨC TỔNG HỢP (pages/)                              │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐            │
│  │ entities/    │ │ topics/      │ │ summaries/   │            │
│  │ model,       │ │ research     │ │ 1 page per   │            │
│  │ framework,   │ │ directions,  │ │ source,       │            │
│  │ dataset...   │ │ comparisons  │ │ deep summary  │            │
│  └──────────────┘ └──────────────┘ └──────────────┘            │
│                                                                 │
│  index.md      — Bản đồ tri thức (entry point cho Agent)        │
│  link_index.json — Forward link index (graph edges)             │
│  log.md        — Nhật ký ingestion (append-only, rotate 1000ln) │
└─────────────────────────────┬───────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────┐
│  TẦNG 1: NGUỒN THÔ (raw/) — BẤT BIẾN                            │
│  raw/documents/{doc_id}.txt     — Text trích xuất từ PDF        │
│  raw/transcripts/{meeting_id}.txt — Text từ Soniox STT           │
└─────────────────────────────────────────────────────────────────┘
```

### Cấu trúc thư mục (per user)

```
wiki/{user_id}/
├── raw/
│   ├── documents/
│   └── transcripts/
├── pages/
│   ├── entities/      # Người, công ty, model, framework, dataset...
│   ├── topics/        # Research directions, problems, techniques
│   └── summaries/     # Tóm tắt chuyên sâu từng nguồn
├── index.md
├── link_index.json
├── log.md
└── wiki_schema.md
```

---

## 3. Storage Backend

WikiRepository hỗ trợ 2 backend, tự động chọn qua `STORAGE_BACKEND` env var:

| Backend | Cấu hình | Dùng cho |
|---------|----------|----------|
| **Local filesystem** | `STORAGE_BACKEND=local`, `WIKI_BASE_DIR=./wiki` | Local dev |
| **S3** | `STORAGE_BACKEND=s3` | Production ECS |

API giống hệt nhau — `read_page()`, `write_page()`, `list_all_pages()`, v.v.

---

## 4. Pipeline xử lý (4 Phase)

Trigger: `WikiService.update_wiki_from_document()` (PDF upload) hoặc `update_wiki_from_transcript()` (transcript stop).

Cả hai đều gọi `_process_source()` — fire-and-forget background task.

### Phase 1: MAP — Parallel Extraction

```
Raw text → Split thành chunks (WIKI_CHUNK_SIZE = 16384 chars)
    ↓
Mỗi chunk → _extract_topics() [LLM: gemini-2.0-flash]
    ↓
Parallel: asyncio.gather với semaphore (WIKI_MAX_PARALLEL_EXTRACTIONS = 5)
    ↓
Kết quả: list[entities, topics, summary] per chunk
```

**LLM prompt** trả về JSON:
```json
{
  "entities": [{"slug": "lora", "title": "LoRA", "type": "method"}],
  "topics": [{"slug": "peft", "title": "Parameter-Efficient Fine-Tuning"}],
  "summary": {"slug": "paper-x", "title": "Tóm tắt: Paper X"}
}
```

**Fallback**: Nếu LLM error → đảm bảo luôn có ít nhất 1 entity + 1 topic + 1 summary.

### Phase 2: REDUCE — Merge & Deduplicate

```
Tất cả chunk results → _reduce_extractions()
    ↓
- Merge entities/trùng slug (cùng category + cùng source)
- Merge topics/trùng slug
- Giới hạn: WIKI_MAX_ENTITIES_PER_SOURCE (20), WIKI_MAX_TOPICS_PER_SOURCE (5)
    ↓
_build_slug_to_chunks() → map mỗi slug → merged text từ tất cả chunks liên quan
    ↓
Giới hạn merged text: WIKI_SYNTHESIS_MAX_TEXT_PER_PAGE (32768 chars)
```

### Phase 3: PARALLEL SYNTHESIS

```
Mỗi page cần synthesize → _synthesize_page() [LLM: gemini-2.0-flash]
    ↓
Parallel: asyncio.gather với semaphore (WIKI_MAX_PARALLEL_SYNTHESIS = 5)
    ↓
LLM nhận:
  - existing_content (nếu page đã tồn tại)
  - new_text (merged từ chunks)
  - topic_title, topic_type
  - source_name, source_id
  - wiki_schema.md (dynamic injection)
    ↓
Ghi vào wiki/{user_id}/pages/{category}/{slug}.md
    ↓
Song song:
  - _update_link_index() — cập nhật forward links
  - _create_ghost_stubs() — tạo stub pages cho [[links]] chưa tồn tại
```

**Ghost stubs**: Khi page A link đến `[[pages/entities/foo.md]]` nhưng `foo.md` chưa có → tạo stub page với `version: 0`, `stub: true`, `sources: [source_id]`.

### Phase 4: FINALIZATION

```
_update_related_pages() — scan pages khác có cùng source_id, cập nhật nếu liên quan
    ↓
_rebuild_index() — rebuild index.md từ scratch (rule-based, không LLM)
    ↓
_rebuild_link_index() — rebuild link_index.json từ scratch (scan [[links]] trong content)
    ↓
append_log() — ghi entry vào log.md
```

---

## 5. Format mỗi trang Wiki

```yaml
---
title: Low-Rank Adaptation (LoRA)
tags: [fine-tuning, peft, lora]
type: method
sources: [doc_abc123, meet_xyz789]
last_updated: 2026-04-09
version: 3
---

# Low-Rank Adaptation (LoRA)

## Tổng quan
LoRA là phương pháp parameter-efficient fine-tuning...

## Phương pháp
...

## Kết quả
...

## Liên quan
- [[pages/entities/qlora.md]] — QLoRA: quantized version
- [[pages/topics/efficientml.md]] — Efficient ML overview
```

### Frontmatter fields

| Field | Mô tả |
|-------|-------|
| `title` | Tên đầy đủ |
| `tags` | List tags cho categorization |
| `type` | `model`, `framework`, `dataset`, `benchmark`, `researcher`, `lab`, `tool`, `method`, `concept`, `topic`, `summary` |
| `sources` | List source IDs (document_id hoặc meeting_id) |
| `last_updated` | YYYY-MM-DD |
| `version` | Số lần page được cập nhật (0 = stub) |

---

## 6. Quy tắc phân loại

### entities/
Thực thể AI/ML/research **có thể định danh rõ ràng**:

| Type | Ví dụ |
|------|-------|
| **model** | GPT-4o, Claude, Gemini, LLaMA, ViT, SAM, Whisper |
| **framework** | PyTorch, JAX, LangChain, Google ADK, vLLM |
| **dataset** | GLUE, SQuAD, ImageNet, MMLU, GSM8K, SWE-bench |
| **benchmark** | HELM, BIG-Bench, LMSYS Arena, AgentBench |
| **researcher** | Yann LeCun, Geoffrey Hinton, Andrej Karpathy |
| **lab** | OpenAI, Anthropic, Google DeepMind, Meta AI |
| **tool** | Qdrant, FAISS, Ray, CUDA, W&B |
| **method** | ReAct, LoRA, QLoRA, DPO, GRPO, GraphRAG, Tree of Thoughts |
| **concept** | Transformer, Attention, Diffusion, MoE, Agentic AI, RAG |

### topics/
**Chủ đề nghiên cứu** cấp độ cao — vấn đề/hướng đang được giải quyết:
- "Multi-agent Orchestration", "LLM Hallucination", "AI Safety Alignment"
- "Zero-shot Detection", "3D Scene Understanding", "Video Generation"
- "Model Compression", "Inference Optimization", "PEFT"

### summaries/
Tóm tắt chuyên sâu **1 page per source**:
- TL;DR → Đóng góp chính → Phương pháp → Kết quả → Hạn chế → Future work

---

## 7. Liên kết & Trích dẫn

### Wiki links
```
[[pages/entities/lora.md]]    # entity page
[[pages/topics/peft.md]]      # topic page
[[pages/summaries/paper-x.md]] # summary page
```

**Quy tắc slug:**
- Chỉ `[a-z0-9]`, không gạch ngang: "U-Net" → `unet`, "LoRA" → `lora`
- Luôn kèm đầy đủ path prefix + `.md` — KHÔNG dùng `[[slug]]` thuần

### Trích dẫn nguồn
```
[Paper: LoRA: Low-Rank Adaptation of Large Language Models]  # dấu ngoặc đơn
```

### Mâu thuẫn giữa nguồn
```
~~Thông tin cũ [nguồn cũ]~~ → thông tin mới [nguồn mới]
```

---

## 8. Index & Link Index

### index.md
Auto-generated sau mỗi ingestion. Format:

```markdown
# Wiki Index

## Entities
- [[pages/entities/lora.md]] — **Low-Rank Adaptation** — PEFT method cho LLM fine-tuning
- [[pages/entities/pytorch.md]] — **PyTorch** — Deep learning framework từ Meta

## Topics
- [[pages/topics/peft.md]] — **Parameter-Efficient Fine-Tuning** — Các phương pháp fine-tuning tiết kiệm

## Summaries
- [[pages/summaries/paper-lora.md]] — **Tóm tắt: LoRA Paper** — Tóm tắt paper LoRA gốc
```

### link_index.json
Forward link index — JSON map `rel_path → [list of rel_paths linked from this page]`:

```json
{
  "pages/entities/lora.md": [
    "pages/entities/qlora.md",
    "pages/topics/efficientml.md"
  ],
  "pages/topics/peft.md": [
    "pages/entities/lora.md",
    "pages/entities/qlora.md"
  ]
}
```

Dùng để:
- Tính **backlink_count** cho mỗi node trong graph
- Tạo **edges** cho React Flow visualization

---

## 9. Agent Flow (ADK Tools)

Agent đọc wiki theo flow:

```
1. read_wiki_index()
   → Nhận danh sách tất cả wiki pages (~1-2k tokens)
   → Chọn pages liên quan đến query

2. read_wiki_page(rel_path)
   → Đọc nội dung page cụ thể
   → Nhận: content, backlinks, is_stub flag

3. Nếu is_stub=True hoặc nội dung chưa đủ:
   → Fallback search_documents / search_meeting_transcripts

4. Nếu page có [[pages/.../*.md]] links liên quan:
   → Đọc thêm bằng read_wiki_page
```

### Agent strategy

| Câu hỏi | Flow |
|---------|------|
| "LoRA là gì?" | `read_wiki_index` → tìm "lora" → `read_wiki_page("pages/entities/lora.md")` |
| "So sánh LoRA vs QLoRA" | `read_wiki_index` → đọc cả 2 pages → tổng hợp |
| "Tóm tắt paper X" | `read_wiki_index` → tìm summary page → `read_wiki_page("pages/summaries/...")` |
| Wiki không có thông tin | Fallback → `search_documents` / `search_meeting_transcripts` |

---

## 10. Frontend — Knowledge Graph

### API

| Method | Path | Mô tả |
|--------|------|-------|
| GET | `/api/v1/wiki/graph` | Lấy nodes + edges cho React Flow |
| GET | `/api/v1/wiki/pages/{category}/{slug}` | Đọc nội dung một wiki page |

### Graph endpoint params

| Param | Type | Mô tả |
|-------|------|-------|
| `show_stubs` | bool | Hiện stub pages (version=0) |
| `show_summaries` | bool | Hiện summary pages |
| `source_ids` | list[str] | Lọc theo source IDs ([] = tất cả) |

### Response

```json
{
  "nodes": [
    {
      "key": "entities/lora",
      "id": "lora",
      "title": "Low-Rank Adaptation",
      "type": "method",
      "category": "entities",
      "source_count": 2,
      "backlink_count": 5,
      "is_stub": false
    }
  ],
  "edges": [
    {
      "id": "entities_lora__topics_peft",
      "source": "entities/lora",
      "target": "topics/peft"
    }
  ]
}
```

### Components

| Component | Mô tả |
|-----------|-------|
| `WikiGraphPanel.tsx` | React Flow canvas với toolbar, filters, mini-map |
| `WikiPageDrawer.tsx` | Side drawer hiển thị nội dung page (Markdown + Math + wiki links) |
| `WikiNodeCard.tsx` | Custom React Flow node card với màu theo type |
| `useWikiGraph.ts` | React Query hooks cho graph + page data |

### Features

- **Dagre auto-layout** — nodes tự sắp xếp theo hierarchy
- **Source filtering** — lọc graph theo documents đã upload
- **Wiki link rendering** — `[[pages/...]]` links trong page content thành clickable buttons
- **Math rendering** — KaTeX cho `$$...$$` và `$...$`
- **Active node highlighting** — nodes agent đọc được highlight trong graph
- **Backlink count** — hiển thị số trang khác đang link đến

---

## 11. Deletion Flow

Khi user xóa document hoặc meeting:

```
remove_source_from_wiki(user_id, source_id)
    ↓
1. Scan tất cả pages → tìm pages có source_id trong frontmatter
    ↓
2. Với mỗi page tìm thấy:
   ├─ Nếu chỉ có 1 source = source này → XÓA page
   └─ Nếu có nhiều sources → LLM re-synthesize (bỏ source bị xóa)
    ↓
3. Xóa raw file: raw/{category}/{source_id}.txt
    ↓
4. Rebuild index + link index
    ↓
5. Ghi log entry
```

---

## 12. Wiki Indexing Status

Frontend theo dõi tiến trình wiki sau khi upload PDF:

| Status | Mô tả | UI |
|--------|-------|----|
| `processing` | Đang extract + synthesize | Spinner "Wiki đang xây dựng..." |
| `done` | Hoàn thành | Icon check "Wiki index" |
| `error` | Lỗi | Icon lỗi "Wiki — lỗi" |
| `disabled` | `WIKI_ENABLED=false` | Không hiển thị |

Polling: bắt đầu sau 1.5s, interval 2s, timeout 120s.

---

## 13. Config (Environment Variables)

| Variable | Default | Mô tả |
|----------|---------|-------|
| `WIKI_ENABLED` | `true` | Bật/tắt wiki auto-synthesis |
| `WIKI_BASE_DIR` | `./wiki` | Thư mục local cho wiki (khi STORAGE_BACKEND=local) |
| `WIKI_CHUNK_SIZE` | `16384` | Kích thước chunk cho extraction |
| `WIKI_MAX_ENTITIES_PER_SOURCE` | `20` | Số entities tối đa extract per source |
| `WIKI_MAX_TOPICS_PER_SOURCE` | `5` | Số topics tối đa extract per source |
| `WIKI_MAX_RELATED_PAGES_PER_SOURCE` | `10` | Số pages liên quan tối đa update |
| `WIKI_MAX_PARALLEL_EXTRACTIONS` | `5` | Concurrent _extract_topics calls |
| `WIKI_MAX_PARALLEL_SYNTHESIS` | `5` | Concurrent _synthesize_page calls |
| `WIKI_SYNTHESIS_MAX_TEXT_PER_PAGE` | `32768` | Max merged text per page |

---

## 14. Files liên quan

```
backend/app/
  agents/tools/
    wiki_tools.py              read_wiki_index, read_wiki_page, list_wiki_pages
  api/v1/
    wiki.py                    REST API endpoints
  core/
    config.py                  Wiki config fields
  repositories/
    wiki_repo.py               WikiRepository (local + S3)
  services/
    wiki_service.py            WikiService — 4-phase pipeline
  schemas/
    wiki.py                    Pydantic models cho API response
  utils/
    wiki_utils.py              parse_frontmatter, slug extraction, link extraction

frontend/src/
  api/
    wiki.ts                    wikiApi client
  components/wiki/
    WikiGraphPanel.tsx         React Flow knowledge graph
    WikiPageDrawer.tsx         Side drawer cho page content
    WikiNodeCard.tsx           Custom React Flow node
  hooks/
    useWikiGraph.ts            React Query hooks
  utils/
    wikiGraphLayout.ts         Dagre layout algorithm
    wikiNodeColors.ts          Color mapping per node type
  types/
    index.ts                   WikiGraphNode, WikiGraphEdge, WikiGraphData, WikiPage
```

---

## 15. LLM Models dùng trong Wiki

| Model | Vai trò | Config key |
|-------|---------|------------|
| `gemini-2.0-flash` | _extract_topics (MAP phase) | `llm.summary_model` |
| `gemini-2.0-flash` | _synthesize_page (SYNTHESIS phase) | `llm.summary_model` |

> Wiki dùng `summary_model` (gemini-2.0-flash) thay vì `gemini-2.5-flash` của Root Agent — chi phí thấp hơn, tốc độ nhanh hơn cho batch processing.

---

## 16. Wiki Schema (Hiến pháp)

`wiki_schema.md` là **Single Source of Truth** về quy tắc wiki của mỗi user. Được **dynamic injection** vào prompt khi LLM synthesize pages.

**Lợi ích:**
- Thay đổi schema → thay đổi ngay hành vi LLM, không cần restart backend
- Mỗi user có schema riêng (per-user wiki rules)
- Agent có thể đọc schema qua `read_wiki_page("wiki_schema.md")`

**Nội dung schema:**
- Quy tắc phân loại entities/topics/summaries
- Format frontmatter
- Quy ước liên kết & trích dẫn
- Nguyên tắc cập nhật
