"""Deterministic E0-E6 evidence envelope around the H0-H10 compute funnel."""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from masld_agent.config import DEFAULT_COMPETITION, load_competition_config
from masld_agent.http_cache import CachedHttp
from masld_agent.models import (
    CompoundEvidenceCard,
    EvidenceLevel,
    MechanismHypothesis,
    PocketQualification,
    StructureCandidate,
    TargetEvidenceCard,
)
from masld_agent.reporting.markdown import try_export_pdf
from masld_agent.tools.chembl import fetch_chembl_activities, find_chembl_molecule_by_inchikey
from masld_agent.tools.ai4s_brief import normalize_output_language
from masld_agent.tools.compound_evidence import (
    DEFAULT_NOMINATION_WEIGHTS,
    dump_cards_jsonl,
    load_compound_library,
    rank_compounds,
)
from masld_agent.tools.literature import build_target_query, search_europe_pmc
from masld_agent.tools.open_targets import fetch_target_associations_post
from masld_agent.tools.pdb import discover_structure_candidates, qualify_pocket
from masld_agent.tools.pubchem import fetch_compound_by_inchikey, parse_pubchem_properties
from masld_agent.tools.reactome import search_human_pathways
from masld_agent.tools.uniprot import resolve_human_gene


EVIDENCE_STAGES = (
    "E0_scope",
    "E1_target_biology",
    "E2_structure_reconnaissance",
    "E3_pocket_qualification",
    "E4_compound_enrichment",
    "E5_toxicity_triage",
    "E6_nomination_reporting",
)

LIPID_MECHANISM_TERMS = {
    "SREBP": "de novo lipogenesis",
    "ACACA": "ACC / de novo lipogenesis",
    "ACACB": "ACC / fatty-acid oxidation gate",
    "ACETYL-COA CARBOXYLASE": "ACC / lipogenesis and fatty-acid oxidation gate",
    "FASN": "fatty-acid synthesis",
    "FATTY ACID SYNTHASE": "fatty-acid synthesis",
    "SCD1": "fatty-acid desaturation",
    "STEAROYL-COA DESATURASE": "fatty-acid desaturation",
    "PPARA": "fatty-acid oxidation",
    "PPAR-ALPHA": "fatty-acid oxidation",
    "PEROXISOME PROLIFERATOR-ACTIVATED RECEPTOR ALPHA": "fatty-acid oxidation",
    "PRKAA": "AMPK energy sensing",
    "AMPK": "AMPK energy sensing",
    "CPT1": "mitochondrial fatty-acid oxidation",
    "CD36": "fatty-acid uptake",
    "ABCA1": "lipid efflux",
    "AUTOPHAG": "autophagy / lipophagy",
}

TOP10_NOMINATION_FIELDS = [
    "rank",
    "library_id",
    "id_or_name",
    "canonical_smiles",
    "parent_inchikey",
    "smiles_or_inchikey",
    "target_or_pathway",
    "evidence_level",
    "lipid_score",
    "safety_score",
    "uncertainty_penalty",
    "ranking_basis",
    "score_components",
    "structure_applicability",
    "lipid_rationale",
    "tox_rationale",
    "toxicity_evidence_status",
    "mechanism_hypothesis",
    "validation_readouts",
    "evidence_refs",
    "library_source",
    "library_sha256",
    "nomination_status",
]


def _toxicity_evidence_status(card: CompoundEvidenceCard) -> str:
    if any(item.observed for item in card.safety_evidence):
        return "observed"
    if any(item.prediction for item in card.safety_evidence):
        return "predicted_only"
    return "unknown"


def _ranking_basis(card: CompoundEvidenceCard) -> str:
    return (
        "weighted score: lipid evidence 30%; mechanism/pathway 20%; activity quality 15%; "
        "safety 20%; structure/developability 10%; diversity 5%; "
        f"uncertainty penalty {card.score.uncertainty_penalty:g} points"
    )


