---
name: "dd-md-desmond"
description: "Use for cross-cutting Desmond MD operations."
---

# DD MD Desmond - Post-Docking Molecular Dynamics

Apply reusable Desmond system, GPU, launch, recovery, and validation rules shared by short and
long production stages. Prefer the stage-specific funnel skills for H8/H9 policy.

## When to Use

Use for corrected-pose system preparation, launch diagnostics, GPU assignment, checkpoint
recovery, or cross-stage MD troubleshooting after validated docking poses.

## Prerequisites

- Stable parent/pose/complex identity and validated full-system inputs.
- Existing MSJ protocol, explicit component expectations, ASLs, duration, and frame interval.
- Resolved Desmond launchers, owned GPU/host, attempt directory, and recovery policy.

## How to Run

Use this skill inside a manifest for shared operations, or invoke the native multisim command
shown below. It does not set H8/H9 duration or candidate-selection policy.

## Quick Reference

| Operation | Rule |
| --- | --- |
| System reuse | Keep validated CMS and all components |
| GPU launch | Set both CUDA visibility variables |
| Recovery | Resume exact checkpoint/attempt only |
| Analysis | Validate trajectory before SEA |

## Procedure

1. Validate complex pose/frame, CMS components, protocol, and selectors.
2. Resolve multisim/jobcontrol and probe installed help.
3. Launch one isolated attempt on one approved physical GPU.
4. Record and monitor exact job/process IDs plus file progress.
5. Validate trajectory and route only valid runs to SEA.

## Concrete Operation Procedure

Resolve launchers from the registry and inspect help:

```bash
MULTISIM="$(masld-agent platform-resolve --id sz.bin.multisim)"
RUN="$(masld-agent platform-resolve --id sz.bin.run)"
"$MULTISIM" -h; "$RUN" -h
```

For a supported job call `schrodinger_md_submit` with `mode=dry_prep`, inspect its
protocol/job directory, then submit `mode=short` only with confirmation. For a campaign,
launch the declared MSJ from `attempt_XX` with `"$MULTISIM" -WAIT -HOST "$HOST_SPEC"
-maxjob 1`, set both CUDA variables, verify GPU placement, and validate CMS/DTR before
SEA. Never infer ASL or duration from this skill.

Target-agnostic operator skill for Schrödinger Desmond stability MD.

Use the funnel Desmond skills for stage policy and `desmond-md-campaign` for
portable implementation details. This skill carries supplementary guidance for
membrane-system builds and GPU-parallel launch patterns.

## Quick links

- [`desmond-membrane-md-ops`](../desmond-membrane-md-ops/SKILL.md) — membrane
  build QC and multi-GPU operational rules.

## Key rules (also in the reference file)

1. **Reuse verified MSJ templates** — never hand-write a full protocol
   when a validated `prod_2ns_eq_50ns.msj` and `build_membrane_system.msj`
   exist in the campaign repo.
2. **Post-build composition QC is mandatory** — verify manifest-declared
   protein/ligand/membrane/water/ion/cofactor counts or ranges before submitting
   production.
3. **Use standalone launcher scripts** — never submit MD via multi-line
   inline terminal commands (escaping bugs are common: backslashes
   treated as args, cd missing separators, etc.).
4. **Set both `CUDA_VISIBLE_DEVICES` AND `SCHRODINGER_CUDA_VISIBLE_DEVICES`**
   when assigning a GPU.
5. **Verify GPU placement ~30 s after launch** with `nvidia-smi` + log
   `JobId:` line.

## Universal Manifest Invocation

Use this cross-cutting skill when the manifest needs system QC, launch diagnostics,
recovery, or GPU policy shared by a short or long run. It does not replace the H8/H9
stage-specific gates.

```bash
bash scripts/run_skill.sh --skill dd-md-desmond --manifest MANIFEST --dry-run
bash scripts/run_skill.sh --skill dd-md-desmond --manifest MANIFEST --validate
bash scripts/run_skill.sh --skill dd-md-desmond --manifest MANIFEST --execute --confirm
bash scripts/run_skill.sh --skill dd-md-desmond --manifest MANIFEST --resume --execute --confirm
```

The manifest supplies the existing system-build or multisim command, full-system input,
component expectations, GPU IDs, attempt path, timeout, and validation outputs. Use an
empty CUDA assignment for CPU-only SEA steps. Never infer membrane composition, ligand
ASL, target label, or production duration.

## Standalone Command-Line Procedure

For a direct Desmond launch, use a validated full-system CMS and an existing MSJ protocol:

```bash
SCHRODINGER="${SCHRODINGER:-}"
MULTISIM="${MULTISIM:-}"
if command -v masld-agent >/dev/null 2>&1; then
  SCHRODINGER="${SCHRODINGER:-$(masld-agent platform-resolve --id sz.env)}"
  MULTISIM="${MULTISIM:-$(masld-agent platform-resolve --id sz.bin.multisim)}"
fi
SCHRODINGER="${SCHRODINGER:?set SCHRODINGER or make sz.env resolvable}"
MULTISIM="${MULTISIM:-$SCHRODINGER/utilities/multisim}"
CMS="$(realpath inputs/validated_system.cms)"
MSJ="$(realpath inputs/prod_protocol.msj)"
OUT="$(realpath -m outputs/md/attempt_01)"
mkdir -p "$OUT"
JOBNAME="${JOBNAME:-md}"
FINAL_CMS="$OUT/${JOBNAME}-out.cms"
CUDA_VISIBLE_DEVICES="${GPU_ID:?approved GPU}" \
SCHRODINGER_CUDA_VISIBLE_DEVICES="${GPU_ID}" \
  "$MULTISIM" -WAIT -HOST "${HOST_SPEC:-localhost}" -maxjob 1 -JOBNAME "$JOBNAME" \
  -m "$MSJ" -o "$FINAL_CMS" "$CMS"
```

Keep one attempt per physical GPU, record JobDJ IDs and input hashes, and validate
continuity, topology, and final CMS/DTR before running SEA. Do not hand-write a new MSJ
to compensate for a failed monitor.

## Pitfalls

- Do not use this stage-policy-neutral skill as a replacement for H8/H9 gates.
- Do not hand-write a production MSJ when an approved protocol already exists.
- Do not rebuild or resubmit because an unrelated monitor or shell exited.

## Verification

Confirm corrected-pose lineage, full-system component checks, MSJ/input hashes, exact GPU and
job ownership, attempt isolation, normal completion, valid CMS/DTR duration and topology, and
an explicit SEA handoff or documented failure reason.
