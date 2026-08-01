#!/usr/bin/env python3
"""masld-agent CLI."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer
from rich import print as rprint

from masld_agent.config import DEFAULT_COMPETITION, PKG_ROOT
from masld_agent.models import DiseaseScope
from masld_agent.supervisor import evaluate_single_target, run_offline_demo, run_pipeline

app = typer.Typer(add_completion=False, no_args_is_help=True, name="masld-agent")
evidence_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Deterministic E0-E6 biology, structure, compound-evidence, and nomination tools.",
)
funnel_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Deterministic H0-H10 campaign planning, execution, and validation.",
)
app.add_typer(evidence_app, name="evidence")
app.add_typer(funnel_app, name="funnel")


@app.command("run")
def cmd_run(
    competition: Path = typer.Option(DEFAULT_COMPETITION, "--competition"),
    disease: DiseaseScope = typer.Option(DiseaseScope.MASLD, "--disease"),
    modality: str = typer.Option("small_molecule_inhibitor", "--modality"),
    top_targets: int = typer.Option(10, "--top-targets"),
    output: Path = typer.Option(PKG_ROOT / "runs" / "demo", "--output"),
    online: bool = typer.Option(False, "--online/--offline-panel"),
    offline_replay: bool = typer.Option(False, "--offline-replay"),
    library: Optional[Path] = typer.Option(None, "--library", exists=True, dir_okay=False),
    final_count: int = typer.Option(10, "--final-count", min=1),
    target_gene: Optional[str] = typer.Option(None, "--target-gene"),
    evidence_profile: str = typer.Option("generic", "--evidence-profile"),
    online_enrichment_limit: int = typer.Option(50, "--online-enrichment-limit", min=0),
    library_source: str = typer.Option("official_sdf_library", "--library-source"),
) -> None:
    """Run target discovery, or E0-E6 nomination when a library is supplied."""
    out = run_pipeline(
        output,
        competition_config=competition,
        disease=disease,
        modality=modality,
        top_targets=top_targets,
        online=online,
        offline_replay=offline_replay,
        library_path=library,
        final_count=final_count,
        target_gene=target_gene,
        evidence_profile=evidence_profile,
        online_enrichment_limit=online_enrichment_limit,
        library_source=library_source,
    )
    rprint(f"[green]OK[/green] wrote run to {out}")


@app.command("evaluate-target")
def cmd_evaluate_target(
    gene: str = typer.Option(..., "--gene"),
    uniprot: Optional[str] = typer.Option(None, "--uniprot"),
    output: Path = typer.Option(PKG_ROOT / "runs", "--output"),
    competition: Path = typer.Option(DEFAULT_COMPETITION, "--competition"),
) -> None:
    out = evaluate_single_target(
        gene=gene,
        uniprot=uniprot,
        output_dir=output,
        competition_config=competition,
    )
    rprint(f"[green]OK[/green] wrote {out}")


@app.command("offline-demo")
def cmd_offline_demo(
    fixture: Path = typer.Option(
        PKG_ROOT / "tests" / "fixtures" / "hsd17b13",
        "--fixture",
    ),
    output: Path = typer.Option(PKG_ROOT / "runs", "--output"),
    competition: Path = typer.Option(DEFAULT_COMPETITION, "--competition"),
) -> None:
    """Fully offline reproducible demo (no network required)."""
    out = run_offline_demo(fixture, output, competition_config=competition)
    rprint(f"[green]OK[/green] offline demo -> {out}")


@app.command("chat")
def cmd_chat() -> None:
    """Deprecated: dialogue is Hermes multi-provider chat, not a hardcoded LLM REPL."""
    rprint(
        "[yellow]masld-agent chat 已移除[/yellow]。请用 Hermes 对话（人设见 config/SOUL.md）：\n"
        "  bash scripts/start_agent.sh\n"
        "  hermes chat --provider openai-relay\n"
        "  hermes model"
    )
    raise SystemExit(2)


@app.command("competition-brief")
def cmd_competition_brief(
    competition: Path = typer.Option(DEFAULT_COMPETITION, "--competition"),
) -> None:
    """Print AI4S life-science brief (dual readout, scoring, resources). Offline."""
    from masld_agent.tools.ai4s_brief import format_competition_brief, load_ai4s_config

    print(format_competition_brief(load_ai4s_config(competition)))


@app.command("dual-readout-lint")
def cmd_dual_readout_lint(
    text: Optional[Path] = typer.Option(
        None,
        "--text",
        help="Path to text/markdown; omit to read stdin",
    ),
    competition: Path = typer.Option(DEFAULT_COMPETITION, "--competition"),
) -> None:
    """Lint nomination/plan text for HepG2 dual readout (lipid + viability)."""
    import json

    from masld_agent.tools.ai4s_brief import lint_dual_readout, load_ai4s_config

    if text is not None:
        body = text.read_text(encoding="utf-8")
    else:
        body = sys.stdin.read()
    result = lint_dual_readout(body, load_ai4s_config(competition))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 1)


@app.command("export-top10-template")
def cmd_export_top10_template(
    output: Path = typer.Option(
        PKG_ROOT / "runs" / "top10_nomination_template.csv",
        "--output",
    ),
    competition: Path = typer.Option(DEFAULT_COMPETITION, "--competition"),
) -> None:
    """Write official-style Top10 nomination CSV template (no invented structures)."""
    from masld_agent.submission import export_top10_template
    from masld_agent.tools.ai4s_brief import load_ai4s_config

    path = export_top10_template(output, load_ai4s_config(competition))
    rprint(f"[green]OK[/green] template -> {path}")


@app.command("validate-submission")
def cmd_validate_submission(
    run_dir: Path = typer.Option(..., "--run-dir"),
    top10_csv: Optional[Path] = typer.Option(None, "--top10-csv"),
    competition: Path = typer.Option(DEFAULT_COMPETITION, "--competition"),
) -> None:
    """Validate run artifacts against AI4S submission checklist."""
    import json

    from masld_agent.submission import validate_submission, write_validation_report

    result = validate_submission(
        run_dir, top10_csv=top10_csv, competition_config=competition
    )
    md = write_validation_report(run_dir, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    rprint(f"[cyan]report[/cyan] {md}")
    raise SystemExit(0 if result["ok"] else 1)


@app.command("hepg2-plan")
def cmd_hepg2_plan(
    run_dir: Path = typer.Option(..., "--run-dir"),
    competition: Path = typer.Option(DEFAULT_COMPETITION, "--competition"),
) -> None:
    """Write HepG2-FFA dual-readout validation plan skeleton for a run."""
    from masld_agent.submission import write_hepg2_plan

    path = write_hepg2_plan(run_dir, competition_config=competition)
    rprint(f"[green]OK[/green] {path}")


@app.command("pack-submission")
def cmd_pack_submission(
    run_dir: Path = typer.Option(..., "--run-dir"),
    output: Path = typer.Option(..., "--output"),
    top10_csv: Optional[Path] = typer.Option(None, "--top10-csv"),
    competition: Path = typer.Option(DEFAULT_COMPETITION, "--competition"),
) -> None:
    """Pack run + AI4S checklist/template into a submission zip."""
    from masld_agent.submission import pack_submission

    path = pack_submission(
        run_dir,
        output,
        top10_csv=top10_csv,
        competition_config=competition,
    )
    rprint(f"[green]OK[/green] bundle -> {path}")


def _json_print(payload: dict) -> None:
    import json

    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


@evidence_app.command("target")
def cmd_evidence_target(
    gene: str = typer.Option(..., "--gene"),
    disease: str = typer.Option("MASLD", "--disease"),
    online: bool = typer.Option(False, "--online/--offline"),
    offline_replay: bool = typer.Option(False, "--offline-replay"),
    output: Optional[Path] = typer.Option(None, "--output"),
) -> None:
    """Build a target biology card from verified public sources."""
    from masld_agent.evidence_pipeline import build_target_evidence_card

    from masld_agent.http_cache import CachedHttp

    card = build_target_evidence_card(
        gene,
        disease,
        online=online or offline_replay,
        http=CachedHttp(cache_only=offline_replay),
    )
    payload = card.model_dump(mode="json")
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            __import__("json").dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    _json_print(payload)


@evidence_app.command("structures")
def cmd_evidence_structures(
    gene: Optional[str] = typer.Option(None, "--gene"),
    uniprot: Optional[str] = typer.Option(None, "--uniprot"),
    limit: int = typer.Option(25, "--limit", min=1, max=100),
    offline_replay: bool = typer.Option(False, "--offline-replay"),
) -> None:
    """Search and rank experimental RCSB structures for a target."""
    from masld_agent.tools.pdb import discover_structure_candidates

    from masld_agent.http_cache import CachedHttp

    structures = discover_structure_candidates(
        gene=gene,
        uniprot_id=uniprot,
        limit=limit,
        http=CachedHttp(cache_only=offline_replay),
    )
    _json_print({"structures": [item.model_dump(mode="json") for item in structures]})


@evidence_app.command("prepare-structure")
def cmd_evidence_prepare_structure(
    pdb_id: str = typer.Option(..., "--pdb-id"),
    ligand_id: str = typer.Option(..., "--ligand-id"),
    output: Path = typer.Option(..., "--output"),
    chains: str = typer.Option("", "--chains", help="Comma-separated target protein chains"),
    ligand_chain: Optional[str] = typer.Option(None, "--ligand-chain"),
    ligand_resseq: Optional[int] = typer.Option(None, "--ligand-resseq"),
    ligand_icode: Optional[str] = typer.Option(None, "--ligand-icode"),
    keep_hetero: str = typer.Option("", "--keep-hetero", help="Comma-separated cofactors/metals"),
    model: int = typer.Option(1, "--model", min=1),
    source_pdb: Optional[Path] = typer.Option(None, "--source-pdb", exists=True),
    source_mmcif: Optional[Path] = typer.Option(None, "--source-mmcif", exists=True),
    ccd_cif: Optional[Path] = typer.Option(None, "--ccd-cif", exists=True),
    offline_replay: bool = typer.Option(False, "--offline-replay"),
) -> None:
    """Download and prepare a clean receptor plus native-coordinate ligand."""
    from masld_agent.tools.structure_prep import prepare_native_structure

    manifest = prepare_native_structure(
        pdb_id=pdb_id,
        ligand_id=ligand_id,
        output_dir=output,
        chains=[value.strip() for value in chains.split(",") if value.strip()],
        ligand_chain=ligand_chain,
        ligand_resseq=ligand_resseq,
        ligand_icode=ligand_icode,
        keep_hetero=[value.strip() for value in keep_hetero.split(",") if value.strip()],
        model=model,
        source_pdb=source_pdb,
        source_mmcif=source_mmcif,
        ccd_cif=ccd_cif,
        offline_replay=offline_replay,
    )
    _json_print(manifest)


@evidence_app.command("nominate")
def cmd_evidence_nominate(
    library: Path = typer.Option(..., "--library", exists=True, dir_okay=False),
    output: Path = typer.Option(..., "--output"),
    final_count: int = typer.Option(10, "--final-count", min=1),
    disease: str = typer.Option("MASLD", "--disease"),
    target_gene: Optional[str] = typer.Option(None, "--target-gene"),
    online: bool = typer.Option(False, "--online/--offline"),
    offline_replay: bool = typer.Option(False, "--offline-replay"),
    online_enrichment_limit: int = typer.Option(50, "--online-enrichment-limit", min=0),
    library_source: str = typer.Option("official_sdf_library", "--library-source"),
) -> None:
    """Run the complete E0-E6 evidence envelope and nominate compounds."""
    from masld_agent.evidence_pipeline import run_evidence_nomination

    result = run_evidence_nomination(
        library,
        output,
        final_count=final_count,
        disease=disease,
        target_gene=target_gene,
        online=online,
        offline_replay=offline_replay,
        online_enrichment_limit=online_enrichment_limit,
        library_source=library_source,
    )
    _json_print({"status": "completed", "output_dir": str(result)})


@funnel_app.command("plan")
def cmd_funnel_plan(
    final_count: int = typer.Option(..., "--final-count", min=1),
    profile: str = typer.Option("full", "--profile", help="full (default) or explicit test"),
    manifest: Optional[Path] = typer.Option(None, "--manifest"),
    target_id: Optional[str] = typer.Option(None, "--target-id"),
) -> None:
    """Infer all stage counts and allocate available local resources."""
    from masld_agent.funnel.planner import plan_campaign

    payload = plan_campaign(
        final_count,
        manifest_path=manifest,
        target_id=target_id,
        profile=profile,
        write=True,
    )
    _json_print(payload)


@funnel_app.command("preflight")
def cmd_funnel_preflight(
    manifest: Path = typer.Option(..., "--manifest", exists=True, dir_okay=False),
) -> None:
    """Read-only campaign input, environment, and adapter preflight."""
    from masld_agent.funnel.runner import preflight_campaign

    payload = preflight_campaign(manifest)
    _json_print(payload)
    raise SystemExit(0 if payload.get("status") == "ok" else 1)


@funnel_app.command("status")
def cmd_funnel_status(
    manifest: Path = typer.Option(..., "--manifest", exists=True, dir_okay=False),
) -> None:
    """Validate all stages without trusting chat text or marker files."""
    from masld_agent.funnel.runner import stage_status

    payload = stage_status(manifest)
    _json_print(payload)
    raise SystemExit(0 if payload.get("status") == "ok" else 1)


@funnel_app.command("validate")
def cmd_funnel_validate(
    stage: str = typer.Option(..., "--stage"),
    manifest: Path = typer.Option(..., "--manifest", exists=True, dir_okay=False),
) -> None:
    """Hard-validate one stage's declared or conventional artifacts."""
    from masld_agent.funnel.runner import validate_stage

    payload = validate_stage(manifest, stage)
    _json_print(payload)
    raise SystemExit(0 if payload.get("status") == "ok" else 1)


