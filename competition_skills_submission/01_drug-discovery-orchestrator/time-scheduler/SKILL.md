---
name: time-scheduler
description: Use when an E-Drug Lab task needs adaptive agent wake-ups, local watchdog liveness, 48-hour stage timeouts, and resume-first recovery by composing campaign memory, Desmond, JobDJ, and Hermes cron behavior.
---

# Time Scheduler

## Concrete Operation Procedure

After a confirmed background worker, obtain the adaptive interval and create one monitor
tick; never start a second worker:

```bash
masld-agent funnel monitor-plan --manifest "$MANIFEST"
masld-agent funnel autopilot-status --manifest "$MANIFEST"
```

Use the returned `cron_schedule` and prompt with Hermes `cronjob`. At each tick call
status first; on a stage transition call `funnel report-update`, then request a fresh
monitor plan. Inspect process/job and heartbeat before recovery. Stop at completed,
failed, blocked, or gated preflight; keep the local watchdog separate from model wakeups.

Use this as the cross-stage scheduling umbrella. It composes `funnel-campaign-memory`,
`desmond-md-campaign`, `pose-library-screening`, and the Hermes native `cronjob` tool;
do not copy their backend-specific waiting or recovery recipes.

## Start

After a confirmed background `funnel_autopilot` call:

1. Call `funnel_monitor_plan` to obtain the current stage, adaptive interval, and prompt.
2. Create one short Hermes cron tick using the returned `cron_schedule` and prompt.
3. On every tick call `funnel_autopilot_status` first; never start a second worker while
   the existing worker or its process group is alive.
4. If a stage completed, call `funnel_report_update`, then request a new plan for the next
   stage and create the next one-shot tick.
5. Stop scheduling after `completed`, `blocked_or_failed`, `failed`, or `gated_preflight`.

The project watchdog checks process and log liveness locally every 60 seconds and may
resume a dead worker from the manifest at most three times. A worker recovery is not a
scientific completion claim; validate the existing artifacts before continuing.

## Adaptive intervals

| Expected stage duration | Agent wake interval |
|---|---:|
| `<=20 min` | 10 min |
| `20 min-2 h` | 30 min |
| `2-12 h` | 1 h |
| `>12 h` through 48 h | 3 h |

The local watchdog remains at 60 seconds regardless of the model-wake interval. A quiet
tick returns exactly `[SILENT]`; report only stage transitions, errors, recovery, or final
completion.

## Long-task rules

- Never use a multi-hour `sleep` inside a model or tool call.
- A submitted JobDJ/Desmond job is not complete until its backend validator passes.
- Preserve task locks, attempt directories, logs, and existing validated artifacts.
- Do not kill a live GPU job merely because a heartbeat is old; inspect the process group,
  backend job state, and output progress first.
- Enforce a finite per-stage timeout of at most 48 hours and record the timeout in state.
- Read `funnel-campaign-memory` before recovery and `desmond-md-campaign` or
  `pose-library-screening` before backend-specific monitoring.

## Interfaces

```bash
masld-agent funnel monitor-plan --manifest MANIFEST
masld-agent funnel autopilot-status --manifest MANIFEST
masld-agent funnel report-update --manifest MANIFEST --stage H9 --analysis "..."
```

Keep the terminal Hermes process open for the scheduler. The durable scientific source of
truth remains the manifest, stage JSON/Markdown, heartbeat, and validated artifacts.

Human-readable scheduler handoffs and cumulative reports default to Chinese; use the task's
`language=en` setting when an English handoff is required. Heartbeat fields and status IDs
remain language-neutral.

## Universal Manifest Invocation

Use this scheduler for any target and long-running stage. Declare the task/stage,
inputs, heartbeat and output paths, resource/time policy, validation, reporting,
and explicit argv `command` or ordered `steps`; do not infer a 48-hour limit.

```bash
bash scripts/run_skill.sh --skill time-scheduler --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill time-scheduler --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill time-scheduler --manifest MANIFEST --status
bash scripts/run_skill.sh --skill time-scheduler --manifest MANIFEST --execute --confirm
bash scripts/run_skill.sh --skill time-scheduler --manifest MANIFEST --resume --execute --confirm
```

Keep wakeups adaptive and recovery resume-first; the manifest, heartbeat, logs,
and validated outputs remain the source of truth.

## Standalone Command-Line Procedure

For a manifest-free long run, use a separate terminal supervisor with an explicit target
and conservative polling interval. Keep the supervisor alive independently of chat:

```bash
TARGET_ID="${TARGET_ID:?target gene or protein identifier}"
INTERVAL="${MONITOR_SECONDS:-900}"
while :; do
  STATUS="$(masld-agent funnel autopilot-status --target-id "$TARGET_ID" 2>&1 || true)"
  printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$STATUS"
  printf '%s\n' "$STATUS" > "${STATUS_FILE:-autopilot_status.json}"
  printf '%s\n' "$STATUS" | jq -e '.status == "completed" or .status == "failed"' >/dev/null 2>&1 && break
  sleep "$INTERVAL"
done
```

On each wakeup compare the reported job/stage ID with the last state, inspect only the
declared outputs, and resume from validated artifacts. Do not launch a duplicate job
because a status query is delayed; write a gate and escalate only after the recorded
timeout or explicit failure condition.
