---
name: funnel-desmond-short-md
description: H8 corrected-pose Desmond short MD with hard validation and SEA.
---

# H8 Short MD

Use `$SCHRODINGER`, not a new conda environment. Reuse validated CMS systems and MSJ
templates. Short production may be a pilot 10 ns or standard 50 ns, but the manifest
must state the duration and equilibration protocol. Submission requires explicit
confirmation and one known GPU per job.

Validate the final production CMS/DTR with the bundled
`desmond-md-campaign/scripts/validate_desmond_trajectory.py`, then run SEA only on
validated trajectories. A submitted job, readable CMS alone, or dry prep is not PASS.
