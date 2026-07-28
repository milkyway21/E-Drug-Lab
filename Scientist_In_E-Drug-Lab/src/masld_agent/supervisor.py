"""Supervisor orchestrating deterministic tool nodes."""
from __future__ import annotations

import csv
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

from masld_agent.agents.evidence_critic import critique_hypothesis
from masld_agent.agents.novelty_critic import OFFLINE_NOVELTY_PRIORS, assess_novelty
from masld_agent.agents.target_generator import generate_candidates
from masld_agent.config import DEFAULT_SCORING, PKG_ROOT, load_competition_config
from masld_agent.models import (
    AgentRunManifest,
    DiseaseScope,
    EvidenceLevel,
    EvidenceRecord,
    TargetHypothesis,
    ValidationExperiment,
)
from masld_agent.reporting import write_standard_reports
from masld_agent.scoring import load_weights, novelty_score_from_class, score_target
from masld_agent.submission import write_ai4s_readme
from masld_agent.tools.competition import parse_competition
from masld_agent.tools.docking import run_docking
from masld_agent.tools.pdb import pocket_from_fixture, rank_structures, structure_from_fixture
from masld_agent.tools.pubchem import ligand_from_fixture
from masld_agent.tools.rdkit_eval import evaluate_ligand_record


def _now_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]