@funnel_app.command("run")
def cmd_funnel_run(
    stage: str = typer.Option(..., "--stage"),
    manifest: Path = typer.Option(..., "--manifest", exists=True, dir_okay=False),
    execute: bool = typer.Option(False, "--execute"),
    confirm: bool = typer.Option(False, "--confirm"),
) -> None:
    """Reuse valid outputs or run one configured stage through an argv adapter."""
    from masld_agent.funnel.runner import run_stage

    payload = run_stage(manifest, stage, execute=execute, confirm=confirm)
    _json_print(payload)
    accepted = {"completed", "dry_run", "submitted_or_incomplete"}
    raise SystemExit(0 if payload.get("status") in accepted else 1)


@funnel_app.command("autopilot")
def cmd_funnel_autopilot(
    final_count: int = typer.Option(..., "--final-count", min=1),
    profile: str = typer.Option("full", "--profile", help="full (default) or explicit test"),
    manifest: Optional[Path] = typer.Option(None, "--manifest"),
    target_id: Optional[str] = typer.Option(None, "--target-id"),
    execute: bool = typer.Option(False, "--execute"),
    confirm: bool = typer.Option(False, "--confirm"),
    background: bool = typer.Option(False, "--background"),
) -> None:
    """Plan resources and run/report H0-H10 through one deterministic call."""
    from masld_agent.funnel.autopilot import run_autopilot, start_autopilot

    if execute and background:
        payload = start_autopilot(
            final_count,
            manifest_path=manifest,
            target_id=target_id,
            profile=profile,
            confirm=confirm,
        )
    else:
        payload = run_autopilot(
            final_count,
            manifest_path=manifest,
            target_id=target_id,
            profile=profile,
            execute=execute,
            confirm=confirm,
        )
    _json_print(payload)
    raise SystemExit(0 if payload.get("status") in {"planned", "completed", "queued", "running"} else 1)


