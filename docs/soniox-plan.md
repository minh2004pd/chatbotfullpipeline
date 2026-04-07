# 🧠 Kế hoạch tích hợp Soniox — Realtime Transcription & RAG Pipeline

> Ngày tạo: 2026-04-06  
> Dự án: MemRAG Chatbot (proj2)  
> Mục tiêu: Thêm tính năng realtime transcription + translation + diarization từ nhiều nguồn audio → lưu transcript vào RAG pipeline

---

## 1. Mapping Yêu cầu ↔ Soniox

| Yêu cầu | Soniox hỗ trợ? | Chi tiết |
|---------|-----------------|---------|
| 🎤 Input đa nguồn (Mic / System / Both) | ✅ | Nhận audio stream qua WebSocket, không quan tâm nguồn |
| ⚡ Realtime transcription | ✅ | Token-level streaming, partial transcript ngay lập tức |
| 🌐 Realtime translation | ✅ | Mid-sentence translation, không cần đợi hết câu |
| 🌍 Multi-language + mixed lang | ✅ | 60+ ngôn ngữ, switch giữa câu vẫn OK |
| 👥 Speaker diarization | ✅ | Diarization realtime (speaker_1, speaker_2...) |
| 💾 Lưu transcript cho RAG | ✅ | Stream realtime + lưu final transcript + audio |

---

## 2. Kiến trúc tổng thể (Pipeline)

```
[Audio Sources]
   ├── Mic         → getUserMedia({ audio: true })
   ├── System      → getDisplayMedia({ audio: true, video: true })
   └── Both        → AudioContext merge (mic + system → mixed stream)

        ↓  raw PCM stream (16kHz, mono)

[Audio Processor — Frontend]
   - Resample → 16kHz
   - Chunk → 4096 samples/chunk (~256ms)
   - Convert → ArrayBuffer / PCM16

        ↓  WebSocket (binary audio chunks)

[Soniox Realtime API]
   ├── partial transcript (token-level)
   ├── final transcript (sentence-level)
   ├── translation
   └── speaker diarization

        ↓  JSON events

[Backend (FastAPI) — ECS Task trên EC2]
   ├── Live UI ← SSE stream qua CloudFront → Frontend
   ├── DynamoDB ← lưu raw transcript (single-table design)
   ├── S3 ← lưu audio recordings (prefix audio/)
   └── RAG Pipeline:
         Chunk → Embed (Gemini) → Qdrant (sidecar)

[RAG Query]
   User hỏi → embed → Qdrant search → context → ADK Agent → response
```

### Mapping vào AWS Infrastructure hiện có

| Thành phần Soniox | AWS Service | Ghi chú |
|---|---|---|
| Backend logic (SonioxService) | **ECS Task — backend container** | Thêm service/routes mới vào FastAPI, cùng container hiện tại |
| Secrets (`SONIOX_API_KEY`) | **SSM Parameter Store** | Thêm `/memrag/soniox-api-key` SecureString, inject qua ECS task def |
| Lưu audio recordings | **S3** | Thêm prefix `audio/` trong bucket hiện có (cùng `uploads/`) |
| Lưu transcript metadata | **DynamoDB** | Thêm table `memrag-meetings` (single-table design, PAY_PER_REQUEST) |
| Transcript embeddings (RAG) | **Qdrant** (sidecar) | Thêm collection `meetings` bên cạnh RAG + mem0 hiện có |
| Streaming result về FE | **CloudFront** `/api/*` | SSE — tận dụng `compress=false` đã config cho chat streaming |
| Logs | **CloudWatch** | Tự động — cùng log group `/ecs/memrag` |
| CI/CD | **GitHub Actions → ECR → ECS** | Cùng workflow `ci-cd.yml` + `deploy-frontend.yml` |

> ⚠️ CloudFront **không hỗ trợ WebSocket** → dùng **SSE** (đã proven với chat streaming hiện tại).  
> **Không cần thêm AWS service mới** — chỉ thêm SSM param, S3 prefix, DynamoDB table, Qdrant collection.  
> **Không cần thay đổi docker-compose** — Soniox là external API (giống Gemini), gọi qua internet.

---

## 3. Xử lý 3 nguồn Audio (Frontend)

### 3.1 Mic only

