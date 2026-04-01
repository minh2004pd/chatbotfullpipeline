**✅ ĐÂY LÀ SPEC HOÀN CHỈNH CHO DỰ ÁN CỦA BẠN**

Tôi đã thiết kế theo đúng những gì bạn yêu cầu:  
- **Google ADK** làm core agent  
- **FilesRetrieval** + **ContextFilterPlugin** cho RAG & short-term memory  
- **mem0** cho long-term memory + cá nhân hóa  
- **Qdrant** làm vector DB  
- Input: **text + ảnh** (multimodal)  
- Upload **PDF** để RAG  
- FE: **React** (riêng folder)  
- BE: **Docker** (docker-compose)  

### 1. Mô tả dự án (Project Description)

**Tên dự án đề xuất:** **MemRAG Chatbot** (hoặc **PersonalAI Companion**)

**Mô tả ngắn gọn:**  
MemRAG Chatbot là một chatbot cá nhân hóa đa phương thức (multimodal) được xây dựng trên **Google Agent Development Kit (ADK)**. Người dùng có thể chat bằng **text hoặc upload ảnh**, upload file **PDF** để thực hiện RAG thông minh. Hệ thống có **short-term memory** (qua ADK Session + ContextFilterPlugin) và **long-term memory + personalization** (qua mem0 + Qdrant). Toàn bộ backend chạy trong Docker, frontend dùng React hiện đại, dễ scale và deploy.

**Mục tiêu:**  
- Tạo trải nghiệm chatbot “nhớ lâu”, hiểu sở thích người dùng theo thời gian.  
- Hỗ trợ RAG trên tài liệu PDF cá nhân.  
- Hoàn toàn miễn phí (local/self-hosted) hoặc dễ nâng cấp lên Gemini API.

### 2. Tính năng chính (Features)

| Nhóm tính năng              | Chi tiết cụ thể |
|-----------------------------|-----------------|
| **Input**                   | - Text<br>- Upload ảnh (Gemini multimodal)<br>- Upload PDF (RAG) |
| **RAG Pipeline**            | - Upload PDF → FilesRetrieval Tool (dùng ADK Artifact)<br>- Chunking + embedding (Gemini embedding)<br>- Lưu vào Qdrant collection (per user hoặc global) |
| **Short-term Memory**       | - ADK Session + **ContextFilterPlugin** (giới hạn context, tránh token explosion) |
| **Long-term Memory & Personalization** | - **mem0** (store user preferences, summary cuộc trò chuyện, facts cá nhân)<br>- mem0 kết nối Qdrant |
| **Agent**                   | - Root Agent (Gemini 2.5 Flash / Pro)<br>- Tools: FilesRetrieval, PDFIngestion, QdrantSearch, Mem0Store/Retrieve |
| **UI/UX**                   | - React + Tailwind + shadcn/ui<br>- Chat hiện đại, hỗ trợ drag & drop file/ảnh<br>- Hiển thị citation từ RAG |
| **Khác**                    | - Multi-user (user_id trong mem0 & Qdrant)<br>- Lịch sử chat lưu persistent<br>- Error handling & logging |

### 3. Tech Stack (100% theo yêu cầu của bạn)

| Layer       | Công nghệ                                                                 |
|-------------|---------------------------------------------------------------------------|
| **LLM**     | Gemini 2.5 Flash (Google AI Studio - free tier) hoặc Gemini 2.5 Pro      |
| **Agent Framework** | **Google ADK** (với ContextFilterPlugin)                                 |
| **Memory**  | **mem0** (long-term + personalization)                                    |
| **Vector DB** | **Qdrant** (self-hosted)                                                 |
| **RAG Tools** | FilesRetrieval (custom tool dựa trên ADK Artifact) + Qdrant MCP Tool     |
| **Backend** | Python + FastAPI (hoặc ADK built-in runner) + Docker                     |
| **Frontend** | React 19 + Vite + TypeScript + Tailwind + shadcn/ui + Axios              |
| **Docker**  | docker-compose (Qdrant + Backend + optional Redis cho cache)             |
| **Storage** | Local filesystem (artifacts) + Qdrant                                    |

### 4. Kiến trúc hệ thống (High-level Architecture)

```
Người dùng (React FE)
       ↓ (WebSocket / REST)
Backend API (FastAPI + ADK Agent)
       ├── ADK Root Agent (Gemini)
       │     ├── ContextFilterPlugin (short-term memory)
       │     ├── FilesRetrieval Tool → ADK Artifact → PDF Ingestion
       │     ├── Qdrant MCP Tool (RAG retrieval)
       │     └── mem0 Tools (store/retrieve long-term memory)
       └── mem0 + Qdrant (long-term & personalization)
```

