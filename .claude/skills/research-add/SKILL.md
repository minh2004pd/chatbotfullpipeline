---
name: research-add
description: Standard flow for adding a new research paper to MemRAG — upload, wait for wiki ingestion, verify output. Use when onboarding a new paper into the knowledge base.
disable-model-invocation: true
---

You are guiding the user through adding a new research paper to MemRAG. Walk through each step:

## Step 1: Prepare the paper

Ask the user for:
- Paper title (for reference)
- PDF file path or URL to download from

If it's a URL, suggest downloading first:
```bash
curl -L "<url>" -o "<paper-title>.pdf"
```

## Step 2: Upload via API

```bash
curl -X POST http://localhost:8000/api/v1/documents/upload \
  -H "X-User-ID: <user_id>" \
  -F "file=@<paper-title>.pdf"
```

Note the returned `document_id` — needed for verification.

## Step 3: Wait for wiki ingestion

Wiki update runs as `asyncio.create_task()` — fire-and-forget after upload response. Wait ~10-30 seconds depending on paper length and LLM latency.

Check server logs for:
```
wiki_process_done source=<paper-title> entities=N topics=N
```

Or check log.md directly (use `/wiki-debug` for this).

## Step 4: Verify wiki output

Run `/wiki-debug` to check:
1. Did a new summary page appear in `pages/summaries/`?
2. Were entity pages created in `pages/entities/` (models, methods, researchers mentioned)?
3. Did `index.md` update with new entries?
4. Does `log.md` show `INGEST | documents | <paper-title>`?

## Step 5: Test agent response

Ask the agent about the paper:
```
"Tóm tắt về paper [paper-title]"
"[paper-title] đề xuất method gì?"
"So sánh [method-from-paper] với [other-method]"
```

Verify agent calls `read_wiki_index` first (check server logs for `agent_tool_called tool=read_wiki_index`).

## Step 6: If wiki didn't populate

Common causes:
- `WIKI_ENABLED=false` in `.env`
- LLM extraction failed (check logs for `wiki_extract_topics_failed`)
- `wiki_max_text_chars` too small — paper text was truncated before key content
- Background task silently failed (check for `wiki_update_document_failed` in logs)

Run `/adk-wiki-trace` if agent isn't using wiki in responses.
