---
name: scope-molecular-nomination
description: Use when starting a compound nomination task to lock the phenotype, library, requested final count, evidence policy, compute profile, and required reports before any biology or chemistry work.
---

# Scope Molecular Nomination

Create E0 before invoking target, structure, docking, or screening tools.

Required inputs:

- disease or phenotype and intended biological system
- official compound-library path and stable library identifier
- requested final molecule count
- target-based or phenotype-first mechanism policy
- online evidence permission and compute authorization

Write `evidence_task_plan.json`. Record an SHA-256 for the library and state whether
the run is online, cached replay, or offline. Never silently replace the official
library or infer that a small final count means a test profile.

For a complete computational funnel, call `funnel_autopilot` after E3. Preserve H0-H10
stage names. Evidence stages E0-E6 wrap that funnel rather than renumbering it.

Report completion with the locked inputs, unresolved inputs, artifact path, and next skill.
