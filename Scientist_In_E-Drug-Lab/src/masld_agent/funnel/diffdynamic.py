"""Portable Prudent post-processing with Vina execution disabled."""
from __future__ import annotations

import csv
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import yaml

from masld_agent.funnel.manifest import campaign_root, load_manifest, resolve_campaign_path, stage_config
from masld_agent.platform.gates import GateError, require_diffdynamic_inputs
from masld_agent.platform.paths import DIFFDYNAMIC_CONDA, DIFFDYNAMIC_ROOT


def _configured_path(manifest: dict[str, Any], value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else resolve_campaign_path(manifest, path)


def prudent_generate(
    manifest_path: str | Path,
    *,
    execute: bool = False,
    confirm: bool = False,
) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    config = stage_config(manifest, "H1B")
    target_value = config.get("target_count") or (manifest.get("pipeline_targets") or {}).get("H1B")
    if target_value is None:
        return {
            "status": "blocked",
            "error": "manifest must declare stages.H1B.target_count or pipeline_targets.H1B",
        }
    target_count = int(target_value)
    template_value = config.get("config_template") or (manifest.get("reused_assets") or {}).get(
        "prudent_config_template"
    )
    if not template_value:
        return {
            "status": "blocked",
            "error": "manifest must declare stages.H1B.config_template or reused_assets.prudent_config_template",
        }
    template = _configured_path(manifest, template_value)
    inputs = manifest.get("inputs") or {}
    receptor = resolve_campaign_path(manifest, inputs.get("receptor_pdb") or "")
    ligand = resolve_campaign_path(manifest, inputs.get("reference_ligand_sdf") or "")
    python = _configured_path(
        manifest,
        config.get("diffdynamic_python") or DIFFDYNAMIC_CONDA / "bin" / "python",
    )
    sampler = _configured_path(
        manifest,
        config.get("sampler") or DIFFDYNAMIC_ROOT / "scripts" / "sample_diffusion.py",
    )
    output = resolve_campaign_path(manifest, config.get("generation_output_dir") or "diffdynamic/prudent/run")
    generated_config_dir = resolve_campaign_path(
        manifest, config.get("generated_config_dir") or "configs"
    )
    generated_config = generated_config_dir / f"prudent_target_{target_count}.yml"
    for label, path in (
        ("template", template),
        ("receptor", receptor),
        ("reference ligand", ligand),
        ("DiffDynamic Python", python),
        ("sampler", sampler),
    ):
        if not path.is_file():
            return {"status": "blocked", "error": f"{label} not found: {path}"}
    try:
        require_diffdynamic_inputs(protein_path=receptor, ligand_path=ligand)
    except GateError as exc:
        return {"status": "blocked", "error": str(exc)}
    try:
        existing_pt = select_prudent_pt(manifest)
    except FileNotFoundError:
        existing_pt = None
    if existing_pt is not None:
        return {
            "status": "completed",
            "reused_existing": True,
            "pt": str(existing_pt),
            "target_count": target_count,
        }
    raw_config = yaml.safe_load(template.read_text(encoding="utf-8"))
    prudent = raw_config["sample"]["dynamic"]["prudent"]
    large_step = raw_config["sample"]["dynamic"]["large_step"]
    advance_top_k = int(prudent.get("advance_top_k") or 1)
    batch_size = max(1, (target_count + advance_top_k - 1) // advance_top_k)
    large_step["batch_size"] = batch_size
    raw_config["sample"]["seed"] = int(config.get("seed") or raw_config["sample"].get("seed") or 20260730)
    command = [
        str(python),
        "-u",
        str(sampler),
        str(generated_config),
        "--protein_path",
        str(receptor),
        "--protein_root",
        str(receptor.parent),
        "--ligand_path",
        str(ligand),
        "--result_path",
        str(output),
        "--device",
        "cuda:0",
        "--mode",
        "prudent",
    ]
    preview = {
        "argv": command,
        "target_count": target_count,
        "advance_top_k": advance_top_k,
        "large_step_batch_size": batch_size,
        "config_template": str(template),
        "generated_config": str(generated_config),
        "note": "Prudent internal selection is preserved; post-generation analysis uses Vina none.",
    }
    if not execute:
        return {"status": "dry_run", "command_preview": preview}
    if not confirm:
        return {"status": "gated", "error": "Prudent generation requires confirm=true", "command_preview": preview}
    generated_config.parent.mkdir(parents=True, exist_ok=True)
    generated_config.write_text(
        yaml.safe_dump(raw_config, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    output.mkdir(parents=True, exist_ok=True)
    log = output.parent / "prudent_generation.log"
    with log.open("w", encoding="utf-8") as stream:
        result = subprocess.run(
            command,
            cwd=DIFFDYNAMIC_ROOT,
            stdout=stream,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=int(config.get("generation_timeout_seconds") or 172_800),
            check=False,
        )
    if result.returncode:
        return {"status": "failed", "exit_code": result.returncode, "log": str(log), "command_preview": preview}
    try:
        pt_path = select_prudent_pt(manifest)
    except FileNotFoundError as exc:
        return {"status": "failed", "exit_code": 0, "error": str(exc), "log": str(log)}
    return {
        "status": "completed",
        "reused_existing": False,
        "pt": str(pt_path),
        "log": str(log),
        "command_preview": preview,
    }


def select_prudent_pt(manifest: dict[str, Any]) -> Path:
    config = stage_config(manifest, "H1B")
    explicit = config.get("pt_path")
    if explicit:
        path = resolve_campaign_path(manifest, explicit)
        if not path.is_file():
            raise FileNotFoundError(f"configured Prudent PT not found: {path}")
        return path
    pattern = str(config.get("pt_glob") or "diffdynamic/prudent/run/result_custom*.pt")
    candidates = [path for path in campaign_root(manifest).glob(pattern) if path.is_file()]
    preferred = [
        path
        for path in candidates
        if not any(token in path.stem.lower() for token in ("_seed", "_chains", "_gen", "_full"))
    ]
    pool = preferred or candidates
    if not pool:
        raise FileNotFoundError(f"no Prudent PT matched campaign-relative glob: {pattern}")
    return sorted(pool, key=lambda path: (-path.stat().st_size, path.name))[0]


def build_physchem_command(manifest: dict[str, Any], pt_path: Path) -> tuple[list[str], Path]:
    config = stage_config(manifest, "H1B")
    inputs = manifest.get("inputs") or {}
    evaluator = _configured_path(
        manifest,
        config.get("evaluator")
        or (manifest.get("reused_assets") or {}).get("analysis_script")
        or DIFFDYNAMIC_ROOT / "evaluate_pt_with_correct_reconstruct.py",
    )
    python = _configured_path(
        manifest,
        config.get("diffdynamic_python") or DIFFDYNAMIC_CONDA / "bin" / "python",
    )
    receptor = resolve_campaign_path(manifest, inputs.get("receptor_pdb") or "")
    ligand = resolve_campaign_path(manifest, inputs.get("reference_ligand_sdf") or "")
    for label, path in (
        ("Prudent PT", pt_path),
        ("evaluator", evaluator),
        ("DiffDynamic Python", python),
        ("receptor", receptor),
        ("reference ligand", ligand),
    ):
        if not path.is_file():
            raise FileNotFoundError(f"{label} not found: {path}")
    require_diffdynamic_inputs(protein_path=receptor, ligand_path=ligand)
    output = resolve_campaign_path(
        manifest,
        config.get("physchem_output_dir") or "diffdynamic/prudent/physchem_no_vina",
    )
    command = [
        str(python),
        str(evaluator),
        str(pt_path),
        "--output_dir",
        str(output),
        "--protein_root",
        str(receptor.parent),
        "--receptor_pdb",
        str(receptor),
        "--reference_ligand",
        str(ligand),
        "--vina-modes",
        "none",
        "--enable_isolation",
        "--save_intermediate_interval",
        str(int(config.get("save_intermediate_interval") or 16)),
    ]
    return command, output


def deduplicate_physchem_sdf(source_root: Path, output_root: Path) -> dict[str, Any]:
    from rdkit import Chem
    from rdkit.Chem import Crippen, Descriptors, QED

    sdf_paths = sorted(source_root.rglob("*.sdf"))
    unique_dir = output_root / "unique_sdf"
    unique_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    seen = set()
    invalid = 0
    duplicates = 0
    for source in sdf_paths:
        supplier = Chem.SDMolSupplier(str(source), removeHs=False)
        molecule = next((item for item in supplier if item is not None), None)
        if molecule is None:
            invalid += 1
            continue
        canonical = Chem.MolToSmiles(molecule, canonical=True, isomericSmiles=False)
        if not canonical:
            invalid += 1
            continue
        if canonical in seen:
            duplicates += 1
            continue
        seen.add(canonical)
        molecule_id = molecule.GetProp("_Name").strip() if molecule.HasProp("_Name") else source.stem
        molecule_id = molecule_id or source.stem
        destination = unique_dir / f"{len(rows) + 1:05d}_{source.name}"
        shutil.copy2(source, destination)
        rows.append(
            {
                "molecule_id": molecule_id,
                "canonical_smiles": canonical,
                "source_sdf": str(source),
                "unique_sdf": str(destination),
                "QED": molecule.GetProp("QED") if molecule.HasProp("QED") else f"{QED.qed(molecule):.6f}",
                "SA": molecule.GetProp("SA") if molecule.HasProp("SA") else "",
                "MW": f"{Descriptors.MolWt(molecule):.6f}",
                "LogP": f"{Crippen.MolLogP(molecule):.6f}",
                "TPSA": f"{Descriptors.TPSA(molecule):.6f}",
            }
        )
    output_root.mkdir(parents=True, exist_ok=True)
    csv_path = output_root / "unique.csv"
    fields = ["molecule_id", "canonical_smiles", "source_sdf", "unique_sdf", "QED", "SA", "MW", "LogP", "TPSA"]
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return {
        "source_sdf_files": len(sdf_paths),
        "valid_unique": len(rows),
        "duplicates": duplicates,
        "invalid": invalid,
        "unique_csv": str(csv_path),
        "unique_sdf_dir": str(unique_dir),
    }


def prudent_physchem(
    manifest_path: str | Path,
    *,
    execute: bool = False,
    confirm: bool = False,
) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    try:
        pt_path = select_prudent_pt(manifest)
        command, output = build_physchem_command(manifest, pt_path)
    except (FileNotFoundError, GateError) as exc:
        return {"status": "blocked", "error": str(exc)}
    preview = {
        "argv": command,
        "pt_selected_by": "explicit path or largest preferred aggregate PT",
        "vina_modes": "none",
        "vina_executed": False,
        "next_stage": "H2 Glide SP after canonical dedup",
    }
    if not execute:
        return {"status": "dry_run", "command_preview": preview, "output_dir": str(output)}
    if not confirm:
        return {"status": "gated", "error": "Prudent analysis requires confirm=true", "command_preview": preview}
    output.mkdir(parents=True, exist_ok=True)
    log = output / "physchem_no_vina.log"
    with log.open("w", encoding="utf-8") as stream:
        result = subprocess.run(
            command,
            cwd=DIFFDYNAMIC_ROOT,
            stdout=stream,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=int(stage_config(manifest, "H1B").get("physchem_timeout_seconds") or 14_400),
            check=False,
        )
    if result.returncode:
        return {
            "status": "failed",
            "exit_code": result.returncode,
            "log": str(log),
            "command_preview": preview,
        }
    dedup_root = resolve_campaign_path(
        manifest, stage_config(manifest, "H1B").get("dedup_output_dir") or "dedup"
    )
    dedup = deduplicate_physchem_sdf(output, dedup_root)
    status = "completed" if dedup["valid_unique"] > 0 else "failed"
    report = {
        "status": status,
        "exit_code": result.returncode,
        "log": str(log),
        "output_dir": str(output),
        "vina_executed": False,
        "vina_modes": "none",
        "dedup": dedup,
        "command_preview": preview,
    }
    (output / "physchem_summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report
