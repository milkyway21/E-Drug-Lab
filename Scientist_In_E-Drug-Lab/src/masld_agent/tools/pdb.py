"""RCSB PDB structure retrieval and pocket heuristics."""
from __future__ import annotations

from typing import Any, Optional

from masld_agent.http_cache import CachedHttp
from masld_agent.models import BindingPocket, EvidenceLevel, ProteinStructure


def fetch_pdb_entry(pdb_id: str, *, http: Optional[CachedHttp] = None) -> dict[str, Any]:
    client = http or CachedHttp()
    pid = pdb_id.strip().upper()
    return client.get_json(f"https://data.rcsb.org/rest/v1/core/entry/{pid}")


def structure_from_rcsb(pdb_id: str, *, http: Optional[CachedHttp] = None) -> ProteinStructure:
    data = fetch_pdb_entry(pdb_id, http=http)
    reso = None
    try:
        reso = float(
            ((data.get("rcsb_entry_info") or {}).get("resolution_combined") or [None])[0]
        )
    except (TypeError, ValueError, IndexError):
        reso = None
    method = None
    methods = (data.get("exptl") or [])
    if methods:
        method = methods[0].get("method")
    return ProteinStructure(
        source="rcsb",
        evidence_level=EvidenceLevel.A,
        confidence=0.8,
        warnings=[],
        provenance={"entry_id": pdb_id.upper()},
        pdb_id=pdb_id.upper(),
        organism=None,
        resolution_A=reso,
        method=method,
        chains=[],
        cofactors=[],
        bound_ligands=[],
        is_alphafold=False,
        preferred=False,
        selection_reason="RCSB experimental entry",
    )


def structure_from_fixture(rec: dict[str, Any]) -> ProteinStructure:
    return ProteinStructure(
        source="fixture:pdb",
        evidence_level=EvidenceLevel.A,
        confidence=0.95,
        warnings=["alphafold"] if rec.get("is_alphafold") else [],
        provenance=rec.get("provenance") or {},
        pdb_id=rec["pdb_id"].upper(),
        organism=rec.get("organism"),
        resolution_A=rec.get("resolution_A"),
        method=rec.get("method"),
        chains=list(rec.get("chains") or []),
        cofactors=list(rec.get("cofactors") or []),
        bound_ligands=list(rec.get("bound_ligands") or []),
        is_alphafold=bool(rec.get("is_alphafold", False)),
        preferred=bool(rec.get("preferred", False)),
        selection_reason=rec.get("selection_reason", ""),
    )


def rank_structures(structures: list[ProteinStructure]) -> list[ProteinStructure]:
    def key(s: ProteinStructure) -> tuple:
        human = 0 if (s.organism or "").lower().startswith("homo") else 1
        af = 1 if s.is_alphafold else 0
        lig = 0 if s.bound_ligands else 1
        reso = s.resolution_A if s.resolution_A is not None else 99.0
        return (af, human, lig, reso)

    ranked = sorted(structures, key=key)
    if ranked:
        ranked[0].preferred = True
        if not ranked[0].selection_reason:
            ranked[0].selection_reason = (
                "Preferred: experimental, preferably human, ligand-bound, higher resolution"
            )
    return ranked


def pocket_from_fixture(rec: dict[str, Any]) -> BindingPocket:
    return BindingPocket(
        source="fixture:pocket",
        evidence_level=EvidenceLevel.B,
        confidence=0.85,
        warnings=[],
        provenance=rec.get("provenance") or {},
        pocket_type=rec.get("pocket_type", "catalytic"),
        key_residues=list(rec.get("key_residues") or []),
        structure_pdb_id=rec.get("structure_pdb_id"),
        selection_reason=rec.get("selection_reason", ""),
    )
