---
name: funnel-mmgbsa
description: Use to run Prime MMGBSA on validated XP poses.
---

# H7 MMGBSA

Estimate Prime MMGBSA energies for a frozen validated pose set while retaining each source
parent, pose, protocol, unit, and failure state.

## When to Use

Use after Glide XP validation when the funnel requests an energy-based refinement step.

## Prerequisites

- Pose-viewer Maestro input with receptor first and validated ligand poses after it.
- Parent/pose lineage, Prime protocol, flexibility policy, hosts, and output schema.
- Resolvable licensed `prime_mmgbsa` executable and completed H6 validator.

## How to Run

Use the registered adapter when available, or call native `prime_mmgbsa` on the pose viewer.
Use `-ligand` only for complex-per-entry input and an explicit ASL.

## Quick Reference

| Input layout | Native option | Interpretation |
| --- | --- | --- |
| Receptor first, poses follow | No `-ligand` | Standard pose-viewer mode |
| One complex per entry | `-ligand ASL` | Explicit ligand selection |
| `-csv_output yes` | CSV result | Parse numeric energy rows |

## Procedure

1. Validate H6, input entry ordering, stable pose IDs, and protocol choices.
2. Probe `prime_mmgbsa -h` and freeze host, flexibility, and job parameters.
3. Run the native or registered command without adding implicit IFD.
4. Parse numeric energies and join every row to its XP pose.
5. Preserve missing/failed rows and report sign, units, and prediction limits.

Run Prime MMGBSA on the frozen XP pose set and join by molecule/parent ID. IFD is not
part of the default H7 path and must be explicitly requested. Completion requires
numeric binding-energy rows and traceable source poses; missing values remain visible.

Use `masld-agent funnel run/validate --stage H7`. Never perform N-by-N redocking.

## Detailed Generic Procedure

The H7 manifest declares the validated XP pose file or pose set, the molecule/parent/pose
lineage table, Prime MMGBSA backend, output CSV/JSON, host resources, and explicit command.
Use the existing project `schrodinger_mmgbsa` adapter when it represents the input; do not
write a new per-task Prime wrapper. The adapter's dry run must show pose input, output
directory, and exact backend before confirmation.

For each row preserve molecule ID, parent ID, pose ID, XP score, pose source, MMGBSA
energy, backend, and status. Require a numeric energy and traceable source pose for a
promoted row. IFD, minimization, solvent model, dielectric, and residue flexibility are
protocol choices that must be explicit in the manifest; they are not silently added to
H7. Sort only after unit and sign conventions are verified, and never describe MMGBSA as
an experimental affinity measurement.

## Universal Manifest Invocation

```bash
bash scripts/run_skill.sh --skill funnel-mmgbsa --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill funnel-mmgbsa --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill funnel-mmgbsa --manifest MANIFEST --execute --confirm
bash scripts/run_skill.sh --skill funnel-mmgbsa --manifest MANIFEST --resume --execute --confirm
```

The manifest supplies the explicit existing adapter/command, frozen XP inputs, output
schema, resources, validation, and report path. It does not infer a target or energy
cutoff.

## Concrete Operation Procedure

Resolve the registered Prime executable and project adapter before computation:

```bash
MMGBSA="$(masld-agent platform-resolve --id sz.bin.prime_mmgbsa)"
"$MMGBSA" -h
masld-agent schrodinger-mmgbsa --pose "$XP_POSE_FILE" \
  --output "$CAMPAIGN_ROOT/07_mmgbsa" --dry-run
masld-agent schrodinger-mmgbsa --pose "$XP_POSE_FILE" \
  --output "$CAMPAIGN_ROOT/07_mmgbsa" --confirm
```

Before this call run `masld-agent funnel validate --manifest "$MANIFEST" --stage H6`.
Keep XP pose, molecule/parent ID, grid, protocol, and MMGBSA row together. Require
numeric energy, source pose, unit/sign convention, normal backend completion, and one
row per promoted parent. Missing rows block promotion; they are not replaced with an
inferred value.

## Standalone Command-Line Procedure

Prime MMGBSA takes a Maestro structure file, normally a Glide pose viewer with the
receptor first and ligand poses after it. It is not an SDF descriptor command.

```bash
SCHRODINGER="${SCHRODINGER:-}"
if [ -z "${SCHRODINGER}" ] && command -v masld-agent >/dev/null 2>&1; then
  SCHRODINGER="$(masld-agent platform-resolve --id sz.env)"
fi
SCHRODINGER="${SCHRODINGER:?set SCHRODINGER or make sz.env resolvable}"
PRIME_MMGBSA="${PRIME_MMGBSA:-$SCHRODINGER/prime_mmgbsa}"
XP_POSE_MAEGZ="$(realpath inputs/xp_pose_viewer.maegz)"
OUT="$(realpath -m outputs/07_mmgbsa)"
mkdir -p "$OUT"
cd "$OUT"
"$PRIME_MMGBSA" "$XP_POSE_MAEGZ" \
  -job_type ENERGY -csv_output yes -JOBNAME TARGET_mmgbsa -WAIT
```

Use `-HOST`, `-NJOBS`, and `-LOCAL` only when supported by the installed help. Parse
the generated CSV and retain source pose, parent ID, job name, energy units/sign, and
failed rows. A numeric MMGBSA prediction is ranking evidence, not an experimental
binding free energy.

## Pitfalls

- An SDF alone is not the standard Prime MMGBSA receptor-plus-pose input.
- IFD, flexible residues, minimization, and dielectric changes are explicit protocol choices.
- More favorable predicted energy is not measured affinity or proof of mechanism.

## Verification

Require completed H6 provenance, readable Maestro input, explicit protocol and host settings,
normal Prime completion, numeric CSV rows, one source pose per energy, retained failures,
verified sign/unit convention, and exact parent/pose joins.
