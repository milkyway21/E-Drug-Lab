---
name: time-scheduler
description: Use when an E-Drug Lab task needs adaptive agent wake-ups, local watchdog liveness, 48-hour stage timeouts, and resume-first recovery by composing campaign memory, Desmond, JobDJ, and Hermes cron behavior.
---

# Time Scheduler

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