def _json_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def _stage_report(
    output_dir: Path,
    stage: str,
    *,
    status: str,
    summary: str,
    artifacts: list[Path],
    warnings: Optional[list[str]] = None,
) -> None:
    payload = {
        "stage": stage,
        "status": status,
        "summary": summary,
        "artifacts": [str(path.relative_to(output_dir)) for path in artifacts if path.exists()],
        "warnings": warnings or [],
        "reported_at": datetime.now(timezone.utc).isoformat(),
    }
    _json_write(output_dir / "stage_reports" / f"{stage}.json", payload)
    lines = [
        f"# {stage}",
        "",
        f"- status: `{status}`",
        f"- summary: {summary}",
        f"- artifacts: {', '.join(payload['artifacts']) or 'none'}",
        f"- warnings: {', '.join(payload['warnings']) or 'none'}",
        "",
    ]
    (output_dir / "stage_reports" / f"{stage}.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )


def build_target_evidence_card(
    gene: str,
    disease: str,
    *,
    online: bool,
    http: Optional[CachedHttp] = None,
) -> TargetEvidenceCard:
    client = http or CachedHttp()
    warnings: list[str] = []
    identity: dict[str, Any] = {
        "gene_symbol": gene.upper(),
        "uniprot_id": None,
        "ensembl_id": None,
        "function": "",
    }
    literature = []
    associations = []
    pathways: list[str] = []
    if online:
        try:
            identity = resolve_human_gene(gene, http=client)
            warnings.extend(identity.get("warnings") or [])
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"uniprot_lookup_failed:{exc}")
        try:
            literature = search_europe_pmc(build_target_query(gene, disease), http=client)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"literature_lookup_failed:{exc}")
        if identity.get("ensembl_id"):
            associations = fetch_target_associations_post(identity["ensembl_id"], http=client)
            warnings.extend(
                warning
                for record in associations
                if not record.verified
                for warning in record.warnings
            )
        try:
            pathway_hits = search_human_pathways(gene, http=client)
            pathways = [
                f"{hit.get('stable_id')}: {hit.get('name')}"
                for hit in pathway_hits
                if hit.get("name")
            ]
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"reactome_lookup_failed:{exc}")
    else:
        warnings.append("online_disabled_target_evidence_not_enriched")
    disease_terms = {disease.lower()}
    if disease.upper() == "MASLD":
        disease_terms.update({"metabolic dysfunction-associated steatotic liver", "nafld", "steatosis"})
    matching_associations = [
        record
        for record in associations
        if record.verified
        and any(term in (record.supports_claim or "").lower() for term in disease_terms)
    ]
    supporting = literature + matching_associations
    return TargetEvidenceCard(
        source="target_evidence_pipeline",
        evidence_level=EvidenceLevel.B if supporting else EvidenceLevel.U,
        confidence=min(0.9, 0.3 + 0.05 * len(supporting)) if supporting else 0.1,
        warnings=warnings,
        provenance={
            "sources": ["UniProt", "Europe PMC", "Open Targets", "Reactome"],
            "online": online,
        },
        gene_symbol=identity.get("gene_symbol") or gene.upper(),
        disease=disease,
        uniprot_id=identity.get("uniprot_id"),
        ensembl_id=identity.get("ensembl_id"),
        biological_function=identity.get("function") or "",
        pathways=pathways,
        supporting_evidence=supporting,
        unresolved_questions=[
            "Review apparently supporting citations for directionality and causal intervention evidence.",
            "Search explicitly for null, paradoxical, and adverse intervention evidence.",
            *(
                []
                if supporting
                else ["No verified target-disease evidence was retrieved; mechanism remains unresolved."]
            ),
        ],
    )


def _refresh_score(card: CompoundEvidenceCard) -> None:
    weighted = sum(
        getattr(card.score, name) * weight for name, weight in DEFAULT_NOMINATION_WEIGHTS.items()
    )
    card.score.weighted_total = round(max(0.0, min(100.0, weighted)), 4)
    card.score.final_score = round(
        max(0.0, card.score.weighted_total - card.score.uncertainty_penalty), 4
    )
    card.confidence = card.score.final_score / 100.0


