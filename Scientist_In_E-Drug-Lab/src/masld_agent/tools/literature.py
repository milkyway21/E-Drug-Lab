"""Literature retrieval — Europe PMC / PubMed with verification gates."""
from __future__ import annotations

from typing import Optional

from masld_agent.http_cache import CachedHttp
from masld_agent.models import EvidenceLevel, EvidenceRecord


def _excerpt(text: Optional[str], n: int = 400) -> Optional[str]:
    if not text:
        return None
    t = " ".join(text.split())
    return t[:n] + ("…" if len(t) > n else "")


def search_europe_pmc(
    query: str,
    *,
    page_size: int = 5,
    http: Optional[CachedHttp] = None,
) -> list[EvidenceRecord]:
    client = http or CachedHttp()
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    data = client.get_json(
        url,
        params={"query": query, "format": "json", "pageSize": page_size},
    )
    results = []
    for hit in (data.get("resultList") or {}).get("result") or []:
        pmid = hit.get("pmid") or hit.get("id")
        doi = hit.get("doi")
        title = hit.get("title")
        year = None
        try:
            year = int(str(hit.get("pubYear"))) if hit.get("pubYear") else None
        except ValueError:
            year = None
        abstract = hit.get("abstractText")
        url_hit = None
        if pmid and str(pmid).isdigit():
            url_hit = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        elif doi:
            url_hit = f"https://doi.org/{doi}"
        verified = bool(pmid or doi) and bool(title)
        results.append(
            EvidenceRecord(
                source="europepmc",
                evidence_level=EvidenceLevel.B if verified else EvidenceLevel.U,
                confidence=0.7 if verified else 0.2,
                warnings=[] if verified else ["unverified_hit"],
                provenance={"raw_id": hit.get("id"), "source": hit.get("source")},
                pmid=str(pmid) if pmid else None,
                doi=doi,
                url=url_hit,
                title=title,
                year=year,
                abstract_excerpt=_excerpt(abstract),
                supports_claim=query,
                verified=verified,
            )
        )
    return [r for r in results if r.verified]


def search_pubmed_esearch(
    query: str,
    *,
    retmax: int = 5,
    http: Optional[CachedHttp] = None,
    email: Optional[str] = None,
) -> list[EvidenceRecord]:
    """Minimal PubMed E-utilities path; falls back gracefully on failure."""
    client = http or CachedHttp()
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": str(retmax),
        "retmode": "json",
    }
    if email:
        params["email"] = email
    try:
        data = client.get_json(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            params=params,
        )
    except Exception as exc:  # noqa: BLE001
        return [
            EvidenceRecord(
                source="pubmed",
                evidence_level=EvidenceLevel.U,
                confidence=0.0,
                warnings=[f"pubmed_esearch_failed:{exc}"],
                provenance={},
                verified=False,
                supports_claim=query,
            )
        ]
    ids = ((data.get("esearchresult") or {}).get("idlist")) or []
    out: list[EvidenceRecord] = []
    for pmid in ids:
        # ESearch alone has no title/abstract — do NOT mark verified.
        # Callers must efetch or Europe PMC before using in final reports.
        out.append(
            EvidenceRecord(
                source="pubmed",
                evidence_level=EvidenceLevel.U,
                confidence=0.3,
                warnings=["esearch_only_unverified_needs_efetch_or_europepmc"],
                provenance={"esearch": True},
                pmid=str(pmid),
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                title=None,
                verified=False,
                supports_claim=query,
            )
        )
    return out


def build_target_query(gene: str, disease: str = "MASLD") -> str:
    return f'({gene}) AND ({disease} OR NAFLD OR "fatty liver" OR steatosis OR lipotoxicity)'
