"""Optional ChEMBL client."""
from __future__ import annotations

from typing import Any, Optional

from masld_agent.http_cache import CachedHttp
from masld_agent.models import EvidenceLevel, LigandRole, ReferenceLigand


def fetch_chembl_molecule(chembl_id: str, *, http: Optional[CachedHttp] = None) -> dict[str, Any]:
    client = http or CachedHttp()
    url = f"https://www.ebi.ac.uk/chembl/api/data/molecule/{chembl_id}.json"
    return client.get_json(url)


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
