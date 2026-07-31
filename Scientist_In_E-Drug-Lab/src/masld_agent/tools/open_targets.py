"""Open Targets GraphQL client (best-effort)."""
from __future__ import annotations

from typing import Optional

from masld_agent.http_cache import CachedHttp
from masld_agent.models import EvidenceLevel, EvidenceRecord

OT_URL = "https://api.platform.opentargets.org/api/v4/graphql"


def fetch_target_associations_post(
    ensembl_id: str,
    *,
    http: Optional[CachedHttp] = None,
) -> list[EvidenceRecord]:
    """Return association evidence; empty/warning list if API unavailable."""
    client = http or CachedHttp()
    query = """
        query($ensemblId: String!) {
          target(ensemblId: $ensemblId) {
            id
            approvedSymbol
            associatedDiseases {
              rows { disease { id name } score }
            }
          }
        }
        """
    try:
        data = client.post_json(
            OT_URL,
            json_body={"query": query, "variables": {"ensemblId": ensembl_id}},
        )
    except Exception as exc:  # noqa: BLE001
        return [
            EvidenceRecord(
                source="open_targets",
                evidence_level=EvidenceLevel.U,
                confidence=0.0,
                warnings=[f"open_targets_unavailable:{exc}"],
                provenance={},
                verified=False,
            )
        ]

    rows = (
        (((data.get("data") or {}).get("target") or {}).get("associatedDiseases") or {}).get(
            "rows"
        )
        or []
    )
    out: list[EvidenceRecord] = []
    for row in rows[:10]:
        dis = row.get("disease") or {}
        name = dis.get("name") or ""
        score = row.get("score")
        out.append(
            EvidenceRecord(
                source="open_targets",
                evidence_level=EvidenceLevel.B,
                confidence=float(score) if score is not None else 0.4,
                warnings=[],
                provenance={"disease_id": dis.get("id"), "score": score},
                title=f"Open Targets association: {name}",
                supports_claim=name,
                verified=True,
                url="https://platform.opentargets.org/",
            )
        )
    return out