@funnel_app.command("autopilot-status")
def cmd_funnel_autopilot_status(
    manifest: Optional[Path] = typer.Option(None, "--manifest"),
    target_id: Optional[str] = typer.Option(None, "--target-id"),
) -> None:
    """Read persistent autopilot worker and latest stage-report state."""
    from masld_agent.funnel.autopilot import autopilot_status

    payload = autopilot_status(manifest_path=manifest, target_id=target_id)
    _json_print(payload)
    raise SystemExit(0 if payload.get("status") != "error" else 1)


@funnel_app.command("inspect-sdf")
def cmd_funnel_inspect_sdf(
    input_path: Path = typer.Option(..., "--input", exists=True, dir_okay=False),
) -> None:
    """Count plain or gzip-compressed SDF records without text-decoding mistakes."""
    from masld_agent.funnel.utilities import inspect_sdf

    payload = inspect_sdf(input_path)
    _json_print(payload)
    raise SystemExit(0 if payload.get("status") == "ok" else 1)


@funnel_app.command("prudent-physchem")
def cmd_funnel_prudent_physchem(
    manifest: Path = typer.Option(..., "--manifest", exists=True, dir_okay=False),
    execute: bool = typer.Option(False, "--execute"),
    confirm: bool = typer.Option(False, "--confirm"),
) -> None:
    """Reconstruct Prudent PT and compute physchem with Vina execution disabled."""
    from masld_agent.funnel.diffdynamic import prudent_physchem

    payload = prudent_physchem(manifest, execute=execute, confirm=confirm)
    _json_print(payload)
    raise SystemExit(0 if payload.get("status") in {"dry_run", "completed"} else 1)


