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
        library = (
            resolve_under(PKG_ROOT, args.get("library"))
            if args.get("library")
            else None
        )
    except (UnsafePathError, ValueError) as exc:
        return json.dumps({"status": "error", "error": str(exc)})
    online = bool(args.get("online", False))
    top = int(args.get("top_targets", 10))
    out = run_pipeline(
        output,
        disease=disease,
        top_targets=top,
        online=online,
        offline_replay=bool(args.get("offline_replay", False)),
        library_path=library,
        final_count=int(args.get("final_count") or 10),
        target_gene=str(args.get("target_gene") or "").strip() or None,
        evidence_profile=str(args.get("evidence_profile") or "generic"),
        online_enrichment_limit=int(args.get("online_enrichment_limit") or 50),
        library_source=str(args.get("library_source") or "official_sdf_library"),
    )
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


def _target_biology_search(args: dict, **kwargs) -> str:
    from masld_agent.evidence_pipeline import build_target_evidence_card
    from masld_agent.http_cache import CachedHttp

    gene = str(args.get("gene") or "").strip()
    if not gene:
        return json.dumps({"status": "error", "error": "gene is required"})
    card = build_target_evidence_card(
        gene,
        str(args.get("disease") or "MASLD"),
        online=bool(args.get("online", True)) or bool(args.get("offline_replay", False)),
        http=CachedHttp(cache_only=bool(args.get("offline_replay", False))),
    )
    return card.model_dump_json(indent=2)


def _structure_search_rank(args: dict, **kwargs) -> str:
    from masld_agent.http_cache import CachedHttp
    from masld_agent.tools.pdb import discover_structure_candidates

    gene = str(args.get("gene") or "").strip() or None
    uniprot = str(args.get("uniprot_id") or "").strip() or None
    if not gene and not uniprot:
        return json.dumps({"status": "error", "error": "gene or uniprot_id is required"})
    structures = discover_structure_candidates(
        gene=gene,
        uniprot_id=uniprot,
        limit=int(args.get("limit") or 25),
        http=CachedHttp(cache_only=bool(args.get("offline_replay", False))),
    )
    return json.dumps(
        {"status": "ok", "structures": [item.model_dump(mode="json") for item in structures]},
        ensure_ascii=False,
        default=str,
    )


def _pocket_qualify(args: dict, **kwargs) -> str:
    from masld_agent.models import StructureCandidate
    from masld_agent.tools.pdb import qualify_pocket

    structure_data = args.get("structure")
    structure = (
        StructureCandidate.model_validate(structure_data)
        if isinstance(structure_data, dict)
        else None
    )
    result = qualify_pocket(
        structure,
        target_gene=str(args.get("target_gene") or "phenotype_first"),
        key_residues=list(args.get("key_residues") or []),
        evidence_basis=list(args.get("evidence_basis") or []),
        mechanism_is_target_based=bool(args.get("mechanism_is_target_based", True)),
    )
    return result.model_dump_json(indent=2)