def _append_event(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")


def load_fixture(fixture_dir: Path) -> dict[str, Any]:
    meta = yaml.safe_load((fixture_dir / "meta.yaml").read_text(encoding="utf-8"))
    return meta


def build_hypothesis_from_fixture(fixture_dir: Path, weights: dict[str, float]) -> TargetHypothesis:
    meta = load_fixture(fixture_dir)
    gene = meta["gene_symbol"]
    novelty_meta = OFFLINE_NOVELTY_PRIORS.get(gene.upper(), meta.get("novelty", {}))
    novelty_cls, novelty_warnings = assess_novelty(novelty_meta)

    structures = [structure_from_fixture(s) for s in meta.get("structures") or []]
    structures = rank_structures(structures)
    pockets = [pocket_from_fixture(p) for p in meta.get("pockets") or []]
    ligands = [ligand_from_fixture(x) for x in meta.get("ligands") or []]

    evidence = []
    for e in meta.get("evidence") or []:
        evidence.append(
            EvidenceRecord(
                source=e.get("source", "fixture"),
                evidence_level=EvidenceLevel(e.get("evidence_level", "B")),
                confidence=float(e.get("confidence", 0.8)),
                warnings=[],
                provenance=e.get("provenance") or {},
                pmid=e.get("pmid"),
                doi=e.get("doi"),
                url=e.get("url"),
                title=e.get("title"),
                year=e.get("year"),
                abstract_excerpt=e.get("abstract_excerpt"),
                supports_claim=e.get("supports_claim"),
                verified=bool(e.get("verified", True)),
            )
        )
    # Drop unverified from final
    evidence = [e for e in evidence if e.verified]

    dims = meta.get("dimension_scores") or {}
    # Fill novelty from class if missing
    if dims.get("novelty") is None:
        dims["novelty"] = novelty_score_from_class(novelty_cls)

    scores = score_target(
        dimension_scores=dims,
        weights=weights,
        sources=meta.get("score_sources") or {},
    )

    for lig in ligands:
        if lig.smiles:
            props = evaluate_ligand_record(lig.smiles)
            lig.provenance["rdkit"] = props

    docking = [run_docking()]  # typically skipped_missing_dependency offline

    validation = [
        ValidationExperiment(
            source="fixture",
            evidence_level=EvidenceLevel.C,
            confidence=0.7,
            warnings=[],
            provenance={},
            system="cell",
            readout="HepG2-FFA lipid droplet / Nile Red + CellTiter viability",
            controls=["vehicle", "positive lipid-lowering control"],
            notes="Count hits only if viability remains high and lipid falls.",
        ),
        ValidationExperiment(
            source="fixture",
            evidence_level=EvidenceLevel.C,
            confidence=0.6,
            warnings=[],
            provenance={},
            system="organoid",
            readout="Human liver organoid steatosis model",
            controls=["vehicle"],
            notes="Optional follow-up after cell hit confirmation.",
        ),
        ValidationExperiment(
            source="fixture",
            evidence_level=EvidenceLevel.C,
            confidence=0.5,
            warnings=[],
            provenance={},
            system="animal",
            readout="Diet-induced MASLD mouse — liver TG / histology",
            controls=["pair-fed"],
            notes="Only after in vitro confirmation; not a competition wet-lab substitute.",
        ),
    ]

    hyp = TargetHypothesis(
        source="fixture",
        evidence_level=EvidenceLevel.B,
        confidence=0.8,
        warnings=novelty_warnings,
        provenance={"fixture_dir": str(fixture_dir)},
        gene_symbol=gene,
        uniprot_id=meta.get("uniprot_id"),
        novelty_class=novelty_cls,
        scores=scores,
        structures=structures,
        pockets=pockets,
        ligands=ligands,
        docking=docking,
        evidence=evidence,
        scientific_significance=meta.get("scientific_significance", ""),
        clinical_significance=meta.get("clinical_significance", ""),
        uncertainty=meta.get("uncertainty", ""),
        validation_plan=validation,
    )
    return critique_hypothesis(hyp)


def run_offline_demo(
    fixture_dir: Path,
    output_dir: Path,
    *,
    competition_config: Optional[Path] = None,
    disease: DiseaseScope = DiseaseScope.MASLD,
) -> Path:
    run_id = _now_id()
    out = output_dir / run_id
    out.mkdir(parents=True, exist_ok=True)
    events = out / "events.jsonl"

    profile = parse_competition(competition_config, disease=disease)
    _append_event(events, {"event": "competition_parsed", "disease": disease.value})

    weights = load_weights(DEFAULT_SCORING)
    hyp = build_hypothesis_from_fixture(fixture_dir, weights)
    _append_event(events, {"event": "fixture_hypothesis", "gene": hyp.gene_symbol})

    # Also score KHK fixture if present beside hsd17b13 for contrast demos
    hypotheses = [hyp]
    khk = fixture_dir.parent / "khk"
    if khk.exists() and (khk / "meta.yaml").exists() and fixture_dir.name != "khk":
        hypotheses.append(build_hypothesis_from_fixture(khk, weights))

    hypotheses.sort(key=lambda h: (h.scores.total is None, -(h.scores.total or 0)))

    cfg_snap = out / "config_snapshot.yaml"
    cfg_snap.write_text(
        yaml.safe_dump(load_competition_config(competition_config), sort_keys=False),
        encoding="utf-8",
    )

    manifest = AgentRunManifest(
        source="supervisor",
        evidence_level=EvidenceLevel.A,
        confidence=1.0,
        warnings=[profile.competition_scope_warning],
        provenance={},
        run_id=run_id,
        disease=disease,
        offline=True,
        competition_scope_warning=profile.competition_scope_warning,
        config_snapshot_path=str(cfg_snap),
        output_dir=str(out),
        hermes_eval_mode=True,
        tool_versions={"masld_agent": "0.1.0"},
        events_path=str(events),
    )
    (out / "manifest.json").write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8"
    )

    # evidence.json
    (out / "evidence.json").write_text(
        json.dumps(
            {h.gene_symbol: [e.model_dump(mode="json") for e in h.evidence] for h in hypotheses},
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    (out / "structures.json").write_text(
        json.dumps(
            {h.gene_symbol: [s.model_dump(mode="json") for s in h.structures] for h in hypotheses},
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    with (out / "targets_ranked.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "rank",
                "gene_symbol",
                "uniprot_id",
                "novelty_class",
                "score_total",
                "missing_dimensions",
            ],
        )
        w.writeheader()
        for i, h in enumerate(hypotheses, 1):
            w.writerow(
                {
                    "rank": i,
                    "gene_symbol": h.gene_symbol,
                    "uniprot_id": h.uniprot_id,
                    "novelty_class": h.novelty_class.value,
                    "score_total": h.scores.total,
                    "missing_dimensions": ";".join(h.scores.missing_dimensions),
                }
            )

    with (out / "ligands.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["gene_symbol", "name", "role", "pubchem_cid", "smiles", "inchikey"],
        )
        w.writeheader()
        for h in hypotheses:
            for lig in h.ligands:
                w.writerow(
                    {
                        "gene_symbol": h.gene_symbol,
                        "name": lig.name,
                        "role": lig.role.value,
                        "pubchem_cid": lig.pubchem_cid,
                        "smiles": lig.smiles,
                        "inchikey": lig.inchikey,
                    }
                )

    write_standard_reports(out, profile=profile, hypotheses=hypotheses, offline=True)
    write_ai4s_readme(out)
    _append_event(events, {"event": "completed", "output": str(out)})
    return out


def run_pipeline(
    output_dir: Path,
    *,
    competition_config: Optional[Path] = None,
    disease: DiseaseScope = DiseaseScope.MASLD,
    modality: str = "small_molecule_inhibitor",
    top_targets: int = 10,
    online: bool = False,
) -> Path:
    """Online-capable run: uses curated panel; fetches live APIs when online=True."""
    run_id = _now_id()
    out = output_dir / run_id
    out.mkdir(parents=True, exist_ok=True)
    events = out / "events.jsonl"
    profile = parse_competition(competition_config, disease=disease)
    weights = load_weights(DEFAULT_SCORING)
    candidates = generate_candidates(disease, top_n=top_targets)
    _append_event(events, {"event": "candidates", "n": len(candidates)})

    hypotheses: list[TargetHypothesis] = []
    fixtures_root = PKG_ROOT / "tests" / "fixtures"

    for cand in candidates:
        # Prefer fixture enrichment when available (reproducible MVP).
        fix = fixtures_root / cand.gene_symbol.lower()
        # map HSD17B13 -> hsd17b13, KHK -> khk
        alt = fixtures_root / {
            "HSD17B13": "hsd17b13",
            "KHK": "khk",
        }.get(cand.gene_symbol.upper(), "")
        fixture_path = fix if (fix / "meta.yaml").exists() else alt
        if fixture_path and (fixture_path / "meta.yaml").exists():
            hyp = build_hypothesis_from_fixture(fixture_path, weights)
            hypotheses.append(hyp)
            continue

        # Minimal online path for non-fixture genes
        novelty_cls, nwarn = assess_novelty(
            {
                "has_approved_drug": False,
                "has_late_clinical": False,
                "has_early_clinical_or_strong_preclinical": False,
            }
        )
        dims = {
            "human_genetics_evidence": None,
            "disease_mechanism_relevance": 0.5,
            "hepatocyte_or_liver_specificity": 0.4,
            "druggability": None,
            "structure_availability": None,
            "ligand_precedent": None,
            "safety_rationale": 0.4,
            "novelty": novelty_score_from_class(novelty_cls),
        }
        if online:
            try:
                from masld_agent.tools.literature import build_target_query, search_europe_pmc

                ev = search_europe_pmc(build_target_query(cand.gene_symbol, disease.value))
            except Exception as exc:  # noqa: BLE001
                ev = []
                nwarn.append(f"literature_fetch_failed:{exc}")
        else:
            ev = []
            nwarn.append("online_disabled_no_fixture_evidence")

        hyp = TargetHypothesis(
            source="supervisor",
            evidence_level=EvidenceLevel.D,
            confidence=0.3,
            warnings=nwarn,
            provenance={"gene": cand.gene_symbol},
            gene_symbol=cand.gene_symbol,
            uniprot_id=cand.uniprot_id,
            novelty_class=novelty_cls,
            scores=score_target(dimension_scores=dims, weights=weights),
            evidence=[e for e in ev if e.verified],
            scientific_significance=cand.rationale,
            validation_plan=[],
            docking=[run_docking()],
        )
        hypotheses.append(critique_hypothesis(hyp))

    hypotheses.sort(key=lambda h: (h.scores.total is None, -(h.scores.total or 0)))

    cfg_snap = out / "config_snapshot.yaml"
    cfg_snap.write_text(
        yaml.safe_dump(load_competition_config(competition_config), sort_keys=False),
        encoding="utf-8",
    )
    manifest = AgentRunManifest(
        source="supervisor",
        evidence_level=EvidenceLevel.A,
        confidence=1.0,
        warnings=[profile.competition_scope_warning],
        provenance={"modality": modality, "online": online},
        run_id=run_id,
        disease=disease,
        modality=modality,
        top_targets=top_targets,
        offline=not online,
        competition_scope_warning=profile.competition_scope_warning,
        config_snapshot_path=str(cfg_snap),
        output_dir=str(out),
        hermes_eval_mode=True,
        tool_versions={"masld_agent": "0.1.0"},
        events_path=str(events),
    )
    (out / "manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    (out / "evidence.json").write_text(
        json.dumps(
            {h.gene_symbol: [e.model_dump(mode="json") for e in h.evidence] for h in hypotheses},
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    (out / "structures.json").write_text(
        json.dumps(
            {h.gene_symbol: [s.model_dump(mode="json") for s in h.structures] for h in hypotheses},
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    with (out / "targets_ranked.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "rank",
                "gene_symbol",
                "uniprot_id",
                "novelty_class",
                "score_total",
                "missing_dimensions",
            ],
        )
        w.writeheader()
        for i, h in enumerate(hypotheses, 1):
            w.writerow(
                {
                    "rank": i,
                    "gene_symbol": h.gene_symbol,
                    "uniprot_id": h.uniprot_id,
                    "novelty_class": h.novelty_class.value,
                    "score_total": h.scores.total,
                    "missing_dimensions": ";".join(h.scores.missing_dimensions),
                }
            )
    with (out / "ligands.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["gene_symbol", "name", "role", "pubchem_cid", "smiles", "inchikey"],
        )
        w.writeheader()
        for h in hypotheses:
            for lig in h.ligands:
                w.writerow(
                    {
                        "gene_symbol": h.gene_symbol,
                        "name": lig.name,
                        "role": lig.role.value,
                        "pubchem_cid": lig.pubchem_cid,
                        "smiles": lig.smiles,
                        "inchikey": lig.inchikey,
                    }
                )
    write_standard_reports(
        out,
        profile=profile,
        hypotheses=hypotheses,
        offline=not online,
        extra_warnings=[] if online else ["run_used_fixtures_or_partial_online"],
    )
    write_ai4s_readme(out)
    _append_event(events, {"event": "completed", "output": str(out)})
    return out


def evaluate_single_target(
    *,
    gene: str,
    uniprot: Optional[str],
    output_dir: Path,
    competition_config: Optional[Path] = None,
) -> Path:
    fixtures_root = PKG_ROOT / "tests" / "fixtures"
    mapping = {"HSD17B13": "hsd17b13", "KHK": "khk"}
    name = mapping.get(gene.upper(), gene.lower())
    fixture = fixtures_root / name
    if (fixture / "meta.yaml").exists():
        return run_offline_demo(fixture, output_dir, competition_config=competition_config)

    # Fallback: synthesize minimal hypothesis
    out = run_pipeline(
        output_dir,
        competition_config=competition_config,
        top_targets=1,
        online=False,
    )
    return out