@funnel_app.command("prudent-generate")
def cmd_funnel_prudent_generate(
    manifest: Path = typer.Option(..., "--manifest", exists=True, dir_okay=False),
    execute: bool = typer.Option(False, "--execute"),
    confirm: bool = typer.Option(False, "--confirm"),
) -> None:
    """Render a target-sized Prudent config and run the existing DiffDynamic sampler."""
    from masld_agent.funnel.diffdynamic import prudent_generate

    payload = prudent_generate(manifest, execute=execute, confirm=confirm)
    _json_print(payload)
    raise SystemExit(0 if payload.get("status") in {"dry_run", "completed"} else 1)


@funnel_app.command("rank-glide")
def cmd_funnel_rank_glide(
    csv_path: Path = typer.Option(..., "--csv", exists=True, dir_okay=False),
    output: Path = typer.Option(..., "--output"),
    top: int = typer.Option(..., "--top", min=1),
    parent_column: str = typer.Option("parent_id", "--parent-column"),
    score_column: str = typer.Option("r_i_glide_gscore", "--score-column"),
) -> None:
    """Select each parent's numeric best Glide score deterministically."""
    from masld_agent.funnel.utilities import rank_glide_parents

    payload = rank_glide_parents(
        csv_path,
        output,
        top=top,
        parent_column=parent_column,
        score_column=score_column,
    )
    _json_print(payload)
    raise SystemExit(0 if payload.get("status") == "ok" else 1)