def _compound_evidence_enrich(args: dict, **kwargs) -> str:
    from masld_agent.tools.compound_evidence import dump_cards_jsonl, load_compound_library

    try:
        library = resolve_under(PKG_ROOT, args.get("library"))
        output = resolve_under(
            PKG_ROOT,
            args.get("output"),
            default=PKG_ROOT / "runs" / "evidence" / "compound_evidence.jsonl",
        )
    except UnsafePathError as exc:
        return json.dumps({"status": "error", "error": str(exc)})
    cards = load_compound_library(
        library,
        library_source=str(args.get("library_source") or "official_sdf_library"),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    dump_cards_jsonl(cards, output)
    return json.dumps({"status": "ok", "records": len(cards), "output": str(output)})


def _toxicity_triage(args: dict, **kwargs) -> str:
    from masld_agent.models import CompoundEvidenceCard

    try:
        evidence_path = resolve_under(PKG_ROOT, args.get("compound_evidence"))
    except UnsafePathError as exc:
        return json.dumps({"status": "error", "error": str(exc)})
    cards = [
        CompoundEvidenceCard.model_validate_json(line)
        for line in evidence_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    summary = [
        {
            "library_id": card.library_id,
            "safety_score": card.score.safety,
            "observed": sum(item.observed for item in card.safety_evidence),
            "predicted": sum(item.prediction for item in card.safety_evidence),
            "status": (
                "observed"
                if any(item.observed for item in card.safety_evidence)
                else "predicted_only"
                if any(item.prediction for item in card.safety_evidence)
                else "unknown"
            ),
            "rationale": card.toxicity_rationale,
        }
        for card in cards
    ]
    return json.dumps({"status": "ok", "toxicity": summary}, ensure_ascii=False)


def _nominate_compounds(args: dict, **kwargs) -> str:
    from masld_agent.evidence_pipeline import run_evidence_nomination

    try:
        library = resolve_under(PKG_ROOT, args.get("library"))
        output = resolve_under(
            PKG_ROOT,
            args.get("output"),
            default=PKG_ROOT / "runs" / "evidence",
        )
    except UnsafePathError as exc:
        return json.dumps({"status": "error", "error": str(exc)})
    result = run_evidence_nomination(
        library,
        output,
        final_count=int(args.get("final_count") or 10),
        disease=str(args.get("disease") or "MASLD"),
        target_gene=str(args.get("target_gene") or "").strip() or None,
        online=bool(args.get("online", False)),
        offline_replay=bool(args.get("offline_replay", False)),
        online_enrichment_limit=int(args.get("online_enrichment_limit") or 50),
        library_source=str(args.get("library_source") or "official_sdf_library"),
        mechanism_is_target_based=bool(args.get("mechanism_is_target_based", True)),
    )
    return json.dumps({"status": "completed", "output_dir": str(result)})


def _build_validation_report(args: dict, **kwargs) -> str:
    from masld_agent.submission import validate_submission, write_hepg2_plan, write_validation_report

    try:
        run_dir = resolve_under(PKG_ROOT, args.get("run_dir"), default=PKG_ROOT / "runs")
    except UnsafePathError as exc:
        return json.dumps({"status": "error", "error": str(exc)})
    write_hepg2_plan(run_dir)
    result = validate_submission(run_dir)
    report = write_validation_report(run_dir, result)
    return json.dumps(
        {"status": "ok" if result["ok"] else "incomplete", "report": str(report), **result},
        ensure_ascii=False,
        default=str,
    )


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


def _schrodinger_md_submit(args: dict, **kwargs) -> str:
    from masld_agent.platform.schrodinger_md_tools import schrodinger_md_submit

    return json.dumps(
        schrodinger_md_submit(
            structure_path=args.get("structure_path") or None,
            mode=str(args.get("mode") or "dry_prep"),
            confirm=bool(args.get("confirm", False)),
            simulation_time_ns=args.get("simulation_time_ns"),
            host=args.get("host") or None,
            molecule_id=args.get("molecule_id") or None,
            target_id=args.get("target_id") or None,
            api_base=args.get("api_base") or None,
        ),
        default=str,
    )


def _schrodinger_md_status(args: dict, **kwargs) -> str:
    from masld_agent.platform.schrodinger_md_tools import schrodinger_md_status

    return json.dumps(
        schrodinger_md_status(
            task_id=str(args.get("task_id") or ""),
            target_id=args.get("target_id") or None,
            api_base=args.get("api_base") or None,
        ),
        default=str,
    )


def _funnel_plan(args: dict, **kwargs) -> str:
    from masld_agent.funnel.planner import plan_campaign

    result = plan_campaign(
        int(args.get("final_count") or 0),
        manifest_path=args.get("manifest") or None,
        target_id=args.get("target_id") or None,
        profile=str(args.get("profile") or "full"),
        write=True,
    )
    return json.dumps(result, ensure_ascii=False, default=str)


def _funnel_preflight(args: dict, **kwargs) -> str:
    from masld_agent.funnel.planner import resolve_manifest
    from masld_agent.funnel.runner import preflight_campaign

    manifest = resolve_manifest(args.get("manifest") or None, target_id=args.get("target_id"))
    return json.dumps(preflight_campaign(manifest), ensure_ascii=False, default=str)


def _funnel_run_stage(args: dict, **kwargs) -> str:
    from masld_agent.funnel.planner import resolve_manifest
    from masld_agent.funnel.runner import run_stage

    manifest = resolve_manifest(args.get("manifest") or None, target_id=args.get("target_id"))
    result = run_stage(
        manifest,
        str(args.get("stage") or ""),
        execute=bool(args.get("execute", False)),
        confirm=bool(args.get("confirm", False)),
    )
    return json.dumps(result, ensure_ascii=False, default=str)


def _funnel_validate_stage(args: dict, **kwargs) -> str:
    from masld_agent.funnel.planner import resolve_manifest
    from masld_agent.funnel.runner import validate_stage

    manifest = resolve_manifest(args.get("manifest") or None, target_id=args.get("target_id"))
    return json.dumps(
        validate_stage(manifest, str(args.get("stage") or "")),
        ensure_ascii=False,
        default=str,
    )


def _funnel_status(args: dict, **kwargs) -> str:
    from masld_agent.funnel.planner import resolve_manifest
    from masld_agent.funnel.runner import stage_status

    manifest = resolve_manifest(args.get("manifest") or None, target_id=args.get("target_id"))
    return json.dumps(stage_status(manifest), ensure_ascii=False, default=str)


def _funnel_autopilot(args: dict, **kwargs) -> str:
    from masld_agent.funnel.autopilot import run_autopilot, start_autopilot

    execute = bool(args.get("execute", False))
    background = bool(args.get("background", True))
    if execute and background:
        result = start_autopilot(
            int(args.get("final_count") or 0),
            manifest_path=args.get("manifest") or None,
            target_id=args.get("target_id") or None,
            profile=str(args.get("profile") or "full"),
            confirm=bool(args.get("confirm", False)),
        )
    else:
        result = run_autopilot(
            int(args.get("final_count") or 0),
            manifest_path=args.get("manifest") or None,
            target_id=args.get("target_id") or None,
            profile=str(args.get("profile") or "full"),
            execute=execute,
            confirm=bool(args.get("confirm", False)),
        )
    return json.dumps(result, ensure_ascii=False, default=str)


def _funnel_autopilot_status(args: dict, **kwargs) -> str:
    from masld_agent.funnel.autopilot import autopilot_status

    result = autopilot_status(
        manifest_path=args.get("manifest") or None,
        target_id=args.get("target_id") or None,
    )
    return json.dumps(result, ensure_ascii=False, default=str)


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
        "Run target-hypothesis discovery when no library is supplied, or the complete E0-E6 "
        "evidence nomination workflow for an official SDF/CSV/SMI library. Set online=true "
        "for verified public-source enrichment; structure docking remains conditional."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "disease": {"type": "string", "enum": ["MASLD", "HCC"]},
            "top_targets": {"type": "integer"},
            "online": {"type": "boolean"},
            "offline_replay": {"type": "boolean"},
            "output": {"type": "string"},
            "library": {"type": "string"},
            "final_count": {"type": "integer", "minimum": 1},
            "target_gene": {"type": "string"},
            "evidence_profile": {"type": "string", "enum": ["generic", "competition"]},
            "online_enrichment_limit": {"type": "integer", "minimum": 0},
            "library_source": {"type": "string"},
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

TARGET_BIOLOGY_SCHEMA = {
    "name": "target_biology_search",
    "description": (
        "E1 mandatory biology reconnaissance for target-based discovery. Resolve the human gene, "
        "retrieve target-disease literature, Open Targets associations, and Reactome pathways. "
        "Call before structure or pocket selection; preserve missing and opposing evidence."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "gene": {"type": "string"},
            "disease": {"type": "string"},
            "online": {"type": "boolean"},
            "offline_replay": {"type": "boolean"},
        },
        "required": ["gene"],
    },
}

STRUCTURE_SEARCH_SCHEMA = {
    "name": "structure_search_rank",
    "description": (
        "E2 search and rank experimental RCSB structures by target identity, organism, ligand, "
        "resolution, and construct quality. Call after target_biology_search and before pocket_qualify."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "gene": {"type": "string"},
            "uniprot_id": {"type": "string"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            "offline_replay": {"type": "boolean"},
        },
        "required": [],
    },
}

POCKET_QUALIFY_SCHEMA = {
    "name": "pocket_qualify",
    "description": (
        "E3 decide whether structure docking is applicable and evidence-supported. Requires a ranked "
        "structure plus ligand, residue, cofactor, or literature support; never invent a blind pocket."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "target_gene": {"type": "string"},
            "structure": {"type": "object"},
            "key_residues": {"type": "array", "items": {"type": "string"}},
            "evidence_basis": {"type": "array", "items": {"type": "string"}},
            "mechanism_is_target_based": {"type": "boolean"},
        },
        "required": ["target_gene"],
    },
}