```javascript
const micStream = await navigator.mediaDevices.getUserMedia({ audio: true });
```

### 3.2 System Audio (Tab / YouTube / Meet / Zoom)

```javascript
const displayStream = await navigator.mediaDevices.getDisplayMedia({
  audio: true,
  video: true  // bắt buộc phải có video mới capture được audio tab
});
// Lấy audio track
const systemAudioTrack = displayStream.getAudioTracks()[0];
```

> ⚠️ **Giới hạn**: Chrome chỉ cho capture audio của tab, không capture system-wide audio. Với Zoom/Meet desktop app → cần dùng loopback device (VB-Cable, BlackHole) hoặc Chrome Extension.

### 3.3 Mix cả 2 (Mic + System)

```javascript
const audioContext = new AudioContext();

const micSource    = audioContext.createMediaStreamSource(micStream);
const systemSource = audioContext.createMediaStreamSource(systemAudioStream);

const destination = audioContext.createMediaStreamDestination();

micSource.connect(destination);
systemSource.connect(destination);

const mixedStream = destination.stream;
// → mixedStream là stream hợp nhất để gửi lên Soniox
```

---

## 4. Audio Processor (Frontend → Soniox)

```javascript
// Resample về 16kHz + convert sang PCM16
const scriptProcessor = audioContext.createScriptProcessor(4096, 1, 1);

scriptProcessor.onaudioprocess = (event) => {
  const float32 = event.inputBuffer.getChannelData(0);
  const pcm16   = float32ToPCM16(float32);  // Int16Array
  websocket.send(pcm16.buffer);
};

function float32ToPCM16(float32Array) {
  const int16 = new Int16Array(float32Array.length);
  for (let i = 0; i < float32Array.length; i++) {
    const clamped = Math.max(-1, Math.min(1, float32Array[i]));
    int16[i] = clamped < 0 ? clamped * 0x8000 : clamped * 0x7FFF;
  }
  return int16;
}
```

> 💡 Với AudioWorklet (API mới hơn, không deprecated như ScriptProcessor) thì hiệu quả hơn — plan dùng AudioWorklet cho production.

---

## 5. Streaming Flow: Browser ↔ Backend ↔ Soniox

### Tại sao Backend làm proxy (không gọi Soniox trực tiếp từ browser)?

- Giấu `SONIOX_API_KEY` (lưu SSM, chỉ backend đọc được)
- Backend lưu transcript vào DynamoDB + Qdrant ngay khi nhận
- Dùng chung CloudFront domain, SSE cho live UI (không cần CORS)

### Flow

```
[Browser]                        [EC2 Backend]              [Soniox Cloud]
AudioWorklet (16kHz PCM16)       FastAPI
   │                                │
   ├── POST /api/v1/transcription  │
   │   /audio (binary chunks) ────►│
   │                                ├── open WS → Soniox API
   │                                │── forward chunks ────────►│
   │                                │                           │
   │◄── SSE /api/v1/transcription  │◄── JSON events ──────────│
   │    /stream (partial/final) ───│
   │                                │
   │                                ├── lưu final → DynamoDB
   │                                ├── embed → Qdrant
   │                                └── save audio → S3
```

### Soniox config

```json
{
  "token": "${SONIOX_API_KEY}",
  "model": "stt-rt-preview",
  "language_hints": ["vi", "en"],
  "enable_translation": true,
  "translation_target_language": "vi",
  "enable_speaker_diarization": true,
  "num_speakers": 2
}
```

### Response events

```json
// Partial (hiển thị live trên UI qua SSE)
{ "type": "partial", "tokens": [{ "text": "hello", "speaker": 1 }] }

// Final (lưu vào DynamoDB)
{
  "type": "final",
  "tokens": [{ "text": "hello everyone", "speaker": 1 }],
  "translation": "xin chào mọi người"
}
```

---

## 6. Data Structure & Storage

### 6.1 Transcript Record (DynamoDB — single-table design)

```json
{
  "PK": "MEETING#meet_abc123",
  "SK": "UTTERANCE#1712400000#001",
  "speaker": "speaker_1",
  "language": "en",
  "text": "hello everyone let's start the meeting",
  "translated_text": "xin chào mọi người hãy bắt đầu cuộc họp",
  "confidence": 0.97,
  "start_ms": 1200,
  "end_ms": 3400,
  "user_id": "user_xxx",
  "created_at": "2026-04-06T15:00:00Z"
}
```

