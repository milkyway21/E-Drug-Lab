"""Hermes plugin registration (official plugin surface — does not modify Hermes core)."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from masld_agent.paths import UnsafePathError, resolve_under

logger = logging.getLogger(__name__)

PKG_ROOT = Path(__file__).resolve().parents[2]


def _run_offline(args: dict, **kwargs) -> str:
    from masld_agent.supervisor import run_offline_demo

    try:
        fixture = resolve_under(
            PKG_ROOT,
            args.get("fixture"),
            default=PKG_ROOT / "tests/fixtures/hsd17b13",
        )
        output = resolve_under(
            PKG_ROOT,
            args.get("output"),
            default=PKG_ROOT / "runs",
        )
    except UnsafePathError as exc:
        return json.dumps({"status": "error", "error": str(exc)})
    out = run_offline_demo(fixture, output)
    return json.dumps({"status": "ok", "output_dir": str(out)})


def _run_pipeline(args: dict, **kwargs) -> str:
    from masld_agent.models import DiseaseScope
    from masld_agent.supervisor import run_pipeline

    try:
        disease = DiseaseScope(args.get("disease", "MASLD"))
        output = resolve_under(
            PKG_ROOT,
            args.get("output"),
            default=PKG_ROOT / "runs" / "demo",
        )
    except (UnsafePathError, ValueError) as exc:
        return json.dumps({"status": "error", "error": str(exc)})
    online = bool(args.get("online", False))
    top = int(args.get("top_targets", 10))
    out = run_pipeline(output, disease=disease, top_targets=top, online=online)
    return json.dumps({"status": "ok", "output_dir": str(out), "online": online})


def _competition_brief(args: dict, **kwargs) -> str:
    from masld_agent.tools.ai4s_brief import format_competition_brief, load_ai4s_config

    return format_competition_brief(load_ai4s_config())


def _validate_submission(args: dict, **kwargs) -> str:
    from masld_agent.submission import validate_submission, write_validation_report

    try:
        run_dir = resolve_under(
            PKG_ROOT,
            args.get("run_dir"),
            default=PKG_ROOT / "runs",
        )
        top10 = args.get("top10_csv")
        top10_path = (
            resolve_under(PKG_ROOT, top10, default=run_dir / "top10_nomination.csv")
            if top10
            else None
        )
    except UnsafePathError as exc:
        return json.dumps({"status": "error", "error": str(exc)})
    result = validate_submission(run_dir, top10_csv=top10_path)
    write_validation_report(run_dir, result)
    return json.dumps({"status": "ok", **result}, default=str)


def _pack_submission(args: dict, **kwargs) -> str:
    from masld_agent.submission import pack_submission

    try:
        run_dir = resolve_under(
            PKG_ROOT,
            args.get("run_dir"),
            default=PKG_ROOT / "runs",
        )
        output = resolve_under(
            PKG_ROOT,
            args.get("output"),
            default=run_dir / "submission" / "ai4s_bundle.zip",
        )
    except UnsafePathError as exc:
        return json.dumps({"status": "error", "error": str(exc)})
    path = pack_submission(run_dir, output)
    return json.dumps({"status": "ok", "zip": str(path)})


def _platform_catalog(args: dict, **kwargs) -> str:
    from masld_agent.platform.catalog import get_entry, list_entries, summarize_systems

    entry_id = (args.get("id") or args.get("entry_id") or "").strip()
    if entry_id:
        e = get_entry(entry_id)
        return json.dumps({"status": "ok" if e else "error", "entry": e}, default=str)
    entries = list_entries(
        system=(args.get("system") or None) or None,
        stage=(args.get("stage") or None) or None,
    )
    return json.dumps(
        {"status": "ok", "summary": summarize_systems(), "entries": entries},
        default=str,
    )


def _platform_health(args: dict, **kwargs) -> str:
    from masld_agent.platform.health import platform_health

    return json.dumps(platform_health(), default=str)


def _diffdynamic_status(args: dict, **kwargs) -> str:
    from masld_agent.platform.diffdynamic_tools import diffdynamic_status

    return json.dumps(diffdynamic_status(), default=str)


def _diffdynamic_generate(args: dict, **kwargs) -> str:
    from masld_agent.platform.diffdynamic_tools import diffdynamic_generate

    return json.dumps(
        diffdynamic_generate(
            protein_path=str(args.get("protein_path") or ""),
            ligand_path=str(args.get("ligand_path") or ""),
            mode=str(args.get("mode") or "denovo_fast"),
            molecule_path=args.get("molecule_path") or None,
            batch_size=int(args.get("batch_size") or 20),
            sample_only=bool(args.get("sample_only", True)),
            confirm=bool(args.get("confirm", False)),
            dry_run=bool(args.get("dry_run", True)),
            output_dir=args.get("output_dir") or None,
            gpus=args.get("gpus") or None,
        ),
        default=str,
    )


def _diffdynamic_extract(args: dict, **kwargs) -> str:
    from masld_agent.platform.diffdynamic_tools import diffdynamic_extract

    return json.dumps(
        diffdynamic_extract(
            pt_path=str(args.get("pt_path") or ""),
            vina_modes=str(args.get("vina_modes") or "none"),
            output_dir=args.get("output_dir") or None,
            dry_run=bool(args.get("dry_run", True)),
        ),
        default=str,
    )


def _schrodinger_status(args: dict, **kwargs) -> str:
    from masld_agent.platform.schrodinger_tools import schrodinger_status

    return json.dumps(schrodinger_status(), default=str)


def _schrodinger_dock(args: dict, **kwargs) -> str:
    from masld_agent.platform.schrodinger_tools import schrodinger_dock

    smiles = args.get("smiles")
    if isinstance(smiles, str):
        smiles = [s.strip() for s in smiles.split(",") if s.strip()]
    return json.dumps(
        schrodinger_dock(
            receptor_pdb=str(args.get("receptor_pdb") or ""),
            smiles=smiles,
            ligand_sdf=args.get("ligand_sdf") or None,
            precision=str(args.get("precision") or "SP"),
            confirm=bool(args.get("confirm", False)),
            dry_run=bool(args.get("dry_run", True)),
            output_dir=args.get("output_dir") or None,
        ),
        default=str,
    )


def _schrodinger_mmgbsa(args: dict, **kwargs) -> str:
    from masld_agent.platform.schrodinger_tools import schrodinger_mmgbsa

    return json.dumps(
        schrodinger_mmgbsa(
            pose_path=str(args.get("pose_path") or ""),
            confirm=bool(args.get("confirm", False)),
            dry_run=bool(args.get("dry_run", True)),
            output_dir=args.get("output_dir") or None,
        ),
        default=str,
    )


OFFLINE_SCHEMA = {
    "name": "masld_offline_demo",
    "description": (
        "Run Scientist_In_E-Drug-Lab offline demo (example fixtures HSD17B13/KHK) "
        "producing proposal/method artifacts. No network. Includes competition_scope_warning "
        "when used under AI4S competition config."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "fixture": {"type": "string", "description": "Path to fixture directory"},
            "output": {"type": "string", "description": "Output runs directory"},
        },
        "required": [],
    },
}

RUN_SCHEMA = {
    "name": "masld_run_pipeline",
    "description": (
        "Run target-hypothesis supervisor (AI4S competition preset supports MASLD/HCC). "
        "Prefer offline fixtures; set online=true to fetch literature. "
        "Does not nominate official-library Top10 compounds (C1)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "disease": {"type": "string", "enum": ["MASLD", "HCC"]},
            "top_targets": {"type": "integer"},
            "online": {"type": "boolean"},
            "output": {"type": "string"},
        },
        "required": [],
    },
}

BRIEF_SCHEMA = {
    "name": "masld_competition_brief",
    "description": (
        "Print AI4S life-science track brief: dual readout, scoring 60/20/20, "
        "submission artifacts, resources. Does not change agent identity (SOUL)."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}

VALIDATE_SCHEMA = {
    "name": "masld_validate_submission",
    "description": (
        "Validate a run directory against AI4S submission checklist "
        "(proposal/method, dual readout, Top10 CSV). Marks pending_library_nomination if needed."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "run_dir": {"type": "string"},
            "top10_csv": {"type": "string"},
        },
        "required": [],
    },
}

PACK_SCHEMA = {
    "name": "masld_pack_submission",
    "description": "Pack run artifacts + AI4S checklist/template into a zip bundle.",
    "parameters": {
        "type": "object",
        "properties": {
            "run_dir": {"type": "string"},
            "output": {"type": "string"},
        },
        "required": [],
    },
}

CATALOG_SCHEMA = {
    "name": "platform_catalog",
    "description": (
        "Query authoritative DiffDynamic / e-drug-lab / Schrödinger capability catalog "
        "(by system dd|ed|sz or id). Call before compute. Never invent scores."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "system": {"type": "string", "description": "dd|ed|sz"},
            "id": {"type": "string"},
            "stage": {"type": "string"},
        },
        "required": [],
    },
}

HEALTH_SCHEMA = {
    "name": "platform_health",
    "description": "Probe DiffDynamic conda/root, e-drug-lab backend import, Schrödinger install.",
    "parameters": {"type": "object", "properties": {}, "required": []},
}

DD_STATUS_SCHEMA = {
    "name": "diffdynamic_status",
    "description": "DiffDynamic + DiffDynamicRunner status (catalog dd.env / ed.svc.diffdynamic).",
    "parameters": {"type": "object", "properties": {}, "required": []},
}

DD_GEN_SCHEMA = {
    "name": "diffdynamic_generate",
    "description": (
        "Gated DiffDynamic generate via e-drug-lab DiffDynamicRunner. "
        "Requires protein_path+ligand_path; sample_only default true; "
        "batch_size>=100 needs confirm=true. Prefer dry_run=true first."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "protein_path": {"type": "string"},
            "ligand_path": {"type": "string"},
            "mode": {"type": "string"},
            "molecule_path": {"type": "string"},
            "batch_size": {"type": "integer"},
            "sample_only": {"type": "boolean"},
            "confirm": {"type": "boolean"},
            "dry_run": {"type": "boolean"},
            "output_dir": {"type": "string"},
            "gpus": {"type": "string"},
        },
        "required": ["protein_path", "ligand_path"],
    },
}

DD_EXTRACT_SCHEMA = {
    "name": "diffdynamic_extract",
    "description": "Extract .pt → SDF via DiffDynamicRunner.extract_pt (catalog dd.script.extract).",
    "parameters": {
        "type": "object",
        "properties": {
            "pt_path": {"type": "string"},
            "vina_modes": {"type": "string"},
            "output_dir": {"type": "string"},
            "dry_run": {"type": "boolean"},
        },
        "required": ["pt_path"],
    },
}

SZ_STATUS_SCHEMA = {
    "name": "schrodinger_status",
    "description": "Schrödinger install + schrodinger_service.local_health.",
    "parameters": {"type": "object", "properties": {}, "required": []},
}

SZ_DOCK_SCHEMA = {
    "name": "schrodinger_dock",
    "description": (
        "Gated Schrödinger Glide via e-drug-lab (default SP, small ligand set). "
        ">20 ligands or XP needs confirm=true. Prefer dry_run=true first. Never invent scores."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "receptor_pdb": {"type": "string"},
            "smiles": {"type": "string", "description": "Comma-separated SMILES"},
            "ligand_sdf": {"type": "string"},
            "precision": {"type": "string"},
            "confirm": {"type": "boolean"},
            "dry_run": {"type": "boolean"},
            "output_dir": {"type": "string"},
        },
        "required": ["receptor_pdb"],
    },
}

SZ_MMGBSA_SCHEMA = {
    "name": "schrodinger_mmgbsa",
    "description": "Prime MM-GBSA on Glide pose (_pv.maegz). Requires confirm=true.",
    "parameters": {
        "type": "object",
        "properties": {
            "pose_path": {"type": "string"},
            "confirm": {"type": "boolean"},
            "dry_run": {"type": "boolean"},
            "output_dir": {"type": "string"},
        },
        "required": ["pose_path"],
    },
}


def register(ctx):
    """Hermes plugin entry: ctx.register_tool / register_command / register_cli_command."""
    tools = [
        ("masld_offline_demo", OFFLINE_SCHEMA, _run_offline),
        ("masld_run_pipeline", RUN_SCHEMA, _run_pipeline),
        ("masld_competition_brief", BRIEF_SCHEMA, _competition_brief),
        ("masld_validate_submission", VALIDATE_SCHEMA, _validate_submission),
        ("masld_pack_submission", PACK_SCHEMA, _pack_submission),
        ("platform_catalog", CATALOG_SCHEMA, _platform_catalog),
        ("platform_health", HEALTH_SCHEMA, _platform_health),
        ("diffdynamic_status", DD_STATUS_SCHEMA, _diffdynamic_status),
        ("diffdynamic_generate", DD_GEN_SCHEMA, _diffdynamic_generate),
        ("diffdynamic_extract", DD_EXTRACT_SCHEMA, _diffdynamic_extract),
        ("schrodinger_status", SZ_STATUS_SCHEMA, _schrodinger_status),
        ("schrodinger_dock", SZ_DOCK_SCHEMA, _schrodinger_dock),
        ("schrodinger_mmgbsa", SZ_MMGBSA_SCHEMA, _schrodinger_mmgbsa),
    ]
    try:
        for name, schema, handler in tools:
            ctx.register_tool(
                name=name,
                toolset="scientist_in_e_drug_lab",
                schema=schema,
                handler=handler,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Hermes register_tool failed (running outside Hermes?): %s", exc)

    def _slash_offline(raw: str = ""):
        return _run_offline({"fixture": raw.strip() or None})

    try:
        ctx.register_command(
            "masld-offline",
            lambda raw: _slash_offline(raw),
            description="Run offline demo (example AI4S fixtures)",
        )
        ctx.register_command(
            "masld-brief",
            lambda raw: _competition_brief({}),
            description="AI4S life-science competition brief",
        )
        ctx.register_command(
            "platform-health",
            lambda raw: _platform_health({}),
            description="Probe DiffDynamic / e-drug-lab / Schrödinger health",
        )
        ctx.register_command(
            "platform-catalog",
            lambda raw: _platform_catalog({"system": raw.strip()} if raw.strip() else {}),
            description="Query platform capability catalog (optional system dd|ed|sz)",
        )
    except Exception as exc:  # noqa: BLE001
        logger.debug("register_command unavailable: %s", exc)

    try:
        skill_root = PKG_ROOT / "skills" / "scientist-in-e-drug-lab"
        if hasattr(ctx, "register_skill") and skill_root.exists():
            # Parent orchestrator + nested hsv-00…07 stage skills
            ctx.register_skill(str(skill_root))
            for child in sorted(skill_root.iterdir()):
                if child.is_dir() and (child / "SKILL.md").is_file():
                    ctx.register_skill(str(child))
    except Exception as exc:  # noqa: BLE001
        logger.debug("register_skill skipped: %s", exc)

    logger.info("scientist_in_e_drug_lab plugin registered")
