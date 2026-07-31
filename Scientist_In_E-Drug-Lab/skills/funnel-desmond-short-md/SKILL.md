---
name: funnel-desmond-short-md
description: Run the H8 corrected-pose Desmond short-MD gate with manifest-defined duration, hard CMS/DTR validation, and official SEA. Use after MMGBSA selection; do not infer completion from submission, dry preparation, or a readable CMS alone.
---

# H8 Short MD

Use `$SCHRODINGER`, not a new conda environment. Reuse validated CMS systems and MSJ
templates. Short production may be a pilot 10 ns or standard 50 ns, but the manifest
must state the duration and equilibration protocol. Submission requires explicit
confirmation and one known GPU per job.

Validate the final production CMS/DTR with the bundled
`desmond-md-campaign/scripts/validate_desmond_trajectory.py`, then run SEA only on
validated trajectories. Always pass `--minimum-ns` equal to the manifest's short
production duration and `--expected-interval-ps` equal to its recording interval;
never rely on validator defaults. A submitted job, readable CMS alone, or dry prep
is not PASS.
