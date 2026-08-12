---
name: molecular-dynamics
description: Runs corrected-pose Desmond short and long MD with recovery and trajectory QC. Use for H8-H9 after validated docking complexes and explicit compute authorization.
---

# Molecular Dynamics

This main skill routes the short-to-long MD handoff and keeps GPU jobs resumable.

## Child skills

- `funnel-desmond-short-md` for H8 short MD
- `funnel-desmond-long-md` for H9 long MD
- `dd-md-desmond` for cross-cutting Desmond operations
- `dd-md-desmond-sea-qc` for trajectory/SEA QC
- `desmond-md-campaign` for campaign monitoring and analysis
- `desmond-membrane-md-ops` for membrane-specific setup

## Gate

Correct pose frames before membrane/system setup, validate job ownership and backend state,
then validate trajectories, RMSD/contacts, and report figures. Do not kill a live task job
because a heartbeat is old; inspect its process group and scheduler state first.
