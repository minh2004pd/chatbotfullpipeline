---
name: docker-reset
description: Full Qdrant data reset — run when embedding dimension changes or data is corrupted. Destroys all vector data.
disable-model-invocation: true
---

This destroys all Qdrant vector data (RAG documents and mem0 memories). Use when:
- Changing embedding dimension (requires full reset)
- Qdrant data is corrupted
- Starting fresh

Run from the project root (`/home/minhdd/pet_proj/proj2`):

```bash
docker compose down -v && docker compose up -d
```

Then wait for Qdrant to be healthy before restarting the backend. Collections will be auto-created on next app startup via `ensure_collections()`.
