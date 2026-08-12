---
name: funnel-campaign-memory
description: Read and update structured task state in CAMPAIGN.md without enabling Hermes native memory. Use before execution, after every stage decision, and when resuming a task; never treat chat text as scientific completion evidence.
---

# Funnel Campaign Memory

## Concrete Operation Procedure

At task start and before recovery, read manifest-backed status:

```bash
masld-agent funnel status --manifest "$MANIFEST"
masld-agent funnel autopilot-status --manifest "$MANIFEST"
```

After a stage decision write one handoff containing stage, status, tools, inputs, observed
count, validation, warnings, relative artifact paths, and next stage. If a worker dies,
inspect the exact process/job and heartbeat, then use resume only after artifact validation.
Never use chat claims or `.done` markers as scientific completion.

Use `campaign_memory_read` before a task and `campaign_memory_write` only for
stage decisions. Scientific truth remains in the task manifest and artifacts.
Never infer completion from chat text, a submitted job, or a `.done` marker alone.

Use the user-facing term "task" rather than the legacy term "campaign" in Chinese output.
Keep internal IDs (`CAMPAIGN.md`, `campaign_memory_*`, and this skill name) unchanged.

Human-readable handoffs and reports default to Chinese. Use `language=en` when an English
artifact is explicitly requested; state and artifact keys remain language-neutral.

For machine state use:

```bash
masld-agent funnel status --manifest "$MANIFEST"
masld-agent funnel validate --manifest "$MANIFEST" --stage H8
```

Record evidence paths relative to `campaign_root` in portable reports and whether results
were reused or newly produced.

## Universal Manifest Invocation

Use this skill for any long-running target task by declaring the task/stage
identity, inputs, state and artifact outputs, resources, validation, reporting,
and an explicit argv `command` or ordered `steps`. Never infer a campaign root.

```bash
bash scripts/run_skill.sh --skill funnel-campaign-memory --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill funnel-campaign-memory --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill funnel-campaign-memory --manifest MANIFEST --status
bash scripts/run_skill.sh --skill funnel-campaign-memory --manifest MANIFEST --execute --confirm
bash scripts/run_skill.sh --skill funnel-campaign-memory --manifest MANIFEST --resume --execute --confirm
```

Write heartbeats, handoffs, and reuse decisions under `campaign_root`; keep
relative paths in portable reports and preserve prior attempts.

## Standalone Command-Line Procedure

Maintain durable state with a task-root JSON file when no manifest is available:

```bash
STATE="${STATE:?task state JSON}"
STAGE="${STAGE:?stage identifier}"
STATUS="${STATUS:?running, completed, failed, or blocked}"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
mkdir -p "$(dirname "$STATE")"
test -s "$STATE" || printf '%s\n' '{"stages":{},"events":[]}' > "$STATE"
tmp="${STATE}.tmp"
jq --arg stage "$STAGE" --arg status "$STATUS" --arg now "$NOW" \
  '.stages[$stage] = ((.stages[$stage] // {}) + {status:$status,updated_at:$now}) | .events += [{stage:$stage,status:$status,at:$now}]' \
  "$STATE" > "$tmp" && mv "$tmp" "$STATE"
```

Store input/output hashes, exact command or job ID, planned versus observed counts,
validation result, reuse decision, and next allowed stage in the same state record. This
state is a resume aid, not proof of completion; validators and artifacts remain the
source of truth.