@app.command("platform-catalog")
def cmd_platform_catalog(
    system: Optional[str] = typer.Option(None, "--system", help="dd|ed|sz"),
    entry_id: Optional[str] = typer.Option(None, "--id"),
    stage: Optional[str] = typer.Option(None, "--stage"),
) -> None:
    """Query DiffDynamic / e-drug-lab / Schrödinger capability catalog."""
    from masld_agent.platform.catalog import format_entry, get_entry, list_entries, summarize_systems

    if entry_id:
        e = get_entry(entry_id)
        if not e:
            rprint(f"[red]unknown id[/red] {entry_id}")
            raise SystemExit(1)
        print(format_entry(e))
        return
    summary = summarize_systems()
    entries = list_entries(system=system, stage=stage)
    _json_print(
        {
            "summary": summary,
            "n": len(entries),
            "ids": [e.get("id") for e in entries],
            "entries": entries,
        }
    )


@app.command("platform-health")
def cmd_platform_health() -> None:
    """Probe DiffDynamic / e-drug-lab backend / Schrödinger install health."""
    from masld_agent.platform.health import platform_health

    payload = platform_health()
    _json_print(payload)
    raise SystemExit(0 if payload.get("status") == "ok" else 1)


@app.command("diffdynamic-status")
def cmd_diffdynamic_status() -> None:
    from masld_agent.platform.diffdynamic_tools import diffdynamic_status

    _json_print(diffdynamic_status())


