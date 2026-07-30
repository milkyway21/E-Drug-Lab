---
name: funnel-campaign-memory
description: Read and update structured task state (CAMPAIGN.md) without enabling Hermes native memory.
---

# Funnel Campaign Memory

Use `campaign_memory_read` before a task and `campaign_memory_write` only for
stage decisions. Scientific truth remains in the task manifest and artifacts.
Never infer completion from chat text, a submitted job, or a `.done` marker alone.

Speak to the user as 「任务」— do not say 「战役」. Keep internal IDs
(`CAMPAIGN.md`, `campaign_memory_*`, this skill name).

For machine state use:

```bash
masld-agent funnel status --manifest /abs/path/inputs/manifest.json
masld-agent funnel validate --manifest /abs/path/inputs/manifest.json --stage H8
```

Record absolute evidence paths and whether results were reused or newly produced.