**Flow chính:**
1. User upload PDF → FilesRetrieval Tool → lưu Artifact → ingest → embed → Qdrant.
2. Chat (text/ảnh) → ADK Agent → ContextFilterPlugin → retrieve từ Qdrant + mem0 → generate.
3. Mỗi câu trả lời → mem0 tự động lưu summary/preferences.

### 3. Cấu trúc thư mục toàn dự án (Monorepo)

```
memrag-chatbot/
├── frontend/                      # React frontend
│   ├── src/
│   ├── public/
│   ├── package.json
│   └── vite.config.ts
│
├── backend/                       # Backend (FastAPI + ADK)
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                # Entry point FastAPI app
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── config.py          # Settings (Pydantic)
│   │   │   ├── security.py
│   │   │   └── database.py        # Qdrant client, mem0 client
│   │   ├── schemas/               # Pydantic models (request/response)
│   │   │   ├── __init__.py
│   │   │   ├── chat.py
│   │   │   ├── document.py
│   │   │   ├── memory.py
│   │   │   └── user.py
│   │   ├── services/              # Business logic
│   │   │   ├── __init__.py
│   │   │   ├── chat_service.py
│   │   │   ├── rag_service.py
│   │   │   ├── memory_service.py
│   │   │   └── document_service.py
│   │   ├── repositories/          # Data access layer (Qdrant, mem0)
│   │   │   ├── __init__.py
│   │   │   ├── qdrant_repo.py
│   │   │   └── mem0_repo.py
│   │   ├── agents/                # Google ADK Agents & Tools
│   │   │   ├── __init__.py
│   │   │   ├── root_agent.py
│   │   │   ├── tools/
│   │   │   │   ├── files_retrieval_tool.py
│   │   │   │   ├── pdf_ingestion_tool.py
│   │   │   │   ├── qdrant_search_tool.py
│   │   │   │   └── mem0_tools.py
│   │   │   └── plugins/
│   │   │       └── context_filter_plugin.py
│   │   ├── api/                   # Routers (endpoints)
│   │   │   ├── __init__.py
│   │   │   ├── v1/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── chat.py        # /chat endpoints
│   │   │   │   ├── documents.py   # /documents upload & list
│   │   │   │   └── memory.py      # memory management (optional)
│   │   ├── dependencies.py        # FastAPI dependencies (user_id, db, etc.)
│   │   ├── utils/
│   │   │   ├── file_utils.py
│   │   │   └── gemini_utils.py
│   │   └── exceptions/
│   │       └── handlers.py
│   ├── Dockerfile
│   ├── requirements.txt
│   └── .env.example
│
├── docker-compose.yml
├── .env
├── README.md
└── docs/
    └── architecture.md
```

### 4. Kiến trúc Backend (Layered Architecture)

- **Schemas**: Định nghĩa tất cả request/response models (Pydantic).
- **Repositories**: Truy cập dữ liệu thô (Qdrant, mem0).
- **Services**: Chứa business logic, phối hợp giữa ADK Agent, RAG, memory.
- **Agents**: Chứa root_agent và các custom tools/plugins của Google ADK.
- **API (Routers)**: Chỉ định nghĩa endpoints, gọi service, không chứa logic.
- **Core**: Config, database connection, exceptions.

**Luồng dữ liệu điển hình**:
User request → Router → Dependency → Service → (Repository / ADK Agent) → Response

### 5. Các Endpoints chính (API v1)

Dưới đây là các endpoint quan trọng (định nghĩa trong `app/api/v1/`):

| Method | Endpoint                        | Mô tả |
|--------|----------------------------------|-------|
| POST   | `/api/v1/chat`                  | Chat với text hoặc ảnh (multimodal) |
| POST   | `/api/v1/documents/upload`      | Upload PDF → ingest vào RAG |
| GET    | `/api/v1/documents`             | List tài liệu đã upload |
| POST   | `/api/v1/memory/search`         | Tìm kiếm long-term memory (debug) |
| GET    | `/api/v1/memory/user/{user_id}` | Lấy thông tin personalization |

### 6. docker-compose.yml (gợi ý)

```yaml
services:
  qdrant:
    image: qdrant/qdrant:latest
    container_name: memrag-qdrant
    ports:
      - "6333:6333"
    volumes:
      - qdrant_data:/qdrant/storage
    restart: unless-stopped

  backend:
    build: ./backend
    container_name: memrag-backend
    ports:
      - "8000:8000"
    depends_on:
      - qdrant
    environment:
      - GEMINI_API_KEY=${GEMINI_API_KEY}
      - QDRANT_URL=http://qdrant:6333
      - MEM0_CONFIG_PATH=/app/mem0_config.json
    volumes:
      - ./backend:/app
    restart: unless-stopped

volumes:
  qdrant_data:
```

**Chạy local:**
```bash
docker-compose up -d
cd frontend && npm run dev
```