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


@app.command("run")
def cmd_run(
    competition: Path = typer.Option(DEFAULT_COMPETITION, "--competition"),
    disease: DiseaseScope = typer.Option(DiseaseScope.MASLD, "--disease"),
    modality: str = typer.Option("small_molecule_inhibitor", "--modality"),
    top_targets: int = typer.Option(10, "--top-targets"),
    output: Path = typer.Option(PKG_ROOT / "runs" / "demo", "--output"),
    online: bool = typer.Option(False, "--online/--offline-panel"),
) -> None:
    """Run supervisor pipeline (fixtures + optional online literature)."""
    out = run_pipeline(
        output,
        competition_config=competition,
        disease=disease,
        modality=modality,
        top_targets=top_targets,
        online=online,
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
        "  hermes chat --provider volcengine-plan\n"
        "  hermes chat --provider volcano-anthropic\n"
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