COMPOUND_ENRICH_SCHEMA = {
    "name": "compound_evidence_enrich",
    "description": (
        "E4 normalize an SDF/CSV/SMI library into exact parent identities, descriptors, evidence "
        "fields, structural-alert predictions, and explicit unknowns. Writes compound_evidence.jsonl."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "library": {"type": "string"},
            "output": {"type": "string"},
            "library_source": {"type": "string"},
        },
        "required": ["library"],
    },
}

TOXICITY_TRIAGE_SCHEMA = {
    "name": "toxicity_triage",
    "description": (
        "E5 summarize observed, predicted, and unknown toxicity evidence. Absence of evidence is "
        "never labeled low toxicity; structural alerts are predictions rather than observed effects."
    ),
    "parameters": {
        "type": "object",
        "properties": {"compound_evidence": {"type": "string"}},
        "required": ["compound_evidence"],
    },
}

NOMINATE_COMPOUNDS_SCHEMA = {
    "name": "nominate_compounds",
    "description": (
        "Run deterministic E0-E6 compound nomination from an official library. Produces target, "
        "structure, pocket, compound, toxicity, scorecard, Top-N, provenance, and mechanism reports. "
        "Use structure docking only when E3 qualifies it."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "library": {"type": "string"},
            "output": {"type": "string"},
            "final_count": {"type": "integer", "minimum": 1},
            "disease": {"type": "string"},
            "target_gene": {"type": "string"},
            "online": {"type": "boolean"},
            "online_enrichment_limit": {"type": "integer", "minimum": 0},
            "library_source": {"type": "string"},
            "mechanism_is_target_based": {"type": "boolean"},
        },
        "required": ["library"],
    },
}

