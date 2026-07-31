"""Optional ChEMBL client."""
from __future__ import annotations

from typing import Any, Optional

from masld_agent.http_cache import CachedHttp
from masld_agent.models import ActivityEvidence, EvidenceLevel, LigandRole, ReferenceLigand


def fetch_chembl_molecule(chembl_id: str, *, http: Optional[CachedHttp] = None) -> dict[str, Any]:
    client = http or CachedHttp()
    url = f"https://www.ebi.ac.uk/chembl/api/data/molecule/{chembl_id}.json"
    return client.get_json(url)


def find_chembl_molecule_by_inchikey(
    inchikey: str,
    *,
    http: Optional[CachedHttp] = None,
) -> Optional[dict[str, Any]]:
    client = http or CachedHttp()
    data = client.get_json(
        "https://www.ebi.ac.uk/chembl/api/data/molecule.json",
        params={"molecule_structures__standard_inchi_key": inchikey, "limit": "5"},
    )
    molecules = data.get("molecules") or []
    exact = [
        item
        for item in molecules
        if ((item.get("molecule_structures") or {}).get("standard_inchi_key") or "").upper()
        == inchikey.upper()
    ]
    return exact[0] if exact else None


def fetch_chembl_activities(
    chembl_id: str,
    *,
    limit: int = 100,
    http: Optional[CachedHttp] = None,
) -> list[ActivityEvidence]:
    client = http or CachedHttp()
    data = client.get_json(
        "https://www.ebi.ac.uk/chembl/api/data/activity.json",
        params={
            "molecule_chembl_id": chembl_id,
            "limit": str(min(max(limit, 1), 1000)),
        },
    )
    records: list[ActivityEvidence] = []
    for activity in data.get("activities") or []:
        standard_value = None
        pchembl_value = None
        try:
            if activity.get("standard_value") is not None:
                standard_value = float(activity["standard_value"])
        except (TypeError, ValueError):
            pass
        try:
            if activity.get("pchembl_value") is not None:
                pchembl_value = float(activity["pchembl_value"])
        except (TypeError, ValueError):
            pass
        records.append(
            ActivityEvidence(
                source="chembl",
                evidence_level=EvidenceLevel.B,
                confidence=0.75 if activity.get("data_validity_comment") is None else 0.5,
                warnings=[activity["data_validity_comment"]]
                if activity.get("data_validity_comment")
                else [],
                provenance={
                    "activity_id": activity.get("activity_id"),
                    "bao_label": activity.get("bao_label"),
                    "src_id": activity.get("src_id"),
                },
                target=activity.get("target_pref_name") or activity.get("target_chembl_id"),
                assay_id=activity.get("assay_chembl_id"),
                assay_type=activity.get("assay_type"),
                assay_description=activity.get("assay_description"),
                organism=activity.get("target_organism") or activity.get("assay_organism"),
                standard_type=activity.get("standard_type"),
                standard_relation=activity.get("standard_relation"),
                standard_value=standard_value,
                standard_units=activity.get("standard_units"),
                pchembl_value=pchembl_value,
                document_id=activity.get("document_chembl_id"),
            )
        )
    return records


def ligand_from_chembl(
    chembl_id: str,
    *,
    name: Optional[str] = None,
    http: Optional[CachedHttp] = None,
) -> ReferenceLigand:
    data = fetch_chembl_molecule(chembl_id, http=http)
    structs = data.get("molecule_structures") or {}
    return ReferenceLigand(
        source="chembl",
        evidence_level=EvidenceLevel.B,
        confidence=0.75,
        warnings=[],
        provenance={"chembl_id": chembl_id},
        name=name or data.get("pref_name") or chembl_id,
        chembl_id=chembl_id,
        smiles=structs.get("canonical_smiles"),
        inchikey=structs.get("standard_inchi_key"),
        role=LigandRole.BIOCHEMICAL,
    )