def enrich_cards_online(
    cards: list[CompoundEvidenceCard],
    *,
    limit: int,
    http: Optional[CachedHttp] = None,
) -> None:
    """Exact-identity enrichment only; capped to avoid uncontrolled bulk API calls."""
    client = http or CachedHttp()
    for card in cards[: max(0, limit)]:
        if not card.parent_inchikey:
            continue
        try:
            pubchem = parse_pubchem_properties(
                fetch_compound_by_inchikey(card.parent_inchikey, http=client)
            )
            card.pubchem_cid = pubchem.get("cid")
            if not card.name:
                card.name = pubchem.get("iupac")
        except Exception as exc:  # noqa: BLE001
            card.warnings.append(f"pubchem_exact_identity_lookup_failed:{exc}")
        try:
            molecule = find_chembl_molecule_by_inchikey(card.parent_inchikey, http=client)
            if molecule:
                card.chembl_id = molecule.get("molecule_chembl_id")
                if card.chembl_id:
                    card.activity_evidence = fetch_chembl_activities(card.chembl_id, http=client)
                    contextual = [
                        evidence
                        for evidence in card.activity_evidence
                        if evidence.assay_id
                        and evidence.target
                        and evidence.standard_type
                        and (evidence.standard_value is not None or evidence.pchembl_value is not None)
                    ]
                    if contextual:
                        card.evidence_level = EvidenceLevel.B
                    lipid_targets: list[tuple[str, str]] = []
                    for evidence in contextual:
                        target_name = evidence.target or ""
                        target_upper = target_name.upper()
                        for term, pathway in LIPID_MECHANISM_TERMS.items():
                            if term in target_upper:
                                lipid_targets.append((target_name, pathway))
                                break
                    if lipid_targets:
                        for target_name, pathway in lipid_targets:
                            if target_name not in card.target_or_pathway:
                                card.target_or_pathway.append(target_name)
                            if pathway not in card.target_or_pathway:
                                card.target_or_pathway.append(pathway)
                        card.score.lipid_evidence = max(card.score.lipid_evidence, 35.0)
                        card.score.mechanism_relevance = max(
                            card.score.mechanism_relevance, 50.0
                        )
                        if not card.lipid_rationale:
                            card.lipid_rationale = (
                                "Exact-identity ChEMBL records report activity against lipid-related "
                                "target(s); a lipid-lowering phenotype has not yet been demonstrated."
                            )
                        if not card.mechanism_hypotheses:
                            target_names = "; ".join(
                                dict.fromkeys(target for target, _pathway in lipid_targets)
                            )
                            pathways = "; ".join(
                                dict.fromkeys(pathway for _target, pathway in lipid_targets)
                            )
                            card.mechanism_hypotheses.append(
                                MechanismHypothesis(
                                    intervention=card.name or card.library_id,
                                    direct_action="reported ChEMBL activity; functional direction unresolved",
                                    target_or_pathway=f"{target_names} / {pathways}",
                                    expected_direction="to_be_tested",
                                    lipid_phenotype="reduced lipid accumulation if the proposed direction is correct",
                                    evidence_refs=[
                                        evidence.document_id
                                        for evidence in contextual
                                        if evidence.document_id
                                    ],
                                    alternative_mechanisms=[
                                        "off-target or phenotype-independent activity"
                                    ],
                                    falsifiers=[
                                        "no target engagement or no lipid effect at non-cytotoxic exposure"
                                    ],
                                    validation_readouts=[
                                        "HepG2-FFA lipid accumulation",
                                        "cell viability",
                                        "target engagement or pathway readout",
                                    ],
                                )
                            )
                    card.score.activity_quality = min(100.0, 35.0 + 10.0 * len(contextual))
                    _refresh_score(card)
        except Exception as exc:  # noqa: BLE001
            card.warnings.append(f"chembl_exact_identity_lookup_failed:{exc}")
    if len(cards) > limit:
        for card in cards[limit:]:
            card.warnings.append("online_enrichment_limit_reached")