BUILD_VALIDATION_REPORT_SCHEMA = {
    "name": "build_validation_report",
    "description": (
        "E6 rebuild the dual-readout validation plan and validate nomination/submission artifacts. "
        "Use after nominate_compounds or H10 comprehensive analysis."
    ),
    "parameters": {
        "type": "object",
        "properties": {"run_dir": {"type": "string"}},
        "required": ["run_dir"],
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

SZ_MD_SUBMIT_SCHEMA = {
    "name": "schrodinger_md_submit",
    "description": (
        "Schrödinger Desmond MD via e-drug-lab POST /api/v1/affinity/md. "
        "Default mode=dry_prep (prepare job_dir+msj, no production submit). "
        "mode=smoke|short requires confirm=true. Never treat stub as success. "
        "Appends memory/targets/<id>/MD_JOBS.jsonl. "
        "Production PASS needs cms+traj+md_summary+done; smoke gate ≠ production. "
        "Env: use $SCHRODINGER/multisim — do NOT conda create/activate for Desmond "
        "(conda 'diffdynamic' is DiffDynamic-only). "
        "Prefer skills funnel-desmond-short-md / funnel-desmond-long-md for task MD."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "structure_path": {"type": "string"},
            "mode": {"type": "string", "enum": ["dry_prep", "smoke", "short"]},
            "confirm": {"type": "boolean"},
            "simulation_time_ns": {"type": "number"},
            "host": {"type": "string"},
            "molecule_id": {"type": "string"},
            "target_id": {"type": "string"},
            "api_base": {"type": "string"},
        },
        "required": [],
    },
}

SZ_MD_STATUS_SCHEMA = {
    "name": "schrodinger_md_status",
    "description": "Poll Desmond MD task via GET /api/v1/affinity/md/{task_id}; append MD_JOBS.jsonl.",
    "parameters": {
        "type": "object",
        "properties": {
            "task_id": {"type": "string"},
            "target_id": {"type": "string"},
            "api_base": {"type": "string"},
        },
        "required": ["task_id"],
    },
}

FUNNEL_CONTEXT_PROPERTIES = {
    "manifest": {
        "type": "string",
        "description": "Optional absolute campaign manifest; otherwise resolve target session memory.",
    },
    "target_id": {"type": "string", "description": "Campaign target, default HSD17B13."},
}

FUNNEL_PROFILE_PROPERTY = {
    "profile": {
        "type": "string",
        "enum": ["full", "test"],
        "description": "Defaults to full. Use test only when the user explicitly requests a smoke/test run.",
    }
}

FUNNEL_PLAN_SCHEMA = {
    "name": "funnel_plan",
    "description": (
        "Given only the desired final molecule count, deterministically infer H0-H10 stage counts, "
        "inspect local CPU/GPU/disk resources, allocate free resources, and write a profile-specific plan."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "final_count": {"type": "integer", "minimum": 1},
            **FUNNEL_PROFILE_PROPERTY,
            **FUNNEL_CONTEXT_PROPERTIES,
        },
        "required": ["final_count"],
    },
}

