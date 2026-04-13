"""WikiRepository — đọc/ghi Markdown pages cho LLM Wiki Layer.

Hỗ trợ 2 backends:
  - Local filesystem (dev): files tại {base_dir}/{user_id}/...
  - S3 (production ECS): objects tại s3://{bucket}/wiki/{user_id}/...

Cấu trúc thư mục:
  wiki/{user_id}/
  ├── raw/documents/     # text trích xuất từ PDF (bất biến)
  ├── raw/transcripts/   # text từ Soniox transcript (bất biến)
  ├── pages/entities/    # người, công ty, công cụ
  ├── pages/topics/      # khái niệm, dự án, chủ đề
  ├── pages/summaries/   # tóm tắt từng nguồn riêng lẻ
  ├── index.md           # bản đồ tri thức (content map)
  ├── log.md             # nhật ký ingestion
  └── wiki_schema.md     # schema/hiến pháp của wiki (tầng 3)
"""

import json
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

_LOG_MAX_LINES = 1000  # rotate log.md khi quá số dòng này


class WikiRepository:
    """File I/O cho wiki. Tự động chọn backend dựa trên s3_client."""

    def __init__(
        self,
        base_dir: str = "./wiki",
        s3_client=None,
        s3_bucket: str = "",
        s3_prefix: str = "wiki",
    ) -> None:
        self._base_dir = base_dir
        self._s3 = s3_client
        self._s3_bucket = s3_bucket
        self._s3_prefix = s3_prefix.rstrip("/")

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _local_path(self, user_id: str, rel_path: str) -> Path:
        return Path(self._base_dir) / user_id / rel_path

    def _s3_key(self, user_id: str, rel_path: str) -> str:
        return f"{self._s3_prefix}/{user_id}/{rel_path}"

    def _read(self, user_id: str, rel_path: str) -> str | None:
        if self._s3:
            try:
                resp = self._s3.get_object(
                    Bucket=self._s3_bucket,
                    Key=self._s3_key(user_id, rel_path),
                )
                return resp["Body"].read().decode("utf-8")
            except self._s3.exceptions.NoSuchKey:
                return None
            except Exception as e:
                # ClientError code "NoSuchKey" for older botocore
                if "NoSuchKey" in str(e) or "404" in str(e):
                    return None
                raise
        else:
            p = self._local_path(user_id, rel_path)
            if not p.exists():
                return None
            return p.read_text(encoding="utf-8")

    def _write(self, user_id: str, rel_path: str, content: str) -> None:
        if self._s3:
            self._s3.put_object(
                Bucket=self._s3_bucket,
                Key=self._s3_key(user_id, rel_path),
                Body=content.encode("utf-8"),
                ContentType="text/markdown; charset=utf-8",
            )
        else:
            p = self._local_path(user_id, rel_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")

    def _list_prefix(self, user_id: str, prefix: str) -> list[str]:
        """Trả về list filenames (không có prefix) trong thư mục."""
        if self._s3:
            full_prefix = self._s3_key(user_id, prefix).rstrip("/") + "/"
            resp = self._s3.list_objects_v2(Bucket=self._s3_bucket, Prefix=full_prefix)
            keys = [obj["Key"] for obj in resp.get("Contents", [])]
            # Strip prefix, chỉ giữ filename
            return [
                k[len(full_prefix) :]
                for k in keys
                if k != full_prefix and "/" not in k[len(full_prefix) :]
            ]
        else:
            d = self._local_path(user_id, prefix)
            if not d.exists() or not d.is_dir():
                return []
            return [f.name for f in d.iterdir() if f.is_file() and f.suffix == ".md"]

    def _delete(self, user_id: str, rel_path: str) -> None:
        if self._s3:
            self._s3.delete_object(
                Bucket=self._s3_bucket,
                Key=self._s3_key(user_id, rel_path),
            )
        else:
            p = self._local_path(user_id, rel_path)
            if p.exists():
                p.unlink()

    # ── Wiki pages ────────────────────────────────────────────────────────────

    def read_page(self, *, user_id: str, rel_path: str) -> str | None:
        """Đọc nội dung trang Wiki. rel_path: "pages/topics/q1-planning.md"."""
        return self._read(user_id, rel_path)

    def write_page(self, *, user_id: str, rel_path: str, content: str) -> None:
        """Ghi nội dung trang Wiki (overwrite)."""
        self._write(user_id, rel_path, content)
        logger.debug("wiki_page_written", user_id=user_id, path=rel_path)

    def delete_page(self, *, user_id: str, rel_path: str) -> None:
        """Xóa trang Wiki."""
        self._delete(user_id, rel_path)
        logger.debug("wiki_page_deleted", user_id=user_id, path=rel_path)

    def list_pages_in_category(self, *, user_id: str, category: str) -> list[str]:
        """
        Liệt kê filenames trong category.
        category: "entities" | "topics" | "summaries"
        Returns: list of filenames (e.g., ["q1-planning.md", "memrag.md"])
        """
        return self._list_prefix(user_id, f"pages/{category}")

    def list_all_pages(self, *, user_id: str) -> list[dict]:
        """
        Liệt kê tất cả pages kèm category.
        Returns: [{"rel_path": "pages/topics/q1-planning.md", "category": "topics", "filename": "q1-planning.md"}]
        """
        result = []
        for category in ("entities", "topics", "summaries"):
            for filename in self.list_pages_in_category(user_id=user_id, category=category):
                result.append(
                    {
                        "rel_path": f"pages/{category}/{filename}",
                        "category": category,
                        "filename": filename,
                    }
                )
        return result

    # ── Index & Log ───────────────────────────────────────────────────────────

    def read_schema(self, *, user_id: str) -> str:
        """Đọc wiki_schema.md — nguồn sự thật về quy tắc wiki của user này.
        Trả về "" nếu chưa khởi tạo (first ingest sẽ tạo file này)."""
        return self._read(user_id, "wiki_schema.md") or ""

    def read_index(self, *, user_id: str) -> str:
        """Đọc index.md — trả về "" nếu chưa có."""
        return self._read(user_id, "index.md") or ""

    def write_index(self, *, user_id: str, content: str) -> None:
        """Ghi index.md."""
        self._write(user_id, "index.md", content)

    def append_log(self, *, user_id: str, entry: str) -> None:
        """Append một dòng vào log.md. Tự động rotate khi quá _LOG_MAX_LINES."""
        existing = self._read(user_id, "log.md") or ""
        lines = existing.splitlines()
        lines.append(entry)
        # Rotate: giữ _LOG_MAX_LINES dòng gần nhất
        if len(lines) > _LOG_MAX_LINES:
            lines = lines[-_LOG_MAX_LINES:]
        self._write(user_id, "log.md", "\n".join(lines) + "\n")

    # ── Link index ───────────────────────────────────────────────────────────

    def read_link_index(self, *, user_id: str) -> dict[str, list[str]]:
        """Đọc forward link index: {rel_path -> [slugs linked from this page]}.
        Trả về {} nếu chưa có."""
        content = self._read(user_id, "link_index.json")
        if not content:
            return {}
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {}

    def write_link_index(self, *, user_id: str, data: dict[str, list[str]]) -> None:
        """Ghi toàn bộ forward link index (overwrite)."""
        self._write(user_id, "link_index.json", json.dumps(data, ensure_ascii=False, indent=2))

    # ── Raw sources ───────────────────────────────────────────────────────────

    def write_raw(self, *, user_id: str, category: str, filename: str, content: str) -> None:
        """Lưu text thô. category: "documents" | "transcripts"."""
        self._write(user_id, f"raw/{category}/{filename}", content)

    def read_raw(self, *, user_id: str, category: str, filename: str) -> str | None:
        return self._read(user_id, f"raw/{category}/{filename}")

    def delete_raw(self, *, user_id: str, source_id: str) -> None:
        """Xóa raw file của source (thử cả documents lẫn transcripts)."""
        for category in ("documents", "transcripts"):
            rel = f"raw/{category}/{source_id}.txt"
            # Chỉ xóa nếu tồn tại (local: kiểm tra path; S3: delete idempotent)
            if self._s3 or self._local_path(user_id, rel).exists():
                self._delete(user_id, rel)
                logger.debug("wiki_raw_deleted", user_id=user_id, path=rel)

    # ── Init ─────────────────────────────────────────────────────────────────

    def ensure_wiki_structure(self, *, user_id: str) -> None:
        """Khởi tạo index.md, log.md và wiki_schema.md nếu chưa tồn tại."""
        if not self._read(user_id, "index.md"):
            self._write(user_id, "index.md", _INITIAL_INDEX)
        if not self._read(user_id, "log.md"):
            self._write(user_id, "log.md", "")
        if not self._read(user_id, "wiki_schema.md"):
            self._write(user_id, "wiki_schema.md", _WIKI_SCHEMA)
        # Local: tạo thư mục con
        if not self._s3:
            for sub in (
                "raw/documents",
                "raw/transcripts",
                "pages/entities",
                "pages/topics",
                "pages/summaries",
            ):
                Path(self._base_dir, user_id, sub).mkdir(parents=True, exist_ok=True)


_INITIAL_INDEX = """\
# Wiki Index

Chưa có trang Wiki nào. Hệ thống sẽ tự động tạo trang khi bạn upload tài liệu hoặc ghi âm cuộc họp.

## Entities
_(chưa có)_

## Benchmarks
_(chưa có)_

## Mathematical Foundations
_(chưa có)_

## Topics
_(chưa có)_

## Summaries
_(chưa có)_
"""

_WIKI_SCHEMA = """\
# Wiki Schema — MemRAG AI Research Knowledge Base

## Cấu trúc thư mục

```
wiki/{user_id}/
├── raw/                    # TẦNG 1: NGUỒN DỮ LIỆU THÔ (BẤT BIẾN)
│   ├── documents/          # Văn bản trích xuất từ PDF/Word/Excel (papers, báo cáo)
│   └── transcripts/        # Toàn bộ hội thoại từ Soniox STT (thảo luận, review)
├── pages/                  # TẦNG 2: TRI THỨC ĐÃ BIÊN DỊCH (LLM TỔNG HỢP)
│   ├── entities/           # Models, frameworks, datasets, benchmarks, researchers, labs
│   ├── topics/             # Research directions, problems, techniques, comparisons
│   └── summaries/          # Tóm tắt chuyên sâu từng paper/nguồn đơn lẻ
├── index.md                # BẢN ĐỒ TRI THỨC — Entry point cho Agent
├── log.md                  # NHẬT KÝ HOẠT ĐỘNG (Append-only)
└── wiki_schema.md          # TẦNG 3: HIẾN PHÁP — Quy tắc vận hành Wiki
```

## Quy tắc phân loại

### entities/
Trang về thực thể AI/ML/research CÓ THỂ ĐỊNH DANH RÕ RÀNG (phủ rộng toàn bộ lĩnh vực):
- **model**: mọi AI/ML model — LLM (GPT-4o, Claude, Gemini, LLaMA), CV (ViT, SAM, DINO), GenAI (DALL-E 3, Stable Diffusion, Sora, Kling), RL (AlphaGo, MuZero), Speech (Whisper), Multimodal (Flamingo, LLaVA)
- **framework**: PyTorch, JAX, HuggingFace Transformers, Diffusers, LangChain, LlamaIndex, AutoGen, CrewAI, vLLM, TGI, Triton, Google ADK
- **dataset**: GLUE, SQuAD, ImageNet, COCO, LAION, MMLU, HumanEval, GSM8K, MATH, SWE-bench, VQA, MSCOCO, Atari, MuJoCo
- **benchmark**: HELM, BIG-Bench, LMSYS Arena, AgentBench, EvalPlus, LiveCodeBench, FID, IS, ImageNet accuracy, WER (speech)
- **researcher**: Yann LeCun, Geoffrey Hinton, Andrej Karpathy, Demis Hassabis, Ian Goodfellow, Pieter Abbeel, Jitendra Malik
- **lab**: OpenAI, Anthropic, Google DeepMind, Meta AI, Mistral AI, Cohere, xAI, Stability AI, Midjourney, RunwayML, Berkeley AI Research, Stanford HAI
- **tool**: Qdrant, Weaviate, FAISS, Ray, CUDA, TensorRT, W&B, MLflow, DVC, Kubernetes
- **method**: algorithm/quy trình CỤ THỂ có thể implement được — ReAct, Self-RAG, LoRA, QLoRA, DPO, GRPO, HyDE, GraphRAG, Speculative Decoding, Tree of Thoughts, Constitutional AI, PPO fine-tuning, ControlNet conditioning, LLM-as-Judge, Self-Consistency Decoding
- **concept**: kiến trúc/paradigm TỔNG QUÁT — Transformer, Attention mechanism, Diffusion process, GAN, Contrastive Learning, In-context Learning, MoE, Agentic AI (paradigm), RAG (paradigm), Transfer Learning, Self-supervised Learning

### topics/
Trang về CHỦ ĐỀ NGHIÊN CỨU cấp độ cao — vấn đề/hướng đang được giải quyết:
- **LLM/Agentic**: "Multi-agent Orchestration", "Tool Use in LLMs", "LLM Hallucination", "AI Safety Alignment"
- **NLP**: "Machine Translation", "Information Extraction", "Semantic Parsing"
- **CV**: "Zero-shot Detection", "3D Scene Understanding", "Video Generation Coherence"
- **RL**: "Sample Efficiency", "Offline RL", "RL for Robotics"
- **GenAI**: "Controllable Image Generation", "Text-to-Video", "Multimodal Generation"
- **Efficient ML**: "Model Compression", "Inference Optimization", "Parameter-efficient Fine-tuning"
- **Cross-domain**: "Foundation Models", "Transfer Learning", "Self-supervised Learning"

### summaries/
Tóm tắt chuyên sâu từng paper/nguồn đơn lẻ:
- Mỗi document/meeting có đúng **1 summary page**
- Format: TL;DR → Đóng góp chính → Phương pháp → Kết quả → Hạn chế → Future work

### Benchmarks (trong entities/, type: benchmark)
Trang so sánh kết quả nhiều models trên cùng dataset/benchmark:
- **Bảng so sánh** (Markdown table): | Model | Score | Year | Source |
- Agent tự động cập nhật khi ingest paper mới có kết quả trên cùng benchmark
- **Trend Analysis**: 1-2 câu phân tích xu hướng dựa trên bảng kết quả
- Công thức đánh giá (nếu có): dùng $$...$$ cho LaTeX, kèm giải thích biến số

### Mathematical Foundations (trong entities/, type: concept)
Trang chứa công thức toán học dùng chung cho nhiều papers/methods:
- Dùng $$...$$ cho display math, $...$ cho inline math
- Luôn kèm **Giải thích biến số** sau mỗi công thức
- Mục đích: agent có thể tra cứu derivation/proof thay vì lặp lại trong nhiều pages
- Ví dụ: Cross-entropy loss, Attention formula, Diffusion forward/reverse process

## Format mỗi trang

```yaml
---
title: Tên đầy đủ
tags: [tag1, tag2]
type: model|framework|dataset|benchmark|researcher|lab|tool|concept|topic|summary
sources: [source_id_1, source_id_2]
last_updated: YYYY-MM-DD
version: N
---
```

## Quy ước liên kết & trích dẫn

- **Link nội bộ**: dùng full rel_path `[[pages/entities/slug.md]]`, `[[pages/topics/slug.md]]`, `[[pages/summaries/slug.md]]`
  - Slug chỉ gồm `[a-z0-9]`, không dùng gạch ngang: "U-Net" → `[[pages/entities/unet.md]]`, "LoRA" → `[[pages/entities/lora.md]]`
  - KHÔNG dùng `[[slug]]` thuần — luôn kèm đầy đủ path prefix và đuôi `.md`
- **Trích dẫn nguồn**: `[tên paper/nguồn]` (dấu ngoặc đơn, không phải wiki link)
- Giữ thuật ngữ kỹ thuật bằng tiếng Anh (không dịch "attention", "fine-tuning"...)
- Mâu thuẫn giữa nguồn: `~~thông tin cũ [nguồn cũ]~~` → thông tin mới [nguồn mới]
- Khi có mâu thuẫn hoặc nhiều phiên bản: thêm section `## Lịch sử / Tiến triển` dạng bảng

## Nguyên tắc cập nhật

1. **Entities**: trích xuất TẤT CẢ — không bỏ sót model, framework, dataset, researcher nào
2. **Topics**: chọn tối đa 3 research directions quan trọng nhất của nguồn
3. **Summary**: luôn tạo/cập nhật 1 trang tóm tắt cho mỗi nguồn
4. **Không xóa lịch sử**: strikethrough thay vì xóa khi có thông tin mâu thuẫn/cập nhật
5. **Index**: tự động rebuild sau mỗi lần ingestion
"""
