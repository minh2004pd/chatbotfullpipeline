---
name: adk-wiki-trace
description: Diagnose why the agent isn't calling wiki tools correctly — checks tool registration, system_instruction wiki strategy, and replays a query to trace tool call behavior.
---

You are diagnosing why the MemRAG agent isn't using wiki tools (`read_wiki_index`, `read_wiki_page`, `list_wiki_pages`) as expected. Run these checks:

## Check 1: Tool registration

Read `backend/app/agents/root_agent.py`. Verify:
- `read_wiki_index`, `read_wiki_page`, `list_wiki_pages` are imported from `app.agents.tools.wiki_tools`
- All 3 are in the `tools=[...]` list passed to the Root Agent

If missing → add the import and tool to the list.

## Check 2: Circular import guard

Read `backend/app/agents/tools/wiki_tools.py`. Verify:
- There is a `_repo()` lazy helper function that does the import inside the function body
- `get_wiki_repo` is NOT imported at module level
- Each tool function calls `_repo()` at runtime, not at import time

If `get_wiki_repo` is imported at module level → move it inside `_repo()`.

## Check 3: system_instruction wiki strategy

Read `backend/app/core/llm_config.yaml`, section `prompts.system_instruction`. Verify:
- Section "Nguyên tắc: Wiki trước, RAG bổ sung" exists
- It says to call `read_wiki_index` for ALL content questions (not just "overview" queries)
- Wiki source is listed in NGUỒN DỮ LIỆU section

## Check 4: wiki_enabled flag

Check `.env` or `backend/app/core/config.py` default. Verify `WIKI_ENABLED=true` (or `wiki_enabled: bool = True` default).

Note: `wiki_enabled` only gates wiki *write* operations (ingestion). The ADK tools always work regardless — they just return `found=False` if wiki is empty.

## Check 5: Wiki actually has content

Run `/wiki-debug` to confirm wiki has pages. If `index.md` is empty or says "Chưa có trang Wiki nào" → agent correctly returns `found=False`. The fix is to upload a document or record a meeting first.

## Check 6: Log analysis

Check server logs for:
```
agent_tool_called tool=read_wiki_index   → agent IS calling wiki
wiki_index_read page_count=N             → wiki has N pages
wiki_index_empty                         → wiki is empty for this user
```

If `agent_tool_called` never appears → agent isn't invoking the tool. Likely a system_instruction issue (Check 3) or tool not registered (Check 1).

## Check 7: Replay test

Ask the agent a direct wiki question and observe logs:
```
"Tôi có những trang wiki nào?"
"read_wiki_index và cho tôi biết có gì"
```

These should always trigger `read_wiki_index` regardless of system_instruction, because they explicitly name the tool.

If even explicit tool-name queries don't work → ADK runner issue. Run `/adk-debug` for deeper ADK diagnostics.

## Summary report

Report:
- Which check failed (if any)
- Exact fix applied or recommended
- Whether the issue is tool registration, prompt strategy, empty wiki, or ADK-level