FUNNEL_PREFLIGHT_SCHEMA = {
    "name": "funnel_preflight",
    "description": (
        "Read-only H0-H10 assets, environment, adapter, and existing-artifact preflight. "
        "ready_for_one_shot_execution must be true before production starts."
    ),
    "parameters": {"type": "object", "properties": FUNNEL_CONTEXT_PROPERTIES, "required": []},
}

FUNNEL_STAGE_SCHEMA = {
    "name": "funnel_run_stage",
    "description": (
        "Reuse valid outputs or run one configured H0-H10 stage. Preview by default; "
        "execution needs execute=true and compute also needs confirm=true."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "stage": {"type": "string", "enum": ["H0", "H1A", "H1B", "H2", "H3", "H4", "H5", "H6", "H7", "H8", "H9", "H10"]},
            "execute": {"type": "boolean"},
            "confirm": {"type": "boolean"},
            **FUNNEL_CONTEXT_PROPERTIES,
        },
        "required": ["stage"],
    },
}

FUNNEL_AUTOPILOT_STATUS_SCHEMA = {
    "name": "funnel_autopilot_status",
    "description": "Read persistent worker state and latest per-stage report. Poll this after background autopilot launch.",
    "parameters": {"type": "object", "properties": FUNNEL_CONTEXT_PROPERTIES, "required": []},
}

FUNNEL_VALIDATE_SCHEMA = {
    "name": "funnel_validate_stage",
    "description": "Hard-validate one stage from artifacts rather than chat claims or done markers.",
    "parameters": {
        "type": "object",
        "properties": {
            "stage": {"type": "string", "enum": ["H0", "H1A", "H1B", "H2", "H3", "H4", "H5", "H6", "H7", "H8", "H9", "H10"]},
            **FUNNEL_CONTEXT_PROPERTIES,
        },
        "required": ["stage"],
    },
}

FUNNEL_STATUS_SCHEMA = {
    "name": "funnel_status",
    "description": "Return hard-validation status and evidence for every H0-H10 stage.",
    "parameters": {"type": "object", "properties": FUNNEL_CONTEXT_PROPERTIES, "required": []},
}

