"""RCSB PDB structure retrieval and pocket heuristics."""
from __future__ import annotations

from typing import Any, Optional

from masld_agent.http_cache import CachedHttp
from masld_agent.models import (
    BindingPocket,
    EvidenceLevel,
    PocketQualification,
    ProteinStructure,
    StructureCandidate,
)

RCSB_SEARCH_URL = "https://search.rcsb.org/rcsbsearch/v2/query"
COMMON_CRYSTALLIZATION_COMPONENTS = {
    "HOH",
    "DMS",
    "EDO",
    "GOL",
    "PEG",
    "PGE",
    "SO4",
    "PO4",
    "CL",
    "NA",
    "K",
}
COMMON_COFACTORS = {"ATP", "ADP", "AMP", "NAD", "NAP", "FAD", "FMN", "COA", "HEM"}


def fetch_pdb_entry(pdb_id: str, *, http: Optional[CachedHttp] = None) -> dict[str, Any]:
    client = http or CachedHttp()
    pid = pdb_id.strip().upper()
    return client.get_json(f"https://data.rcsb.org/rest/v1/core/entry/{pid}")


def search_structures(
    *,
    gene: Optional[str] = None,
    uniprot_id: Optional[str] = None,
    rows: int = 100,
    http: Optional[CachedHttp] = None,
    cache_only: bool = False,
) -> list[str]:
    """Return RCSB polymer-entity identifiers for a human gene or UniProt accession."""
    if not gene and not uniprot_id:
        raise ValueError("gene or uniprot_id is required")
    if uniprot_id:
        query = {
            "type": "group",
            "logical_operator": "and",
            "nodes": [
                {
                    "type": "terminal",
                    "service": "text",
                    "parameters": {
                        "attribute": (
                            "rcsb_polymer_entity_container_identifiers."
                            "reference_sequence_identifiers.database_accession"
                        ),
                        "operator": "exact_match",
                        "value": uniprot_id,
                    },
                },
                {
                    "type": "terminal",
                    "service": "text",
                    "parameters": {
                        "attribute": (
                            "rcsb_polymer_entity_container_identifiers."
                            "reference_sequence_identifiers.database_name"
                        ),
                        "operator": "exact_match",
                        "value": "UniProt",
                    },
                },
            ],
        }
    else:
        query = {
            "type": "group",
            "logical_operator": "and",
            "nodes": [
                {
                    "type": "terminal",
                    "service": "text",
                    "parameters": {
                        "attribute": "rcsb_entity_source_organism.rcsb_gene_name.value",
                        "operator": "exact_match",
                        "value": gene,
                        "case_sensitive": True,
                    },
                },
                {
                    "type": "terminal",
                    "service": "text",
                    "parameters": {
                        "attribute": "rcsb_entity_source_organism.ncbi_scientific_name",
                        "operator": "exact_match",
                        "value": "Homo sapiens",
                    },
                },
            ],
        }
    payload = {
        "query": query,
        "return_type": "polymer_entity",
        "request_options": {
            "paginate": {"start": 0, "rows": min(max(rows, 1), 1000)},
            "results_content_type": ["experimental"],
        },
    }
    client = http or CachedHttp()
    data = client.post_json(
        RCSB_SEARCH_URL,
        json_body=payload,
        cache_only=cache_only,
    )
    return [
        str(item.get("identifier"))
        for item in data.get("result_set") or []
        if item.get("identifier")
    ]


def fetch_polymer_entity(
    identifier: str,
    *,
    http: Optional[CachedHttp] = None,
) -> dict[str, Any]:
    entry_id, entity_id = identifier.split("_", 1)
    client = http or CachedHttp()
    return client.get_json(
        f"https://data.rcsb.org/rest/v1/core/polymer_entity/{entry_id}/{entity_id}"
    )


