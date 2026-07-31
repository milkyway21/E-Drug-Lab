"""PubChem PUG-REST helpers."""
from __future__ import annotations

from typing import Any, Optional

from masld_agent.http_cache import CachedHttp
from masld_agent.models import EvidenceLevel, LigandRole, ReferenceLigand


def fetch_compound_property_table(
    cid: int,
    *,
    http: Optional[CachedHttp] = None,
) -> dict[str, Any]:
    client = http or CachedHttp()
    url = (
        f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/property/"
        "MolecularFormula,MolecularWeight,CanonicalSMILES,IsomericSMILES,InChIKey,IUPACName/JSON"
    )
    return client.get_json(url)


def fetch_compound_by_inchikey(
    inchikey: str,
    *,
    http: Optional[CachedHttp] = None,
) -> dict[str, Any]:
    client = http or CachedHttp(min_interval_s=0.21)
    url = (
        f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/inchikey/{inchikey}/property/"
        "MolecularFormula,MolecularWeight,CanonicalSMILES,IsomericSMILES,InChIKey,IUPACName/JSON"
    )
    return client.get_json(url)


def ligand_from_pubchem(
    cid: int,
    *,
    name: str,
    role: LigandRole = LigandRole.COMPUTATIONAL,
    http: Optional[CachedHttp] = None,
) -> ReferenceLigand:
    data = fetch_compound_property_table(cid, http=http)
    props = ((data.get("PropertyTable") or {}).get("Properties") or [{}])[0]
    return ReferenceLigand(
        source="pubchem",
        evidence_level=EvidenceLevel.A,
        confidence=0.85,
        warnings=[],
        provenance={"cid": cid},
        name=name or props.get("IUPACName") or f"CID:{cid}",
        pubchem_cid=cid,
        smiles=props.get("CanonicalSMILES") or props.get("IsomericSMILES"),
        inchikey=props.get("InChIKey"),
        role=role,
    )


def ligand_from_fixture(rec: dict[str, Any]) -> ReferenceLigand:
    role = LigandRole(rec.get("role", LigandRole.COMPUTATIONAL.value))
    warnings = []
    if not rec.get("smiles"):
        warnings.append("smiles_null_offline_fetch_pubchem_when_online")
    return ReferenceLigand(
        source="fixture:pubchem",
        evidence_level=EvidenceLevel.A,
        confidence=0.95,
        warnings=warnings,
        provenance=rec.get("provenance") or {},
        name=rec["name"],
        pubchem_cid=rec.get("pubchem_cid"),
        chembl_id=rec.get("chembl_id"),
        smiles=rec.get("smiles"),
        inchikey=rec.get("inchikey"),
        role=role,
        activity_type=rec.get("activity_type"),
        activity_value=rec.get("activity_value"),
        assay_source=rec.get("assay_source"),
    )


def parse_pubchem_properties(data: dict[str, Any]) -> dict[str, Any]:
    props = ((data.get("PropertyTable") or {}).get("Properties") or [{}])[0]
    return {
        "cid": props.get("CID"),
        "smiles": props.get("CanonicalSMILES") or props.get("IsomericSMILES"),
        "inchikey": props.get("InChIKey"),
        "iupac": props.get("IUPACName"),
        "mw": props.get("MolecularWeight"),
    }
