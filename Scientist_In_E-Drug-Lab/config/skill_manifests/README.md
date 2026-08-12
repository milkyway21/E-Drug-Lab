# Generic Skill Manifest

`run_skill.sh` is the reusable entrypoint for every canonical skill. It accepts a
task manifest rather than a project-specific chat prompt, so the same skill can
be used with another target, disease, library, or compute backend.

## Contract

Each manifest uses `e-drug-lab.skill-manifest/v1` and declares:

- `task_id`, `skill`, and a free-form `stage` identifier;
- `campaign_root`, resolved relative to the manifest when written as `.`;
- `inputs`, `outputs`, `resources`, `validation`, and `reporting` objects;
- optional `reporting.language`, which defaults to `zh` for human-readable artifacts and
  accepts `en` when an English artifact is required;
- either an argv-array `command` or ordered argv-array `steps`.

The launcher never guesses a target-specific adapter. This keeps one entrypoint
usable for every target, disease, library, and external scientific backend.

Never put a shell pipeline, `bash -c`, `python -c`, secret, or host-specific
absolute path in a portable manifest. Use `{manifest}`, `{campaign_root}`,
`{task_id}`, `{skill}`, and `{stage}` placeholders in argv values when needed.

## Commands

Preview the resolved commands first. The default is also a read-only preview:

```bash
bash scripts/run_skill.sh --skill SKILL_NAME \
  --manifest MANIFEST --dry-run
```

Execute only after inspecting the preview and explicitly confirming:

```bash
bash scripts/run_skill.sh --skill SKILL_NAME \
  --manifest MANIFEST --execute --confirm
```

Use `--status` for the last run plus output evidence, `--validate` for output
validation only, and `--resume --execute --confirm` to reuse valid outputs or
continue an incomplete attempt. Logs and `result.json` are written beneath the
manifest campaign root in `logs/skills/<skill>/`.

The existing direct entry remains supported for the explicit Prudent adapter:
`masld-agent funnel prudent-physchem --manifest MANIFEST`. It is target-agnostic
when the manifest supplies the target's clean PDB, native SDF, PT, evaluator,
and output paths; it is not the generic default for other skills.

`--profile full` remains the default for the separate H0-H10 funnel planner. The
`test` profile is opt-in and must be selected explicitly; a small final count
does not implicitly switch profiles.

The language setting affects human-readable Markdown, DOCX/PDF, and handoff text only.
Machine-readable JSON keys, CSV column names, registry IDs, and validation flags remain
stable across `zh` and `en`.

`generic.example.json` is a target-neutral contract template. Copy its fields into a
task manifest, replace the explicit executable and paths, then run `--dry-run` before
execution. `funnel-diffdynamic-prudent.example.json` shows the direct H1B adapter shape;
it intentionally contains placeholders for the installed evaluator and Python and is
not executable until those fields are replaced.
