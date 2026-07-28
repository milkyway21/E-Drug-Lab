"""UniProt REST helpers."""
from __future__ import annotations

from typing import Any, Optional

from masld_agent.http_cache import CachedHttp
from masld_agent.models import EvidenceLevel, TargetCandidate


def fetch_uniprot(accession: str, *, http: Optional[CachedHttp] = None) -> dict[str, Any]:
    client = http or CachedHttp()
    url = f"https://rest.uniprot.org/uniprotkb/{accession}.json"
    return client.get_json(url)


def gene_to_candidate_from_uniprot(
    gene: str,
    accession: str,
    *,
    http: Optional[CachedHttp] = None,
    rationale: str = "",
) -> TargetCandidate:
    data = fetch_uniprot(accession, http=http)
    genes = []
    for g in data.get("genes") or []:
        if g.get("geneName", {}).get("value"):
            genes.append(g["geneName"]["value"])
    symbol = genes[0] if genes else gene
    organism = (data.get("organism") or {}).get("scientificName", "Homo sapiens")
    return TargetCandidate(
        source="uniprot",
        evidence_level=EvidenceLevel.A,
        confidence=0.85,
        warnings=[],
        provenance={"accession": accession, "entryType": data.get("entryType")},
        gene_symbol=symbol,
        uniprot_id=accession,
        organism=organism,
        rationale=rationale or f"UniProt entry {accession}",
        mechanisms=[],
    )


def parse_uniprot_fixture(data: dict[str, Any]) -> TargetCandidate:
    genes = []
    for g in data.get("genes") or []:
        if g.get("geneName", {}).get("value"):
            genes.append(g["geneName"]["value"])
    return TargetCandidate(
        source="fixture:uniprot",
        evidence_level=EvidenceLevel.A,
        confidence=0.9,
        warnings=[],
        provenance={"accession": data.get("primaryAccession")},
        gene_symbol=genes[0] if genes else data.get("primaryAccession", "UNKNOWN"),
        uniprot_id=data.get("primaryAccession"),
        organism=(data.get("organism") or {}).get("scientificName", "Homo sapiens"),
        rationale="Loaded from offline UniProt fixture",
    )
