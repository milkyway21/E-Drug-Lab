"""UniProt REST helpers."""
from __future__ import annotations

from typing import Any, Optional

from masld_agent.http_cache import CachedHttp
from masld_agent.models import EvidenceLevel, TargetCandidate


UNIPROT_SEARCH_URL = "https://rest.uniprot.org/uniprotkb/search"


def search_human_gene(
    gene: str,
    *,
    http: Optional[CachedHttp] = None,
    cache_only: bool = False,
) -> list[dict[str, Any]]:
    """Search reviewed human UniProt records for a gene symbol."""
    client = http or CachedHttp()
    data = client.get_json(
        UNIPROT_SEARCH_URL,
        params={
            "query": f"(gene_exact:{gene}) AND (organism_id:9606) AND (reviewed:true)",
            "format": "json",
            "size": "10",
            "fields": "accession,id,gene_names,protein_name,organism_name,xref_ensembl,cc_function",
        },
        cache_only=cache_only,
    )
    return list(data.get("results") or [])


def resolve_human_gene(
    gene: str,
    *,
    http: Optional[CachedHttp] = None,
    cache_only: bool = False,
) -> dict[str, Any]:
    records = search_human_gene(gene, http=http, cache_only=cache_only)
    if not records:
        return {
            "gene_symbol": gene.upper(),
            "uniprot_id": None,
            "ensembl_id": None,
            "function": "",
            "warnings": ["reviewed_human_uniprot_record_not_found"],
        }
    record = records[0]
    genes = record.get("genes") or []
    symbol = gene.upper()
    if genes:
        symbol = ((genes[0].get("geneName") or {}).get("value") or symbol).upper()
    ensembl_ids: list[str] = []
    for reference in record.get("uniProtKBCrossReferences") or []:
        if reference.get("database") != "Ensembl":
            continue
        reference_id = str(reference.get("id") or "").split(".")[0]
        if reference_id.startswith("ENSG"):
            ensembl_ids.append(reference_id)
        for prop in reference.get("properties") or []:
            value = str(prop.get("value") or "").split(".")[0]
            if prop.get("key") in {"GeneId", "Gene ID"} and value.startswith("ENSG"):
                ensembl_ids.append(value)
    comments = record.get("comments") or []
    function_parts: list[str] = []
    for comment in comments:
        if comment.get("commentType") != "FUNCTION":
            continue
        for text in comment.get("texts") or []:
            if text.get("value"):
                function_parts.append(text["value"])
    return {
        "gene_symbol": symbol,
        "uniprot_id": record.get("primaryAccession"),
        "ensembl_id": ensembl_ids[0] if ensembl_ids else None,
        "function": " ".join(function_parts),
        "warnings": [],
        "raw": record,
    }


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