def _write_structure_csv(path: Path, structures: list[StructureCandidate]) -> None:
    fields = [
        "rank",
        "pdb_id",
        "entity_id",
        "target_gene",
        "uniprot_id",
        "organism",
        "method",
        "resolution_A",
        "chains",
        "bound_ligands",
        "mutations",
        "quality_score",
        "preferred",
        "warnings",
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for rank, structure in enumerate(structures, 1):
            writer.writerow(
                {
                    "rank": rank,
                    "pdb_id": structure.pdb_id,
                    "entity_id": structure.entity_id,
                    "target_gene": structure.target_gene,
                    "uniprot_id": structure.uniprot_id,
                    "organism": structure.organism,
                    "method": structure.method,
                    "resolution_A": structure.resolution_A,
                    "chains": ";".join(structure.chains),
                    "bound_ligands": ";".join(structure.bound_ligands),
                    "mutations": ";".join(structure.mutations),
                    "quality_score": structure.quality_score,
                    "preferred": structure.preferred,
                    "warnings": ";".join(structure.warnings),
                }
            )


def _write_toxicity_csv(path: Path, cards: list[CompoundEvidenceCard]) -> None:
    fields = [
        "library_id",
        "parent_inchikey",
        "safety_score",
        "toxicity_rationale",
        "structure_alerts",
        "observed_evidence_count",
        "predicted_evidence_count",
        "evidence_status",
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for card in cards:
            observed = sum(evidence.observed for evidence in card.safety_evidence)
            predicted = sum(evidence.prediction for evidence in card.safety_evidence)
            writer.writerow(
                {
                    "library_id": card.library_id,
                    "parent_inchikey": card.parent_inchikey,
                    "safety_score": card.score.safety,
                    "toxicity_rationale": card.toxicity_rationale,
                    "structure_alerts": ";".join(card.structure_alerts),
                    "observed_evidence_count": observed,
                    "predicted_evidence_count": predicted,
                    "evidence_status": "observed" if observed else "predicted_only" if predicted else "unknown",
                }
            )


def _mechanism_text(card: CompoundEvidenceCard) -> str:
    if not card.mechanism_hypotheses:
        return "Unresolved; requires target/pathway deconvolution."
    mechanism = card.mechanism_hypotheses[0]
    return (
        f"{mechanism.intervention} -> {mechanism.direct_action} -> "
        f"{mechanism.target_or_pathway} -> {mechanism.expected_direction} -> "
        f"{mechanism.lipid_phenotype}"
    )


def _write_scorecards(
    output_dir: Path,
    cards: list[CompoundEvidenceCard],
    final_count: int,
    *,
    library_sha256: str,
) -> None:
    score_fields = [
        "rank",
        "library_id",
        "name",
        "parent_inchikey",
        "lipid_evidence",
        "mechanism_relevance",
        "activity_quality",
        "safety",
        "structure_developability",
        "diversity",
        "uncertainty_penalty",
        "weighted_total",
        "final_score",
        "identity_valid",
        "warnings",
    ]
    with (output_dir / "nomination_scorecard.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=score_fields)
        writer.writeheader()
        for rank, card in enumerate(cards, 1):
            writer.writerow(
                {
                    "rank": rank,
                    "library_id": card.library_id,
                    "name": card.name,
                    "parent_inchikey": card.parent_inchikey,
                    **{
                        field: getattr(card.score, field)
                        for field in score_fields[4:13]
                    },
                    "identity_valid": card.identity_valid,
                    "warnings": ";".join(card.warnings),
                }
            )
    with (output_dir / "top10_nomination.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=TOP10_NOMINATION_FIELDS)
        writer.writeheader()
        for rank, card in enumerate(cards[:final_count], 1):
            evidence_refs = list(card.provenance.get("evidence_refs") or [])
            evidence_refs.extend(
                evidence.document_id
                for evidence in card.activity_evidence
                if evidence.document_id
            )
            readouts = [
                readout
                for mechanism in card.mechanism_hypotheses
                for readout in mechanism.validation_readouts
            ]
            writer.writerow(
                {
                    "rank": rank,
                    "library_id": card.library_id,
                    "id_or_name": card.name or card.library_id,
                    "canonical_smiles": card.canonical_smiles,
                    "parent_inchikey": card.parent_inchikey,
                    "smiles_or_inchikey": card.canonical_smiles or card.parent_inchikey,
                    "target_or_pathway": ";".join(card.target_or_pathway),
                    "evidence_level": card.evidence_level.value,
                    "lipid_score": card.score.lipid_evidence,
                    "safety_score": card.score.safety,
                    "uncertainty_penalty": card.score.uncertainty_penalty,
                    "ranking_basis": _ranking_basis(card),
                    "score_components": json.dumps(
                        card.score.model_dump(mode="json"),
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    "structure_applicability": card.structure_applicability,
                    "lipid_rationale": card.lipid_rationale,
                    "tox_rationale": card.toxicity_rationale,
                    "toxicity_evidence_status": _toxicity_evidence_status(card),
                    "mechanism_hypothesis": _mechanism_text(card),
                    "validation_readouts": ";".join(readouts)
                    or "HepG2-FFA lipid accumulation; cell viability",
                    "evidence_refs": ";".join(dict.fromkeys(evidence_refs)),
                    "library_source": card.library_source,
                    "library_sha256": library_sha256,
                    "nomination_status": (
                        "candidate_for_experimental_testing"
                        if card.identity_valid
                        else "rejected_invalid_identity"
                    ),
                }
            )


def _write_mechanism_report(
    path: Path,
    cards: list[CompoundEvidenceCard],
    *,
    disease: str,
    final_count: int,
    library_sha256: str,
    language: str = "zh",
) -> None:
    english = normalize_output_language(language) == "en"
    if english:
        lines = [
            "# Candidate nomination, mechanism, and validation report",
            "",
            f"- Disease/phenotype context: {disease}",
            f"- Nominated compounds: {min(final_count, len(cards))}",
            f"- Official library SHA-256: `{library_sha256}`",
            "- Ranking is computational evidence synthesis, not experimental confirmation.",
            "- Missing toxicity evidence is reported as unknown, never as low toxicity.",
            "",
            "## Ranking method",
            "",
            "Lipid evidence 30%, mechanism/pathway 20%, activity quality 15%, safety 20%, "
            "structure/developability 10%, diversity 5%; missing/conflicting evidence incurs up to "
            "20 points uncertainty penalty.",
            "",
            "## Candidates",
            "",
        ]
    else:
        lines = [
            "# 候选分子提名、机制与验证报告",
            "",
            f"- 疾病/表型背景：{disease}",
            f"- 提名分子数：{min(final_count, len(cards))}",
            f"- 官方化合物库 SHA-256：`{library_sha256}`",
            "- 排序是计算证据综合，不是实验确认结果。",
            "- 缺失毒性证据标记为 unknown，不得解释为低毒。",
            "",
            "## 排序方法",
            "",
            "降脂证据 30%、机制/通路一致性 20%、活性质量 15%、安全性 20%、结构/成药性 10%、化学多样性 5%；缺失或冲突证据最多扣除 20 个不确定性分。",
            "",
            "## 候选分子",
            "",
        ]
    for rank, card in enumerate(cards[:final_count], 1):
        if english:
            candidate_lines = [
                f"### {rank}. {card.name or card.library_id}",
                "",
                f"- Library ID: `{card.library_id}`",
                f"- Parent InChIKey: `{card.parent_inchikey or 'missing'}`",
                f"- Final score: {card.score.final_score:.2f}; uncertainty penalty: "
                f"{card.score.uncertainty_penalty:.2f}",
                f"- Score components: lipid={card.score.lipid_evidence:.2f}; "
                f"mechanism={card.score.mechanism_relevance:.2f}; "
                f"activity={card.score.activity_quality:.2f}; safety={card.score.safety:.2f}; "
                f"developability={card.score.structure_developability:.2f}; "
                f"diversity={card.score.diversity:.2f}",
                f"- Toxicity evidence status: `{_toxicity_evidence_status(card)}`",
                f"- Lipid rationale: {card.lipid_rationale or 'No verified rationale supplied.'}",
                f"- Toxicity: {card.toxicity_rationale}",
                f"- Mechanism: {_mechanism_text(card)}",
                f"- Evidence references: {'; '.join(dict.fromkeys(card.provenance.get('evidence_refs') or [])) or 'none'}",
                f"- Alternatives/falsifiers: "
                f"{'; '.join(item for mechanism in card.mechanism_hypotheses for item in mechanism.falsifiers) or 'Not yet specified.'}",
                "- Validation: concentration-response HepG2-FFA lipid readout together with "
                "matched cell-viability and morphology controls; follow with mechanism-specific "
                "target engagement, expression/phosphorylation, or flux readouts.",
                "",
            ]
        else:
            candidate_lines = [
                f"### {rank}. {card.name or card.library_id}",
                "",
                f"- 库内 ID：`{card.library_id}`",
                f"- Parent InChIKey：`{card.parent_inchikey or 'missing'}`",
                f"- 最终得分：{card.score.final_score:.2f}；不确定性扣分：{card.score.uncertainty_penalty:.2f}",
                f"- 得分构成：降脂={card.score.lipid_evidence:.2f}；机制={card.score.mechanism_relevance:.2f}；活性={card.score.activity_quality:.2f}；安全性={card.score.safety:.2f}；成药性={card.score.structure_developability:.2f}；多样性={card.score.diversity:.2f}",
                f"- 毒性证据状态：`{_toxicity_evidence_status(card)}`",
                f"- 降脂依据：{card.lipid_rationale or '未提供可核验依据。'}",
                f"- 毒性依据：{card.toxicity_rationale}",
                f"- 机制假说：{_mechanism_text(card)}",
                f"- 证据引用：{'; '.join(dict.fromkeys(card.provenance.get('evidence_refs') or [])) or '无'}",
                f"- 替代机制/证伪条件：{'; '.join(item for mechanism in card.mechanism_hypotheses for item in mechanism.falsifiers) or '尚未指定。'}",
                "- 验证方案：浓度-反应 HepG2-FFA 脂质读出，同时进行匹配的细胞活力和形态对照；再做机制特异性的靶点参与、表达/磷酸化或通量读出。",
                "",
            ]
        lines.extend(candidate_lines)
    if english:
        lines.extend(
            [
                "## Shared validation controls",
                "",
                "- Vehicle and assay-appropriate positive controls.",
                "- Matched exposure time and concentration series for lipid and viability readouts.",
                "- Reject apparent lipid lowering caused by loss of viable cells.",
                "- Test SREBP-1c/ACC/FASN/SCD1, PPARα/AMPK/CPT1, uptake/efflux, or autophagy only when candidate-specific evidence supports that branch.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "## 共用验证对照",
                "",
                "- 设置 vehicle 和适用的阳性对照。",
                "- 脂质与活力读出使用匹配的暴露时间和浓度梯度。",
                "- 排除由活细胞数量下降造成的表观降脂。",
                "- 仅在候选证据支持时检测 SREBP-1c/ACC/FASN/SCD1、PPARα/AMPK/CPT1、摄取/外排或自噬通路。",
                "",
            ]
        )
    path.write_text("\n".join(lines), encoding="utf-8")


def run_evidence_nomination(
    library_path: Path,
    output_dir: Path,
    *,
    final_count: int = 10,
    disease: str = "MASLD",
    target_gene: Optional[str] = None,
    online: bool = False,
    offline_replay: bool = False,
    online_enrichment_limit: int = 50,
    library_source: str = "official_sdf_library",
    mechanism_is_target_based: bool = True,
    language: str = "zh",
) -> Path:
    """Run E0-E6 and write deterministic stage reports and nomination artifacts."""
    library_path = Path(library_path).resolve()
    output_dir = Path(output_dir).resolve()
    if final_count < 1:
        raise ValueError("final_count must be >= 1")
    if not library_path.is_file():
        raise FileNotFoundError(library_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    language = normalize_output_language(language)
    evidence_http = CachedHttp(cache_only=offline_replay)
    evidence_enabled = online or offline_replay
    input_sha256 = hashlib.sha256(library_path.read_bytes()).hexdigest()
    task_plan = {
        "evidence_stages": list(EVIDENCE_STAGES),
        "compute_stages": "H0-H10 unchanged; invoke separately when applicable",
        "library_path": str(library_path),
        "library_sha256": input_sha256,
        "library_source": library_source,
        "disease": disease,
        "target_gene": target_gene,
        "final_count": final_count,
        "online": online,
        "offline_replay": offline_replay,
        "structure_policy": "research_then_conditional_docking",
        "language": language,
    }
    _json_write(output_dir / "evidence_task_plan.json", task_plan)
    _stage_report(
        output_dir,
        "E0_scope",
        status="completed",
        summary=f"Locked library identity, disease context, and final count {final_count}.",
        artifacts=[output_dir / "evidence_task_plan.json"],
    )

    target_card = None
    structures: list[StructureCandidate] = []
    selected_structure = None
    if target_gene:
        target_card = build_target_evidence_card(
            target_gene,
            disease,
            online=evidence_enabled,
            http=evidence_http,
        )
        if evidence_enabled:
            try:
                structures = discover_structure_candidates(
                    gene=target_card.gene_symbol,
                    uniprot_id=target_card.uniprot_id,
                    http=evidence_http,
                )
            except Exception as exc:  # noqa: BLE001
                target_card.warnings.append(f"structure_discovery_failed:{exc}")
        selected_structure = structures[0] if structures and structures[0].evidence_level != EvidenceLevel.U else None
    target_payload = (
        target_card.model_dump(mode="json")
        if target_card
        else {
            "mode": "phenotype_first",
            "disease": disease,
            "warning": "No target supplied; target/pathway deconvolution remains required.",
        }
    )
    _json_write(output_dir / "target_evidence.json", target_payload)
    _stage_report(
        output_dir,
        "E1_target_biology",
        status="completed" if target_card else "not_applicable",
        summary="Target evidence card written." if target_card else "Phenotype-first nomination selected.",
        artifacts=[output_dir / "target_evidence.json"],
        warnings=target_card.warnings if target_card else ["target_not_supplied"],
    )

    _write_structure_csv(output_dir / "structure_candidates.csv", structures)
    _json_write(
        output_dir / "selected_structure.json",
        selected_structure.model_dump(mode="json")
        if selected_structure
        else {"selected": None, "reason": "no_qualified_experimental_structure"},
    )
    _stage_report(
        output_dir,
        "E2_structure_reconnaissance",
        status="completed" if structures else "not_applicable",
        summary=f"Ranked {len(structures)} experimental structure candidates.",
        artifacts=[output_dir / "structure_candidates.csv", output_dir / "selected_structure.json"],
        warnings=[] if structures else ["no_structure_candidates"],
    )

    pocket: PocketQualification = qualify_pocket(
        selected_structure,
        target_gene=target_gene or "phenotype_first",
        mechanism_is_target_based=mechanism_is_target_based and bool(target_gene),
    )
    _json_write(output_dir / "pocket_manifest.json", pocket.model_dump(mode="json"))
    _stage_report(
        output_dir,
        "E3_pocket_qualification",
        status="completed" if pocket.qualified else "not_applicable",
        summary=f"Docking recommendation: {pocket.docking_recommendation}.",
        artifacts=[output_dir / "pocket_manifest.json"],
        warnings=pocket.rejection_reasons,
    )

    cards = load_compound_library(library_path, library_source=library_source)
    if evidence_enabled:
        enrich_cards_online(cards, limit=online_enrichment_limit, http=evidence_http)
    ranked = rank_compounds(cards)
    valid_ranked = [
        card for card in ranked if card.identity_valid and card.parent_inchikey
    ]
    dump_cards_jsonl(ranked, output_dir / "compound_evidence.jsonl")
    _stage_report(
        output_dir,
        "E4_compound_enrichment",
        status="completed",
        summary=f"Standardized {len(cards)} library records; retained exact parent identities.",
        artifacts=[output_dir / "compound_evidence.jsonl"],
        warnings=["online_enrichment_capped"]
        if evidence_enabled and len(cards) > online_enrichment_limit
        else [],
    )

    _write_toxicity_csv(output_dir / "toxicity_evidence.csv", ranked)
    _stage_report(
        output_dir,
        "E5_toxicity_triage",
        status="completed",
        summary="Separated observed, predicted, and unknown toxicity evidence.",
        artifacts=[output_dir / "toxicity_evidence.csv"],
    )

    _write_scorecards(
        output_dir,
        valid_ranked,
        final_count,
        library_sha256=input_sha256,
    )
    _write_mechanism_report(
        output_dir / "mechanism_validation.md",
        valid_ranked,
        disease=disease,
        final_count=final_count,
        library_sha256=input_sha256,
        language=language,
    )
    (output_dir / "proposal.md").write_text(
        (output_dir / "mechanism_validation.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    if language == "en":
        method_lines = [
            "# Reproducible nomination method",
            "",
            f"- Input library SHA-256: `{input_sha256}`",
            f"- Library source: `{library_source}`",
            f"- Output language: `{language}`",
            f"- Online evidence: `{online}`",
            f"- Requested final count: `{final_count}`",
            "- Identity: RDKit parent standardization, parent InChIKey deduplication, stable library-ID tie-break.",
            "- Ranking: lipid 30%, mechanism 20%, activity 15%, safety 20%, structure/developability 10%, diversity 5%, with up to 20 uncertainty points.",
            "- Structure policy: research first; docking only after pocket qualification.",
            "- Validation: HepG2-FFA lipid accumulation plus matched cell viability; cytotoxic lipid-loss signals are rejected.",
            "- Missing evidence remains unknown and is not converted into favorable evidence.",
            "",
        ]
    else:
        method_lines = [
            "# 可复现的候选提名方法",
            "",
            f"- 输入化合物库 SHA-256：`{input_sha256}`",
            f"- 化合物库来源：`{library_source}`",
            f"- 输出语言：`{language}`（默认中文；可切换为 en）",
            f"- 在线证据：`{online}`",
            f"- 请求最终数量：`{final_count}`",
            "- 身份标准化：使用 RDKit 做 parent 标准化、parent InChIKey 去重，并用稳定的 library ID 做并列排序。",
            "- 排序：降脂 30%、机制 20%、活性 15%、安全性 20%、结构/成药性 10%、多样性 5%，最多扣除 20 个不确定性分。",
            "- 结构策略：先做结构和口袋研究，只有口袋合格后才允许对接。",
            "- 验证：HepG2-FFA 脂质蓄积与匹配的细胞活力双读出；排除伴随细胞毒性的降脂假阳性。",
            "- 缺失证据保持 unknown，不转换为有利证据。",
            "",
        ]
    (output_dir / "method.md").write_text("\n".join(method_lines), encoding="utf-8")
    from masld_agent.submission import write_hepg2_plan

    write_hepg2_plan(output_dir, language=language)
    competition_config = load_competition_config(DEFAULT_COMPETITION)
    nomination_contract = {
        "library_source": library_source,
        "library_sha256": input_sha256,
        "weights": DEFAULT_NOMINATION_WEIGHTS,
        "uncertainty_penalty_max": 20,
        "selection_rule": "rank valid unique parent identities by final_score descending, then library_id",
        "effective_hit_rule": (competition_config.get("experimental_readouts") or {}).get(
            "effective_hit_definition"
        ),
        "experimental_validation_plan": competition_config.get("experimental_validation_plan") or {},
        "language": language,
    }
    _json_write(output_dir / "nomination_contract.json", nomination_contract)
    pdf_status = try_export_pdf(
        output_dir / "mechanism_validation.md", output_dir / "mechanism_validation.pdf"
    )
    (output_dir / "mechanism_validation_pdf_status.txt").write_text(
        pdf_status + "\n", encoding="utf-8"
    )
    provenance = {
        "input": {"path": str(library_path), "sha256": input_sha256},
        "sources": [
            "official compound library",
            "RDKit local descriptors and structural alerts",
            *(
                [
                    "UniProt",
                    "RCSB PDB",
                    "Reactome",
                    "Europe PMC",
                    "Open Targets",
                    "PubChem",
                    "ChEMBL",
                ]
                if evidence_enabled
                else []
            ),
        ],
        "weights": DEFAULT_NOMINATION_WEIGHTS,
        "uncertainty_penalty_max": 20,
        "online_enrichment_limit": online_enrichment_limit,
        "evidence_mode": "cache_replay" if offline_replay else "online" if online else "offline",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    _json_write(output_dir / "evidence_provenance.json", provenance)
    manifest = {
        "run_type": "evidence_nomination",
        "stages": list(EVIDENCE_STAGES),
        "library_path": str(library_path),
        "library_source": library_source,
        "library_sha256": input_sha256,
        "language": language,
        "disease": disease,
        "target_gene": target_gene,
        "final_count": final_count,
        "online": online,
        "offline_replay": offline_replay,
        "generated_at": provenance["generated_at"],
    }
    _json_write(output_dir / "manifest.json", manifest)
    machine_report = {
        "competition": {
            "preset": "AI4S life science" if disease.upper() == "MASLD" else "generic",
            "disease": disease,
        },
        "competition_scope_warning": (
            "Use the active competition brief and do not conflate MASLD lipid lowering with "
            "other liver-disease objectives."
        ),
        "targets": [],
        "target_evidence": target_payload,
        "nominations": [
            card.model_dump(mode="json") for card in valid_ranked[:final_count]
        ],
        "evidence_provenance": provenance,
        "nomination_contract": nomination_contract,
        "experimental_validation_plan": nomination_contract["experimental_validation_plan"],
    }
    _json_write(output_dir / "machine_readable_report.json", machine_report)
    all_warnings = list(
        dict.fromkeys(
            warning
            for card in ranked
            for warning in card.warnings
        )
    )
    (output_dir / "warnings.md").write_text(
        "# Warnings\n\n"
        + "\n".join(f"- {warning}" for warning in all_warnings)
        + ("\n" if all_warnings else "- none\n"),
        encoding="utf-8",
    )
    _stage_report(
        output_dir,
        "E6_nomination_reporting",
        status="completed" if len(valid_ranked) >= final_count else "incomplete",
        summary=(
            f"Ranked {len(ranked)} records and found {len(valid_ranked)} valid unique parents; "
            f"nominated up to {final_count}."
        ),
        artifacts=[
            output_dir / "nomination_scorecard.csv",
            output_dir / "top10_nomination.csv",
            output_dir / "mechanism_validation.md",
            output_dir / "mechanism_validation.pdf",
            output_dir / "evidence_provenance.json",
            output_dir / "hepg2_validation_plan.md",
            output_dir / "nomination_contract.json",
            output_dir / "machine_readable_report.json",
            output_dir / "manifest.json",
        ],
        warnings=[]
        if len(valid_ranked) >= final_count
        else ["fewer_valid_unique_candidates_than_requested"],
    )
    return output_dir
