---
name: desmond-membrane-md-ops
description: Use to operate validated Desmond membrane systems.
---

# Desmond Membrane MD Operations

Build, validate, launch, resume, and monitor membrane Desmond systems without assuming a lipid,
ligand selector, component count, force field, host, or GPU.

## When to Use

Use when the selected protein-ligand system requires an explicit membrane environment and
system-specific composition QC.

## Prerequisites

- Corrected complex pose and declared membrane orientation/composition.
- Force field, solvent, ions, cofactors, ASLs, build protocol, and component expectations.
- Approved GPU/host resources, production protocol, monitor cadence, and output root.

## How to Run

Use the manifest and shared campaign tools to build and validate, or launch a prepared native
CMS/MSJ pair directly with multisim after component and topology checks.

## Quick Reference

| Gate | Validate |
| --- | --- |
| Orientation | Protein/membrane placement and pocket access |
| Composition | Protein, ligand, lipids, solvent, ions, cofactors |
| GPU | Exact ownership and both CUDA variables |
| Trajectory | Duration, interval, continuity, topology |

## Procedure

1. Freeze membrane/system chemistry and expected component ranges.
2. Build or reuse the full system and run structure/topology/composition QC.
3. Allocate one owned GPU and launch an isolated attempt.
4. Monitor exact job/process IDs and artifacts; resume only failed units.
5. Hard-validate the trajectory before SEA or interpretation.

## Concrete Operation Procedure

Resolve launchers, then inspect GPU availability and the current CMS:

```bash
MULTISIM="$(masld-agent platform-resolve --id sz.bin.multisim)"
RUN="$(masld-agent platform-resolve --id sz.bin.run)"
"$MULTISIM" -h; "$RUN" -h
nvidia-smi --query-gpu=index,memory.used,memory.total,utilization.gpu --format=csv
```

Run project-owned system QC, compare component counts with this task's ranges, set both
CUDA variables for one approved GPU, and launch a new `attempt_XX` using the declared MSJ.
Inspect job/log/GPU ownership after submission and validate CMS/DTR duration/interval
before SEA. Membrane type, ligand selector, and counts come from the current system.

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
record the diff. Resolve `sz.bin.run` and `sz.bin.multisim` from the platform
registry; never replace them with a hard-coded installation path.

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

## Universal Manifest Invocation

```bash
bash scripts/run_skill.sh --skill desmond-membrane-md-ops --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill desmond-membrane-md-ops --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill desmond-membrane-md-ops --manifest MANIFEST --execute --confirm
bash scripts/run_skill.sh --skill desmond-membrane-md-ops --manifest MANIFEST --resume --execute --confirm
```

The manifest supplies membrane/system inputs, expected component ranges, explicit build
or launch command, approved GPUs, timeout, and QC outputs. Counts and lipid types are
task inputs, not universal thresholds; no target, membrane, ASL, or GPU is guessed.

## Standalone Command-Line Procedure

For a shared installation without a manifest, prepare a valid Desmond CMS/MSJ pair and
launch the native `multisim` command. Membrane composition and force-field choices are
task-specific and must be recorded before launch:

```bash
SCHRODINGER="${SCHRODINGER:-}"
MULTISIM="${MULTISIM:-}"
if command -v masld-agent >/dev/null 2>&1; then
  SCHRODINGER="${SCHRODINGER:-$(masld-agent platform-resolve --id sz.env)}"
  MULTISIM="${MULTISIM:-$(masld-agent platform-resolve --id sz.bin.multisim)}"
fi
SCHRODINGER="${SCHRODINGER:?set SCHRODINGER or make sz.env resolvable}"
MULTISIM="${MULTISIM:-$SCHRODINGER/utilities/multisim}"
CMS="${CMS:?prepared membrane complex CMS}"
MSJ="${MSJ:?validated Desmond MSJ}"
OUT_DIR="${OUT_DIR:-desmond_membrane}"
mkdir -p "$OUT_DIR"
test -s "$CMS" && test -s "$MSJ"
JOBNAME="${JOBNAME:-membrane_md}"
FINAL_CMS="$OUT_DIR/${JOBNAME}-out.cms"
if [ -n "${GPU_ID:-}" ]; then
  export CUDA_VISIBLE_DEVICES="$GPU_ID" SCHRODINGER_CUDA_VISIBLE_DEVICES="$GPU_ID"
fi
"$MULTISIM" -WAIT -HOST "${HOST_SPEC:-localhost}" -maxjob 1 -JOBNAME "$JOBNAME" \
  -m "$MSJ" -o "$FINAL_CMS" "$CMS"
```

Use native `multisim -h` for version-specific flags, allocate GPUs through the scheduler
or environment rather than embedding host paths, and wait on the returned job ID. Validate
CMS plus trajectory duration, frame interval, monotonicity, component continuity, and
required membrane/protein/ligand selections before SEA or interpretation. A failed build
is a gate, not an MD result.

## Pitfalls

- Do not assume POPC, `UNK`, target-specific residue counts, or a particular chain layout.
- Loss of a membrane, ion, cofactor, or component ordering invalidates continuity.
- A successful system build is not production MD completion.

## Verification

Require membrane orientation/composition provenance, component ranges and observed counts,
CMS/MSJ hashes, topology checks, owned GPU/job IDs, attempt history, normal exit, valid duration
and interval, continuity, and explicit protein/ligand/membrane selections before SEA.