FUNNEL_AUTOPILOT_SCHEMA = {
    "name": "funnel_autopilot",
    "description": (
        "PRIMARY WEAK-MODEL ENTRYPOINT. Given final_count only, plan all stage counts, allocate local "
        "resources, reuse valid artifacts, execute H0-H10 in order, stop on failed validation, and "
        "write JSON+Markdown report after every stage. Before any compute, all enabled stages are checked "
        "for a valid artifact or available argv adapter; missing readiness returns gated_preflight. "
        "Full is the default profile; test must be explicit. "
        "Preview/report mode is default. Set execute=true "
        "and confirm=true only after user authorizes production compute."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "final_count": {"type": "integer", "minimum": 1},
            **FUNNEL_PROFILE_PROPERTY,
            "execute": {"type": "boolean"},
            "confirm": {"type": "boolean"},
            "background": {
                "type": "boolean",
                "description": "For production, default true: launch persistent worker and return task state.",
            },
            **FUNNEL_CONTEXT_PROPERTIES,
        },
        "required": ["final_count"],
    },
}

MEMORY_READ_SCHEMA = {
    "name": "campaign_memory_read",
    "description": (
        "Read structured task memory: MAIN_PLAYBOOK, GLOBAL_HISTORY, CAMPAIGN.md "
        "(任务状态), DECISIONS tail, or session.json. Paths confined to memory/."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "section": {
                "type": "string",
                "enum": ["playbook", "global", "campaign", "decisions", "session"],
            },
            "target_id": {"type": "string"},
            "tail": {"type": "integer", "description": "DECISIONS lines from end"},
        },
        "required": ["section"],
    },
}

MEMORY_WRITE_SCHEMA = {
    "name": "campaign_memory_write",
    "description": "Update allowed CAMPAIGN.md (任务状态) metadata field or append DECISIONS row.",
    "parameters": {
        "type": "object",
        "properties": {
            "target_id": {"type": "string"},
            "action": {"type": "string", "enum": ["set_field", "append_decision"]},
            "field": {"type": "string"},
            "value": {"type": "string"},
            "stage": {"type": "string"},
            "decision": {"type": "string"},
            "summary": {"type": "string"},
            "evidence": {"type": "string"},
        },
        "required": ["target_id", "action"],
    },
}

GLOBAL_HISTORY_SCHEMA = {
    "name": "global_history_append",
    "description": "Append one line to memory/GLOBAL_HISTORY.md 任务摘要 section.",
    "parameters": {
        "type": "object",
        "properties": {"line": {"type": "string"}},
        "required": ["line"],
    },
}

UI_NAV_SCHEMA = {
    "name": "edrug_ui_navigate",
    "description": "Enqueue UI navigate command (whitelist paths). Separate from edrug_bridge compute.",
    "parameters": {
        "type": "object",
        "properties": {
            "session_id": {"type": "string"},
            "path": {"type": "string"},
        },
        "required": ["path"],
    },
}

UI_HIGHLIGHT_SCHEMA = {
    "name": "edrug_ui_highlight",
    "description": "Highlight entity in e-drug-lab web UI.",
    "parameters": {
        "type": "object",
        "properties": {
            "session_id": {"type": "string"},
            "entity_type": {"type": "string"},
            "entity_id": {"type": "string"},
        },
        "required": ["entity_type", "entity_id"],
    },
}

UI_OPEN_MOL_SCHEMA = {
    "name": "edrug_ui_open_molecule",
    "description": "Open molecule panel in workflow UI.",
    "parameters": {
        "type": "object",
        "properties": {
            "session_id": {"type": "string"},
            "molecule_id": {"type": "string"},
            "smiles": {"type": "string"},
        },
        "required": ["molecule_id"],
    },
}

UI_SET_TARGET_SCHEMA = {
    "name": "edrug_ui_set_target",
    "description": "Set current workflow target in web UI.",
    "parameters": {
        "type": "object",
        "properties": {
            "session_id": {"type": "string"},
            "target_id": {"type": "string"},
            "name": {"type": "string"},
        },
        "required": ["target_id"],
    },
}

