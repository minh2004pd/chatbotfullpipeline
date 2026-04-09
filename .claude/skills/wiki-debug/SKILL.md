---
name: wiki-debug
description: Inspect wiki state for a user — list all pages, read index.md, show recent log entries. Use when wiki isn't updating correctly after ingestion or when you need to verify wiki content.
---

You are helping debug the Wiki Layer of MemRAG. Perform these steps in order:

## 1. Locate wiki directory

Check `backend/app/core/config.py` for `wiki_base_dir` default. Also check if `.env` overrides `WIKI_BASE_DIR`. Default is `./wiki` relative to where the server runs.

For local dev, wiki lives at `backend/wiki/` or the configured path.

## 2. List wiki structure

Run:
```bash
find <wiki_base_dir>/<user_id> -type f | sort
```

If user_id is unknown, check `backend/wiki/` for available user directories.

## 3. Read index.md

```bash
cat <wiki_base_dir>/<user_id>/index.md
```

Report: how many pages are listed (count `- [[` occurrences), which categories have entries (Entities/Topics/Summaries).

## 4. Show last 20 lines of log.md

```bash
tail -20 <wiki_base_dir>/<user_id>/log.md
```

Report: last INGEST entry (source name, entities count, topics count), any DELETE entries, timestamps.

## 5. Check a specific page (if user provides rel_path)

```bash
cat <wiki_base_dir>/<user_id>/<rel_path>
```

Report: frontmatter (title, type, sources, version), section headers present.

## 6. Count pages by category

```bash
ls <wiki_base_dir>/<user_id>/pages/entities/ | wc -l
ls <wiki_base_dir>/<user_id>/pages/topics/ | wc -l
ls <wiki_base_dir>/<user_id>/pages/summaries/ | wc -l
```

## 7. Summarize findings

Report:
- Total pages (entities / topics / summaries)
- Last ingestion timestamp and source
- Any anomalies (empty index, missing CLAUDE.md, stale log)
- Suggest fix if wiki looks wrong (e.g., `WIKI_ENABLED=false`, LLM extraction failed, fire-and-forget task never ran)
