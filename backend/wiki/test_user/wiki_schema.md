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
