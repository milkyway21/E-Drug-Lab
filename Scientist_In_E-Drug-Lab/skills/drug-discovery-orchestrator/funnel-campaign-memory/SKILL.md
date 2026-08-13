---
name: funnel-campaign-memory
description: Use to persist and resume evidence-backed campaign state.
---

# Funnel Campaign Memory

Persist resumable campaign state without treating state metadata as scientific evidence.
Keep immutable attempts and append-only decisions wherever possible.

## When to Use

Use before any command, after submission, after validation, at stage transitions, and when
an agent or monitor restarts.

## Prerequisites

Require a stable task root and task ID. Record schema version, target/library identity,
profile, requested final count, created time, current stage, and report location.

## How to Run

Prefer campaign memory tools or manifest status. A generic agent may maintain atomic JSON
or Markdown state with temporary-file replacement. State writes must never alter scientific
artifacts or hide older attempts.

## Quick Reference

Each stage record must include status, attempt, command, cwd, input hashes, output hashes,
job/process ID, planned/observed/validated counts, resources, timestamps, validator result,
reuse decision, warnings, and next allowed stage.

## Procedure

1. Read state and reconcile it against files and live job state.
2. Mark stale metadata without deleting it.
3. Decide reuse/resume/rerun/block and append the reason.
4. Write state atomically after submission and after validation.
5. Preserve relative paths so the task directory remains portable.

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

## Pitfalls

Do not infer completion from `.done`, a PID file, chat history, or a stale database row.
Do not overwrite an attempt directory or erase a failed decision.

## Verification

Re-read the state, validate its schema, resolve every relative artifact path, compare
hashes, and ensure exactly one current stage/attempt is marked active.