def fetch_nonpolymer_entities(
    entry_id: str,
    entry_data: dict[str, Any],
    *,
    http: Optional[CachedHttp] = None,
) -> list[dict[str, Any]]:
    client = http or CachedHttp()
    entity_ids = (entry_data.get("rcsb_entry_container_identifiers") or {}).get(
        "non_polymer_entity_ids"
    ) or []
    entities: list[dict[str, Any]] = []
    for entity_id in entity_ids:
        entities.append(
            client.get_json(
                f"https://data.rcsb.org/rest/v1/core/nonpolymer_entity/{entry_id}/{entity_id}"
            )
        )
    return entities


def _ligand_records(nonpolymer_data: list[dict[str, Any]]) -> list[tuple[str, str]]:
    ligands: list[tuple[str, str]] = []
    for entity in nonpolymer_data:
        component_id = str((entity.get("pdbx_entity_nonpoly") or {}).get("comp_id") or "")
        description = str(
            (entity.get("rcsb_nonpolymer_entity") or {}).get("pdbx_description") or ""
        )
        if component_id:
            ligands.append((component_id.upper(), description))
    return ligands


def structure_candidate_from_records(
    identifier: str,
    entry_data: dict[str, Any],
    entity_data: dict[str, Any],
    *,
    target_gene: Optional[str] = None,
    nonpolymer_data: Optional[list[dict[str, Any]]] = None,
) -> StructureCandidate:
    entry_id, entity_id = identifier.split("_", 1)
    entry_info = entry_data.get("rcsb_entry_info") or {}
    resolutions = entry_info.get("resolution_combined") or []
    resolution = None
    if resolutions:
        try:
            resolution = float(resolutions[0])
        except (TypeError, ValueError):
            pass
    organisms = entity_data.get("rcsb_entity_source_organism") or []
    organism = organisms[0].get("ncbi_scientific_name") if organisms else None
    chains = [
        value.strip()
        for value in str((entity_data.get("entity_poly") or {}).get("pdbx_strand_id") or "").split(",")
        if value.strip()
    ]
    refs = (entity_data.get("rcsb_polymer_entity_container_identifiers") or {}).get(
        "reference_sequence_identifiers"
    ) or []
    uniprot = next(
        (r.get("database_accession") for r in refs if r.get("database_name") == "UniProt"),
        None,
    )
    mutations = []
    for feature in entity_data.get("rcsb_polymer_entity_feature") or []:
        if str(feature.get("type") or "").upper() == "MUTATION":
            mutations.append(str(feature.get("name") or feature.get("feature_id") or "mutation"))
    ligand_records = _ligand_records(nonpolymer_data or [])
    ligands = [
        f"{component_id}: {description}" if description else component_id
        for component_id, description in ligand_records
    ]
    relevant_ligand = any(
        component_id not in COMMON_CRYSTALLIZATION_COMPONENTS
        for component_id, _description in ligand_records
    )
    cofactors = [
        component_id
        for component_id, _description in ligand_records
        if component_id in COMMON_COFACTORS
    ]
    methods = entry_data.get("exptl") or []
    release = (entry_data.get("rcsb_accession_info") or {}).get("initial_release_date")
    candidate = StructureCandidate(
        source="rcsb",
        evidence_level=EvidenceLevel.A,
        confidence=0.85,
        warnings=[],
        provenance={"entry_id": entry_id, "polymer_entity_id": entity_id},
        pdb_id=entry_id,
        target_gene=target_gene,
        organism=organism,
        resolution_A=resolution,
        method=methods[0].get("method") if methods else None,
        chains=chains,
        bound_ligands=ligands,
        cofactors=cofactors,
        relevant_ligand=relevant_ligand,
        is_alphafold=False,
        uniprot_id=uniprot,
        entity_id=entity_id,
        mutations=mutations,
        biological_assembly=";".join(
            str(value)
            for value in (entry_data.get("rcsb_entry_container_identifiers") or {}).get(
                "assembly_ids"
            )
            or []
        )
        or None,
        release_date=release,
        selection_reason="RCSB experimental structure candidate",
    )
    return candidate