UI_START_TASK_SCHEMA = {
    "name": "edrug_ui_start_task",
    "description": "Whitelist POST to existing backend domain APIs via UI bus.",
    "parameters": {
        "type": "object",
        "properties": {
            "session_id": {"type": "string"},
            "api_path": {"type": "string"},
            "body": {"type": "object"},
        },
        "required": ["api_path"],
    },
}


def _memory_read(args: dict, **kwargs) -> str:
    from masld_agent.memory_store import read_memory

    return json.dumps(
        read_memory(
            target_id=args.get("target_id"),
            section=str(args.get("section") or "campaign"),
            tail=int(args.get("tail") or 20),
        ),
        ensure_ascii=False,
    )


def _memory_write(args: dict, **kwargs) -> str:
    from masld_agent.memory_store import append_decision, write_campaign_field

    target_id = str(args.get("target_id") or "")
    action = str(args.get("action") or "")
    if action == "set_field":
        result = write_campaign_field(
            target_id=target_id,
            field=str(args.get("field") or ""),
            value=str(args.get("value") or ""),
        )
    elif action == "append_decision":
        result = append_decision(
            target_id=target_id,
            stage=str(args.get("stage") or ""),
            decision=str(args.get("decision") or "NOTE"),
            summary=str(args.get("summary") or ""),
            evidence=str(args.get("evidence") or ""),
        )
    else:
        result = {"status": "error", "error": f"unknown action: {action}"}
    return json.dumps(result, ensure_ascii=False)


def _global_history_append(args: dict, **kwargs) -> str:
    from masld_agent.memory_store import append_global_history

    return json.dumps(append_global_history(str(args.get("line") or "")), ensure_ascii=False)


def _ui_navigate(args: dict, **kwargs) -> str:
    from masld_agent.ui_command_bus import ui_navigate

    return json.dumps(
        ui_navigate(str(args.get("session_id") or "default"), str(args.get("path") or "/")),
        ensure_ascii=False,
    )


def _ui_highlight(args: dict, **kwargs) -> str:
    from masld_agent.ui_command_bus import ui_highlight

    return json.dumps(
        ui_highlight(
            str(args.get("session_id") or "default"),
            str(args.get("entity_type") or ""),
            str(args.get("entity_id") or ""),
        ),
        ensure_ascii=False,
    )


def _ui_open_molecule(args: dict, **kwargs) -> str:
    from masld_agent.ui_command_bus import ui_open_molecule

    return json.dumps(
        ui_open_molecule(
            str(args.get("session_id") or "default"),
            str(args.get("molecule_id") or ""),
            args.get("smiles"),
        ),
        ensure_ascii=False,
    )


def _ui_set_target(args: dict, **kwargs) -> str:
    from masld_agent.ui_command_bus import ui_set_target

    return json.dumps(
        ui_set_target(
            str(args.get("session_id") or "default"),
            str(args.get("target_id") or ""),
            args.get("name"),
        ),
        ensure_ascii=False,
    )


def _ui_start_task(args: dict, **kwargs) -> str:
    from masld_agent.ui_command_bus import ui_start_task

    return json.dumps(
        ui_start_task(
            str(args.get("session_id") or "default"),
            str(args.get("api_path") or ""),
            args.get("body") if isinstance(args.get("body"), dict) else {},
        ),
        ensure_ascii=False,
    )