### 6.2 Meeting Metadata (DynamoDB — cùng table)

```json
{
  "PK": "USER#user_xxx",
  "SK": "MEETING#meet_abc123",
  "title": "Team standup 2026-04-06",
  "duration_ms": 1800000,
  "speakers": ["speaker_1", "speaker_2"],
  "languages": ["en", "vi"],
  "audio_s3_key": "audio/meet_abc123.webm",
  "status": "completed"
}
```

### 6.3 Storage mapping

| Loại dữ liệu | Service | Chi tiết |
|-------------|---------|----------|
| Raw transcript (per utterance) | **DynamoDB** | Table `memrag-meetings`, PAY_PER_REQUEST |
| Meeting metadata | **DynamoDB** | Cùng table, GSI `UserIndex` cho query by user |
| Chunked transcript embeddings | **Qdrant** | Collection `meetings`, chunk 30s–2min |
| Audio file | **S3** | Prefix `audio/`, optional recording |
| Session chat history | **DynamoDB** | Table hiện có `memrag-sessions` |

---

## 7. RAG Pipeline sau khi có Transcript

```
Transcript (final) từ DynamoDB
   ↓
Chunking (time window 30s–2min hoặc semantic boundary)
   ↓
Embedding (Gemini text-embedding-004 — đã dùng cho PDF RAG)
   ↓
Lưu vào Qdrant sidecar (collection: "meetings", localhost:6333)
   ↓
User query → embed → Qdrant search (top-k) → context
   ↓
ADK Root Agent → generate answer (Gemini 2.5 Flash)
```

---

## 8. Terraform Changes

### 8.1 SSM — thêm secret

```hcl
resource "aws_ssm_parameter" "soniox_api_key" {
  name  = "/memrag/soniox-api-key"
  type  = "SecureString"
  value = var.soniox_api_key
}
```

### 8.2 ECS Task Definition — thêm env var

```hcl
# ecs.tf — backend container secrets
secrets = [
  { name = "GEMINI_API_KEY",   valueFrom = aws_ssm_parameter.gemini_api_key.arn },
  { name = "MEM0_API_KEY",     valueFrom = aws_ssm_parameter.mem0_api_key.arn },
  { name = "SONIOX_API_KEY",   valueFrom = aws_ssm_parameter.soniox_api_key.arn },  # NEW
]
```

### 8.3 DynamoDB — thêm table

```hcl
resource "aws_dynamodb_table" "meetings" {
  name         = "memrag-meetings"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "PK"
  range_key    = "SK"

  attribute { name = "PK"      type = "S" }
  attribute { name = "SK"      type = "S" }
  attribute { name = "user_id" type = "S" }

  global_secondary_index {
    name            = "UserIndex"
    hash_key        = "user_id"
    range_key       = "SK"
    projection_type = "ALL"
  }
}
```

### 8.4 IAM — thêm quyền

```hcl
# ecs-task-role — thêm DynamoDB meetings
{
  Effect   = "Allow"
  Action   = ["dynamodb:PutItem", "dynamodb:Query", "dynamodb:GetItem", "dynamodb:BatchWriteItem"]
  Resource = [aws_dynamodb_table.meetings.arn, "${aws_dynamodb_table.meetings.arn}/index/*"]
}
```

---

## 9. Kế hoạch thực thi (Implementation Roadmap)

### Phase 1 — Infrastructure & Config

- [ ] Thêm `SONIOX_API_KEY` vào SSM Parameter Store
- [ ] Cập nhật ECS task def (thêm secret)
- [ ] Thêm DynamoDB table `memrag-meetings` (Terraform)
- [ ] Cập nhật IAM role
- [ ] `terraform apply`

### Phase 2 — Backend Soniox Service

- [ ] `backend/app/services/soniox_service.py` — WS client tới Soniox API
- [ ] `backend/app/schemas/transcription.py` — Pydantic models
- [ ] `backend/app/repositories/meeting_repo.py` — DynamoDB CRUD
- [ ] `backend/app/api/v1/transcription.py`:
  - `POST /api/v1/transcription/start` — bắt đầu session
  - `POST /api/v1/transcription/audio` — gửi audio chunk
  - `GET /api/v1/transcription/stream` — SSE partial/final
  - `GET /api/v1/meetings` — list meetings
  - `GET /api/v1/meetings/{id}/transcript` — full transcript