def discover_structure_candidates(
    *,
    gene: Optional[str] = None,
    uniprot_id: Optional[str] = None,
    limit: int = 25,
    http: Optional[CachedHttp] = None,
) -> list[StructureCandidate]:
    client = http or CachedHttp()
    identifiers = search_structures(gene=gene, uniprot_id=uniprot_id, rows=limit, http=client)
    candidates: list[StructureCandidate] = []
    for identifier in identifiers[:limit]:
        entry_id = identifier.split("_", 1)[0]
        try:
            entry = fetch_pdb_entry(entry_id, http=client)
            entity = fetch_polymer_entity(identifier, http=client)
            nonpolymer = fetch_nonpolymer_entities(entry_id, entry, http=client)
            candidates.append(
                structure_candidate_from_records(
                    identifier,
                    entry,
                    entity,
                    target_gene=gene,
                    nonpolymer_data=nonpolymer,
                )
            )
        except Exception as exc:  # noqa: BLE001
            candidates.append(
                StructureCandidate(
                    source="rcsb",
                    evidence_level=EvidenceLevel.U,
                    confidence=0.0,
                    warnings=[f"rcsb_metadata_fetch_failed:{exc}"],
                    provenance={"identifier": identifier},
                    pdb_id=entry_id,
                    entity_id=identifier.split("_", 1)[-1],
                    target_gene=gene,
                )
            )
    return [StructureCandidate.model_validate(s) for s in rank_structures(candidates)]


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
        lig = 0 if isinstance(s, StructureCandidate) and s.relevant_ligand else 1
        reso = s.resolution_A if s.resolution_A is not None else 99.0
        return (af, human, lig, reso)

    ranked = sorted(structures, key=key)
    for structure in ranked:
        score = 0.0
        score += 25.0 if not structure.is_alphafold else 0.0
        score += 20.0 if (structure.organism or "").lower().startswith("homo") else 0.0
        score += (
            20.0
            if isinstance(structure, StructureCandidate) and structure.relevant_ligand
            else 0.0
        )
        score += max(0.0, 25.0 - 5.0 * (structure.resolution_A or 5.0))
        score += 10.0 if not structure.mutations else 3.0
        structure.quality_score = round(min(score, 100.0), 2)
    if ranked:
        ranked[0].preferred = True
        if not ranked[0].selection_reason:
            ranked[0].selection_reason = (
                "Preferred: experimental, preferably human, ligand-bound, higher resolution"
            )
    return ranked


def qualify_pocket(
    structure: Optional[ProteinStructure],
    *,
    target_gene: str,
    key_residues: Optional[list[str]] = None,
    evidence_basis: Optional[list[str]] = None,
    mechanism_is_target_based: bool = True,
) -> PocketQualification:
    residues = list(key_residues or [])
    evidence = list(evidence_basis or [])
    reasons: list[str] = []
    if not mechanism_is_target_based:
        reasons.append("phenotypic_or_non_target_mechanism")
    if structure is None:
        reasons.append("no_structure_candidate")
    elif structure.evidence_level == EvidenceLevel.U:
        reasons.append("structure_metadata_unverified")
    relevant_ligand = (
        structure.relevant_ligand
        if isinstance(structure, StructureCandidate)
        else False
    )
    if structure and not (relevant_ligand or residues or evidence):
        reasons.append("no_ligand_residue_or_literature_pocket_evidence")
    applicable = mechanism_is_target_based and structure is not None
    qualified = applicable and not reasons
    return PocketQualification(
        source="pocket_qualification",
        evidence_level=EvidenceLevel.B if qualified else EvidenceLevel.U,
        confidence=0.8 if qualified else 0.2,
        warnings=reasons,
        provenance={},
        target_gene=target_gene,
        structure_id=structure.pdb_id if structure else None,
        applicable=applicable,
        qualified=qualified,
        pocket_type="ligand_supported" if relevant_ligand else None,
        key_residues=residues,
        evidence_basis=evidence + (structure.bound_ligands if structure else []),
        rejection_reasons=reasons,
        docking_recommendation="dock" if qualified else "do_not_dock",
    )


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