def register(ctx):
    """Hermes plugin entry: ctx.register_tool / register_command / register_cli_command."""
    tools = [
        ("masld_offline_demo", OFFLINE_SCHEMA, _run_offline),
        ("masld_run_pipeline", RUN_SCHEMA, _run_pipeline),
        ("masld_competition_brief", BRIEF_SCHEMA, _competition_brief),
        ("masld_validate_submission", VALIDATE_SCHEMA, _validate_submission),
        ("masld_pack_submission", PACK_SCHEMA, _pack_submission),
        ("target_biology_search", TARGET_BIOLOGY_SCHEMA, _target_biology_search),
        ("structure_search_rank", STRUCTURE_SEARCH_SCHEMA, _structure_search_rank),
        ("pocket_qualify", POCKET_QUALIFY_SCHEMA, _pocket_qualify),
        ("compound_evidence_enrich", COMPOUND_ENRICH_SCHEMA, _compound_evidence_enrich),
        ("toxicity_triage", TOXICITY_TRIAGE_SCHEMA, _toxicity_triage),
        ("nominate_compounds", NOMINATE_COMPOUNDS_SCHEMA, _nominate_compounds),
        ("build_validation_report", BUILD_VALIDATION_REPORT_SCHEMA, _build_validation_report),
        ("platform_catalog", CATALOG_SCHEMA, _platform_catalog),
        ("platform_health", HEALTH_SCHEMA, _platform_health),
        ("diffdynamic_status", DD_STATUS_SCHEMA, _diffdynamic_status),
        ("diffdynamic_generate", DD_GEN_SCHEMA, _diffdynamic_generate),
        ("diffdynamic_extract", DD_EXTRACT_SCHEMA, _diffdynamic_extract),
        ("schrodinger_status", SZ_STATUS_SCHEMA, _schrodinger_status),
        ("schrodinger_dock", SZ_DOCK_SCHEMA, _schrodinger_dock),
        ("schrodinger_mmgbsa", SZ_MMGBSA_SCHEMA, _schrodinger_mmgbsa),
        ("schrodinger_md_submit", SZ_MD_SUBMIT_SCHEMA, _schrodinger_md_submit),
        ("schrodinger_md_status", SZ_MD_STATUS_SCHEMA, _schrodinger_md_status),
        ("funnel_plan", FUNNEL_PLAN_SCHEMA, _funnel_plan),
        ("funnel_preflight", FUNNEL_PREFLIGHT_SCHEMA, _funnel_preflight),
        ("funnel_run_stage", FUNNEL_STAGE_SCHEMA, _funnel_run_stage),
        ("funnel_validate_stage", FUNNEL_VALIDATE_SCHEMA, _funnel_validate_stage),
        ("funnel_status", FUNNEL_STATUS_SCHEMA, _funnel_status),
        ("funnel_autopilot", FUNNEL_AUTOPILOT_SCHEMA, _funnel_autopilot),
        ("funnel_autopilot_status", FUNNEL_AUTOPILOT_STATUS_SCHEMA, _funnel_autopilot_status),
        ("campaign_memory_read", MEMORY_READ_SCHEMA, _memory_read),
        ("campaign_memory_write", MEMORY_WRITE_SCHEMA, _memory_write),
        ("global_history_append", GLOBAL_HISTORY_SCHEMA, _global_history_append),
        ("edrug_ui_navigate", UI_NAV_SCHEMA, _ui_navigate),
        ("edrug_ui_highlight", UI_HIGHLIGHT_SCHEMA, _ui_highlight),
        ("edrug_ui_open_molecule", UI_OPEN_MOL_SCHEMA, _ui_open_molecule),
        ("edrug_ui_set_target", UI_SET_TARGET_SCHEMA, _ui_set_target),
        ("edrug_ui_start_task", UI_START_TASK_SCHEMA, _ui_start_task),
    ]
    for name, schema, handler in tools:
        try:
            ctx.register_tool(
                name=name,
                toolset="scientist_in_e_drug_lab",
                schema=schema,
                handler=handler,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Hermes register_tool skipped %s: %s", name, exc)

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
        skills_root = PKG_ROOT / "skills"
        if hasattr(ctx, "register_skill") and skills_root.exists():
            for skill_root in sorted(skills_root.iterdir()):
                if skill_root.is_dir() and (skill_root / "SKILL.md").is_file():
                    ctx.register_skill(str(skill_root))
    except Exception as exc:  # noqa: BLE001
        logger.debug("register_skill skipped: %s", exc)

    logger.info("scientist_in_e_drug_lab plugin registered")
