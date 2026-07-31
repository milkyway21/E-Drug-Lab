"""Compound-library normalization, evidence preservation, toxicity triage, and ranking."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable, Optional

from rdkit import Chem, DataStructs
from rdkit.Chem import AllChem, Crippen, Descriptors, Lipinski, rdMolDescriptors
from rdkit.Chem.MolStandardize import rdMolStandardize

from masld_agent.models import (
    CompoundEvidenceCard,
    EvidenceLevel,
    MechanismHypothesis,
    NominationScoreBreakdown,
    SafetyEvidence,
)


DEFAULT_NOMINATION_WEIGHTS = {
    "lipid_evidence": 0.30,
    "mechanism_relevance": 0.20,
    "activity_quality": 0.15,
    "safety": 0.20,
    "structure_developability": 0.10,
    "diversity": 0.05,
}

STRUCTURE_ALERTS = {
    "aldehyde": "[CX3H1](=O)[#6]",
    "michael_acceptor": "[C,c]=[C,c]-[C,S](=O)[#6,#7,#8]",
    "epoxide": "[OX2r3]1[CX4r3][CX4r3]1",
    "alkyl_halide": "[CX4][Cl,Br,I]",
    "hydrazine": "[NX3][NX3]",
}

ALIASES = {
    "library_id": ("library_id", "id", "ID", "molecule_id", "compound_id", "title"),
    "name": ("name", "Name", "compound_name", "pref_name"),
    "smiles": ("canonical_smiles", "smiles", "SMILES", "structure"),
    "inchikey": ("parent_inchikey", "inchikey", "InChIKey", "INCHIKEY"),
}


def _first(record: dict[str, Any], names: Iterable[str]) -> Optional[str]:
    for name in names:
        value = record.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _float(record: dict[str, Any], names: Iterable[str]) -> Optional[float]:
    value = _first(record, names)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _split_values(value: Optional[str]) -> list[str]:
    if not value:
        return []
    normalized = value.replace("|", ";")
    return [part.strip() for part in normalized.split(";") if part.strip()]


def _standardize(smiles: Optional[str]) -> tuple[Optional[Chem.Mol], Optional[str], Optional[str]]:
    if not smiles:
        return None, None, None
    molecule = Chem.MolFromSmiles(smiles)
    if molecule is None:
        return None, None, None
    try:
        parent = rdMolStandardize.FragmentParent(molecule)
        Chem.SanitizeMol(parent)
    except (ValueError, RuntimeError):
        parent = molecule
    canonical = Chem.MolToSmiles(parent, canonical=True, isomericSmiles=True)
    inchikey = Chem.MolToInchiKey(parent)
    return parent, canonical, inchikey or None


def _properties(molecule: Chem.Mol) -> dict[str, Optional[float]]:
    return {
        "mw": round(float(Descriptors.MolWt(molecule)), 4),
        "logp": round(float(Crippen.MolLogP(molecule)), 4),
        "tpsa": round(float(rdMolDescriptors.CalcTPSA(molecule)), 4),
        "hbd": float(Lipinski.NumHDonors(molecule)),
        "hba": float(Lipinski.NumHAcceptors(molecule)),
        "rotatable_bonds": float(Lipinski.NumRotatableBonds(molecule)),
        "fraction_csp3": round(float(rdMolDescriptors.CalcFractionCSP3(molecule)), 4),
    }


def _alerts(molecule: Chem.Mol) -> list[str]:
    matches: list[str] = []
    for name, smarts in STRUCTURE_ALERTS.items():
        pattern = Chem.MolFromSmarts(smarts)
        if pattern is not None and molecule.HasSubstructMatch(pattern):
            matches.append(name)
    return matches


def _developability_score(properties: dict[str, Optional[float]]) -> float:
    rules = [
        (properties.get("mw"), lambda value: 100.0 <= value <= 550.0),
        (properties.get("logp"), lambda value: -1.0 <= value <= 5.0),
        (properties.get("tpsa"), lambda value: value <= 140.0),
        (properties.get("hbd"), lambda value: value <= 5.0),
        (properties.get("hba"), lambda value: value <= 10.0),
    ]
    passed = sum(1 for value, rule in rules if value is not None and rule(value))
    return 20.0 * passed


def compound_card_from_record(
    record: dict[str, Any],
    *,
    index: int,
    library_source: str,
) -> CompoundEvidenceCard:
    supplied_smiles = _first(record, ALIASES["smiles"])
    molecule, canonical, computed_inchikey = _standardize(supplied_smiles)
    library_id = _first(record, ALIASES["library_id"]) or f"LIB_{index:06d}"
    name = _first(record, ALIASES["name"])
    supplied_inchikey = _first(record, ALIASES["inchikey"])
    warnings: list[str] = []
    if molecule is None:
        warnings.append("invalid_or_missing_structure")
    if supplied_inchikey and computed_inchikey and supplied_inchikey != computed_inchikey:
        warnings.append("supplied_inchikey_differs_from_standardized_parent")
    properties = _properties(molecule) if molecule is not None else {}
    alerts = _alerts(molecule) if molecule is not None else []
    lipid_rationale = _first(record, ("lipid_rationale", "lipid_evidence")) or ""
    toxicity_rationale = _first(record, ("tox_rationale", "toxicity_rationale")) or ""
    targets = _split_values(_first(record, ("target_or_pathway", "targets", "pathways")))
    evidence_refs = _split_values(_first(record, ("evidence_refs", "references")))
    mechanism_text = _first(record, ("mechanism_hypothesis", "mechanism")) or ""
    mechanism: list[MechanismHypothesis] = []
    if mechanism_text:
        mechanism.append(
            MechanismHypothesis(
                intervention=name or library_id,
                direct_action=mechanism_text,
                target_or_pathway="; ".join(targets) or "unresolved",
                expected_direction=_first(record, ("expected_direction",)) or "to_be_tested",
                lipid_phenotype="reduced lipid accumulation",
                evidence_refs=evidence_refs,
                alternative_mechanisms=_split_values(
                    _first(record, ("alternative_mechanisms",))
                ),
                falsifiers=_split_values(_first(record, ("falsifiers",))),
                validation_readouts=_split_values(
                    _first(record, ("validation_readouts",))
                ),
            )
        )
    safety_evidence = [
        SafetyEvidence(
            source="structural_alert",
            evidence_level=EvidenceLevel.D,
            confidence=0.45,
            warnings=["alert_is_not_observed_toxicity"],
            provenance={"smarts_alert": alert},
            endpoint="reactive_structure_alert",
            result=alert,
            severity="potential",
            prediction=True,
            applicability="structure_based",
        )
        for alert in alerts
    ]
    qplogherg = _float(record, ("QPlogHERG", "qplogherg"))
    qikprop_stars = _float(record, ("#stars", "qikprop_stars"))
    if qplogherg is not None:
        safety_evidence.append(
            SafetyEvidence(
                source="schrodinger_qikprop",
                evidence_level=EvidenceLevel.D,
                confidence=0.55,
                warnings=["prediction_not_observed_cardiotoxicity"],
                provenance={"QPlogHERG": qplogherg},
                endpoint="predicted_hERG_logIC50",
                result=str(qplogherg),
                severity="higher_concern" if qplogherg < -5 else "lower_predicted_concern",
                prediction=True,
                applicability="qikprop_model",
            )
        )
    cell_viability = _float(record, ("cell_viability", "viability_percent"))
    if cell_viability is not None:
        safety_evidence.append(
            SafetyEvidence(
                source=_first(record, ("viability_source", "assay_source")) or "library_annotation",
                evidence_level=EvidenceLevel.C,
                confidence=0.75,
                warnings=[],
                provenance={
                    "concentration": _first(record, ("viability_concentration",)),
                    "exposure": _first(record, ("viability_exposure",)),
                },
                endpoint="cell_viability_percent",
                result=str(cell_viability),
                severity="higher_concern" if cell_viability < 70 else "lower_observed_concern",
                observed=True,
                applicability="assay_context_required",
            )
        )
    explicit_scores = {
        "lipid_evidence": _float(record, ("lipid_score", "lipid_evidence_score")),
        "mechanism_relevance": _float(record, ("mechanism_score", "mechanism_relevance_score")),
        "activity_quality": _float(record, ("activity_score", "activity_quality_score")),
        "safety": _float(record, ("safety_score", "toxicity_score")),
        "structure_developability": _float(
            record, ("developability_score", "structure_developability_score")
        ),
        "diversity": _float(record, ("diversity_score",)),
    }
    inferred = {
        "lipid_evidence": 70.0 if lipid_rationale and evidence_refs else 40.0 if lipid_rationale else 0.0,
        "mechanism_relevance": 75.0 if mechanism and targets else 45.0 if mechanism or targets else 0.0,
        "activity_quality": 60.0 if _first(record, ("assay_id", "activity_value")) else 0.0,
        "safety": (
            max(
                0.0,
                60.0
                - 10.0 * len(alerts)
                - (20.0 if qplogherg is not None and qplogherg < -5 else 0.0)
                - (10.0 if qikprop_stars is not None and qikprop_stars >= 8 else 0.0)
                + (
                    15.0
                    if cell_viability is not None and cell_viability >= 80
                    else -25.0
                    if cell_viability is not None and cell_viability < 70
                    else 0.0
                ),
            )
            if molecule is not None
            else 0.0
        ),
        "structure_developability": _developability_score(properties) if molecule is not None else 0.0,
        "diversity": 50.0,
    }
    values = {
        key: max(0.0, min(100.0, explicit_scores[key] if explicit_scores[key] is not None else value))
        for key, value in inferred.items()
    }
    missing = [
        not lipid_rationale,
        not toxicity_rationale,
        not mechanism,
        not targets,
        not evidence_refs,
    ]
    uncertainty_penalty = min(20.0, 4.0 * sum(missing))
    weighted_total = sum(values[key] * weight for key, weight in DEFAULT_NOMINATION_WEIGHTS.items())
    score = NominationScoreBreakdown(
        **values,
        uncertainty_penalty=uncertainty_penalty,
        weighted_total=round(weighted_total, 4),
        final_score=round(max(0.0, weighted_total - uncertainty_penalty), 4),
        weights=DEFAULT_NOMINATION_WEIGHTS,
    )
    if not toxicity_rationale:
        toxicity_parts: list[str] = []
        if alerts:
            toxicity_parts.append(f"Predicted structural alerts: {', '.join(alerts)}")
        if qplogherg is not None:
            toxicity_parts.append(f"QikProp QPlogHERG={qplogherg:g} (prediction)")
        if cell_viability is not None:
            toxicity_parts.append(
                f"Observed cell viability={cell_viability:g}% in the supplied assay context"
            )
        toxicity_rationale = (
            "; ".join(toxicity_parts)
            if toxicity_parts
            else "No observed toxicity evidence supplied; safety remains unknown."
        )
    return CompoundEvidenceCard(
        source="official_library",
        evidence_level=EvidenceLevel.D,
        confidence=max(0.0, min(1.0, score.final_score / 100.0)),
        warnings=warnings,
        provenance={"input_record": record, "evidence_refs": evidence_refs},
        library_id=library_id,
        library_source=library_source,
        name=name,
        canonical_smiles=canonical,
        parent_inchikey=computed_inchikey or supplied_inchikey,
        molecular_properties=properties,
        structure_alerts=alerts,
        target_or_pathway=targets,
        lipid_rationale=lipid_rationale,
        toxicity_rationale=toxicity_rationale,
        safety_evidence=safety_evidence,
        mechanism_hypotheses=mechanism,
        score=score,
        structure_applicability=_first(record, ("structure_applicability",)) or "not_assessed",
        identity_valid=molecule is not None,
    )


def _read_records(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix in {".csv", ".tsv"}:
        delimiter = "\t" if suffix == ".tsv" else ","
        with path.open(newline="", encoding="utf-8-sig") as stream:
            return [dict(row) for row in csv.DictReader(stream, delimiter=delimiter)]
    if suffix in {".smi", ".smiles"}:
        records: list[dict[str, Any]] = []
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            parts = line.split()
            records.append(
                {"smiles": parts[0], "library_id": parts[1] if len(parts) > 1 else str(index)}
            )
        return records
    if suffix in {".sdf", ".sd"}:
        records = []
        supplier = Chem.SDMolSupplier(str(path), removeHs=False)
        for index, molecule in enumerate(supplier, 1):
            if molecule is None:
                records.append({"library_id": f"INVALID_{index:06d}"})
                continue
            record = {name: molecule.GetProp(name) for name in molecule.GetPropNames()}
            record.setdefault("library_id", molecule.GetProp("_Name") or f"LIB_{index:06d}")
            record["smiles"] = Chem.MolToSmiles(molecule, isomericSmiles=True)
            records.append(record)
        return records
    raise ValueError(f"unsupported compound library format: {path.suffix}")


def load_compound_library(
    path: Path,
    *,
    library_source: str = "official_sdf_library",
) -> list[CompoundEvidenceCard]:
    records = _read_records(Path(path))
    return [
        compound_card_from_record(record, index=index, library_source=library_source)
        for index, record in enumerate(records, 1)
    ]


def apply_diversity_scores(cards: list[CompoundEvidenceCard]) -> None:
    fingerprints: list[Optional[Any]] = []
    for card in cards:
        molecule = Chem.MolFromSmiles(card.canonical_smiles or "")
        fingerprints.append(
            AllChem.GetMorganGenerator(radius=2, fpSize=2048).GetFingerprint(molecule)
            if molecule is not None
            else None
        )
    for index, card in enumerate(cards):
        fingerprint = fingerprints[index]
        similarities = [
            DataStructs.TanimotoSimilarity(fingerprint, other)
            for other_index, other in enumerate(fingerprints)
            if fingerprint is not None and other is not None and other_index != index
        ]
        diversity = 100.0 * (1.0 - max(similarities)) if similarities else 100.0
        old_value = card.score.diversity
        card.score.diversity = round(diversity, 4)
        weighted = card.score.weighted_total + (diversity - old_value) * DEFAULT_NOMINATION_WEIGHTS[
            "diversity"
        ]
        card.score.weighted_total = round(max(0.0, min(100.0, weighted)), 4)
        card.score.final_score = round(
            max(0.0, card.score.weighted_total - card.score.uncertainty_penalty), 4
        )


def rank_compounds(cards: list[CompoundEvidenceCard]) -> list[CompoundEvidenceCard]:
    apply_diversity_scores(cards)
    unique: dict[str, CompoundEvidenceCard] = {}
    invalid: list[CompoundEvidenceCard] = []
    for card in cards:
        if not card.identity_valid or not card.parent_inchikey:
            invalid.append(card)
            continue
        current = unique.get(card.parent_inchikey)
        if current is None or card.score.final_score > current.score.final_score:
            unique[card.parent_inchikey] = card
    ranked = sorted(
        unique.values(),
        key=lambda card: (-card.score.final_score, card.library_id),
    )
    return ranked + sorted(invalid, key=lambda card: card.library_id)


def dump_cards_jsonl(cards: list[CompoundEvidenceCard], path: Path) -> None:
    with Path(path).open("w", encoding="utf-8") as stream:
        for card in cards:
            stream.write(json.dumps(card.model_dump(mode="json"), ensure_ascii=False) + "\n")
