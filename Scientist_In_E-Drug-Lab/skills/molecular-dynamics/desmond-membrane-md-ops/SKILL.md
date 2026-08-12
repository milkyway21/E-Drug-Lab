---
name: desmond-membrane-md-ops
description: Build, validate, launch, resume, and monitor Schrödinger Desmond membrane MD across local GPUs using manifest-defined protocols and system-specific QC expectations. Use for POPC or other membrane systems; do not assume target-specific residue counts, ligand ASL, paths, or GPU IDs.
---

# Desmond Membrane MD Operations

Use with `desmond-md-campaign` and the funnel short/long MD skills. This skill
covers membrane-specific system QC and multi-GPU operations, not candidate
selection policy.

## Freeze the run contract

Before building or submitting, record in the task manifest:

- Input complex and pose lineage.
- Protein, ligand, membrane, cofactor, water, and ion selectors.
- Force field, solvent model, salt concentration, membrane type, and protocol.
- Equilibration and production duration, trajectory interval, and retry policy.
- Allowed GPU IDs, one-job-per-GPU policy, output root, and completion artifacts.
- Expected component counts or acceptable ranges derived from the input system.

Never infer a ligand as `UNK`, a membrane as POPC, or a particular protein chain
count unless the prepared system and manifest establish it.

## Reuse protocol assets

Prefer the validated MSJ templates under
`skills/desmond-md-campaign/scripts/protocols/`. For a shorter pilot, change only
the manifest-approved production duration. Do not rewrite equilibration blocks,
thermostat/barostat settings, restraints, or recording interval ad hoc.

Before launch, compare the rendered protocol with the selected template and
record the diff. Require `$SCHRODINGER` to be set and readable; never replace it
with a hard-coded installation path.

## Post-build system QC

Run a project-owned Schrödinger structure adapter and record:

- Total atoms and residues by component.
- Protein chain count and residues per chain.
- Ligand and cofactor counts using explicit selectors.
- Membrane lipid count and membrane type.
- Water and ion counts, net charge if available, and periodic box dimensions.
- Missing components, duplicate ligands, severe overlaps, and unreadable CMS
  topology.

Compare these values with the manifest's expected values or ranges. Published or
previous-target counts may be cited as references but must never be universal
PASS thresholds. A readable CMS alone is not build success.

## GPU allocation and launch

1. Inspect current GPU processes and memory immediately before allocation.
2. Allocate only manifest-approved idle GPUs.
3. Set both `CUDA_VISIBLE_DEVICES` and
   `SCHRODINGER_CUDA_VISIBLE_DEVICES` for each job.
4. Run one Desmond job per physical GPU unless the manifest explicitly proves a
   different safe policy.
5. Use the existing campaign launcher/queue and a terminal-independent
   supervisor. Do not rely on an interactive shell or an improvised `nohup`
   command when the project worker is available.
6. Keep each attempt in `attempt_XX`; never overwrite another attempt.

Within about 30 seconds of submission, verify the scheduler job ID, target GPU
memory/process, log progress, input CMS, protocol, and output directory. A
submission message is not completion.

## Monitoring and recovery

- Prefer completion notifications; otherwise inspect approximately every 300 to
  420 seconds for short jobs and at a manifest-defined cadence for long jobs.
- Declare a stall only when both the GPU process has disappeared and files show
  no progress beyond the configured timeout.
- Resume from readable checkpoints or completed stages. Do not rebuild or rerun
  valid work merely because monitoring restarted.
- Retry only the failed attempt with the recorded reason and unchanged scientific
  protocol unless the manifest authorizes a protocol change.

## Completion gate

After production, run
`desmond-md-campaign/scripts/validate_desmond_trajectory.py` with explicit
`--minimum-ns` and `--expected-interval-ps` matching the manifest. Require a
valid final CMS/DTR pair, sufficient duration, monotonic frames, expected
interval, and the attempt validation JSON before SEA.

Report after each phase: allocated resources, exact command/backend, job IDs,
build QC, progress, retries, validation status, and output paths.