### Phase 3 — RAG Pipeline

- [ ] `backend/app/services/transcript_rag_service.py`
  - chunk theo time window
  - embed với Gemini
  - upsert vào Qdrant collection `meetings`
- [ ] ADK Tool `MeetingSearchTool` — search transcript từ Qdrant
- [ ] Thêm tool vào Root Agent

### Phase 4 — Frontend Audio Capture

- [ ] `AudioCaptureService.ts` — quản lý mic / system / mix
- [ ] `AudioProcessor.worklet.ts` — resample 16kHz, PCM16
- [ ] `TranscriptionAPI.ts` — gọi backend + listen SSE
- [ ] `TranscriptionPanel.tsx` — live subtitle + translation
- [ ] `MeetingControls.tsx` — chọn nguồn, Start/Stop

### Phase 5 — Polish & Deploy

- [ ] Speaker label UI (màu khác nhau)
- [ ] Meeting history page
- [ ] Chat với meeting transcript (RAG)
- [ ] Error handling + retry Soniox WS disconnect

---

## 10. Config & Environment

### SSM Parameters (thêm mới)

| Parameter | Type | Giá trị |
|-----------|------|---------|
| `/memrag/soniox-api-key` | SecureString | API key từ console.soniox.com |

### Backend `.env` (local dev)

```bash
# Existing
GEMINI_API_KEY=xxx
QDRANT_URL=http://qdrant:6333
DYNAMODB_ENDPOINT_URL=http://dynamodb-local:8000

# NEW — Soniox
SONIOX_API_KEY=xxx
SONIOX_MODEL=stt-rt-preview
SONIOX_TARGET_LANG=vi
```

> **docker-compose.yml**: Không cần thay đổi — Soniox là external API (giống Gemini), gọi qua internet. DynamoDB Local + Qdrant đã có sẵn.

---

## 11. Cấu trúc file mới

```
proj2/
├── infrastructure/
│   ├── ecs.tf              [MODIFY] thêm SONIOX_API_KEY secret
│   ├── dynamodb.tf         [MODIFY] thêm table memrag-meetings
│   ├── iam.tf              [MODIFY] thêm quyền DynamoDB meetings
│   └── variables.tf        [MODIFY] thêm var.soniox_api_key
│
├── backend/app/
│   ├── services/
│   │   ├── soniox_service.py           [NEW]
│   │   └── transcript_rag_service.py   [NEW]
│   ├── repositories/
│   │   └── meeting_repo.py             [NEW]
│   ├── schemas/
│   │   └── transcription.py            [NEW]
│   ├── agents/tools/
│   │   └── meeting_search_tool.py      [NEW]
│   └── api/v1/
│       └── transcription.py            [NEW]
│
├── frontend/src/
│   ├── services/
│   │   ├── AudioCaptureService.ts      [NEW]
│   │   ├── AudioProcessor.worklet.ts   [NEW]
│   │   └── TranscriptionAPI.ts         [NEW]
│   └── components/
│       ├── TranscriptionPanel.tsx      [NEW]
│       └── MeetingControls.tsx         [NEW]
│
└── docs/
    └── soniox-plan.md                  ← file này
```

---

## 12. Rủi ro & Giải pháp

| Rủi ro | Giải pháp |
|--------|-----------|
| CloudFront không hỗ trợ WebSocket | Dùng SSE (đã proven với chat streaming) |
| EC2 t3.small RAM không đủ | Soniox xử lý trên cloud, backend chỉ proxy → minimal RAM |
| Chrome không capture system audio | `getDisplayMedia` + hướng dẫn share tab |
| ScriptProcessor deprecated | Dùng AudioWorklet ngay từ đầu |
| Soniox WS bị ngắt khi mạng yếu | Auto-reconnect + buffer audio chunks |
| Qdrant duplicate khi re-ingest | Dùng `meeting_id + chunk_index` làm point ID |
| DynamoDB cost tăng | PAY_PER_REQUEST + TTL cho meetings cũ |