@app.command("diffdynamic-generate")
def cmd_diffdynamic_generate(
    protein: Path = typer.Option(..., "--protein"),
    ligand: Path = typer.Option(..., "--ligand"),
    mode: str = typer.Option("denovo_fast", "--mode"),
    molecule: Optional[Path] = typer.Option(None, "--molecule"),
    target_name: str = typer.Option("target", "--target-name"),
    batch_size: int = typer.Option(20, "--batch-size"),
    sample_only: bool = typer.Option(True, "--sample-only/--no-sample-only"),
    confirm: bool = typer.Option(False, "--confirm"),
    output: Optional[Path] = typer.Option(None, "--output"),
    gpus: Optional[str] = typer.Option(None, "--gpus"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Gated DiffDynamic generate (sample_only default; large batch needs --confirm)."""
    from masld_agent.platform.diffdynamic_tools import diffdynamic_generate

    payload = diffdynamic_generate(
        protein_path=str(protein),
        ligand_path=str(ligand),
        mode=mode,
        molecule_path=str(molecule) if molecule else None,
        target_name=target_name,
        batch_size=batch_size,
        sample_only=sample_only,
        confirm=confirm,
        output_dir=str(output) if output else None,
        gpus=gpus,
        dry_run=dry_run,
    )
    _json_print(payload)
    raise SystemExit(0 if payload.get("status") in {"ok", "dry_run"} else 1)


@app.command("diffdynamic-extract")
def cmd_diffdynamic_extract(
    pt: Path = typer.Option(..., "--pt"),
    vina_modes: str = typer.Option("none", "--vina-modes"),
    output: Optional[Path] = typer.Option(None, "--output"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    from masld_agent.platform.diffdynamic_tools import diffdynamic_extract

    payload = diffdynamic_extract(
        pt_path=str(pt),
        vina_modes=vina_modes,
        output_dir=str(output) if output else None,
        dry_run=dry_run,
    )
    _json_print(payload)
    raise SystemExit(0 if payload.get("status") in {"ok", "dry_run"} else 1)


@app.command("schrodinger-status")
def cmd_schrodinger_status() -> None:
    from masld_agent.platform.schrodinger_tools import schrodinger_status

    _json_print(schrodinger_status())


@app.command("schrodinger-dock")
def cmd_schrodinger_dock(
    receptor: Path = typer.Option(..., "--receptor"),
    smiles: Optional[list[str]] = typer.Option(None, "--smiles"),
    ligand_sdf: Optional[Path] = typer.Option(None, "--ligand-sdf"),
    precision: str = typer.Option("SP", "--precision"),
    confirm: bool = typer.Option(False, "--confirm"),
    output: Optional[Path] = typer.Option(None, "--output"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Small-scale Schrödinger SP dock (large/XP needs --confirm)."""
    from masld_agent.platform.schrodinger_tools import schrodinger_dock

    payload = schrodinger_dock(
        receptor_pdb=str(receptor),
        smiles=smiles,
        ligand_sdf=str(ligand_sdf) if ligand_sdf else None,
        precision=precision,
        confirm=confirm,
        output_dir=str(output) if output else None,
        dry_run=dry_run,
    )
    _json_print(payload)
    raise SystemExit(0 if payload.get("status") in {"ok", "dry_run"} else 1)


@app.command("schrodinger-mmgbsa")
def cmd_schrodinger_mmgbsa(
    pose: Path = typer.Option(..., "--pose"),
    confirm: bool = typer.Option(False, "--confirm"),
    output: Optional[Path] = typer.Option(None, "--output"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    from masld_agent.platform.schrodinger_tools import schrodinger_mmgbsa

    payload = schrodinger_mmgbsa(
        pose_path=str(pose),
        confirm=confirm,
        output_dir=str(output) if output else None,
        dry_run=dry_run,
    )
    _json_print(payload)
    raise SystemExit(0 if payload.get("status") in {"ok", "dry_run"} else 1)


if __name__ == "__main__":
    app()
