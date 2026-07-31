"""Reactome Content Service helpers for pathway reconnaissance."""
from __future__ import annotations

from typing import Any, Optional

from masld_agent.http_cache import CachedHttp


def search_human_pathways(
    query: str,
    *,
    limit: int = 20,
    http: Optional[CachedHttp] = None,
    cache_only: bool = False,
) -> list[dict[str, Any]]:
    client = http or CachedHttp()
    data = client.get_json(
        "https://reactome.org/ContentService/search/query",
        params={
            "query": query,
            "species": "Homo sapiens",
            "types": "Pathway",
            "cluster": "true",
        },
        cache_only=cache_only,
    )
    hits: list[dict[str, Any]] = []
    for group in data.get("results") or []:
        for entry in group.get("entries") or []:
            stable_id = entry.get("stId") or entry.get("dbId")
            hits.append(
                {
                    "stable_id": str(stable_id) if stable_id is not None else None,
                    "name": entry.get("name"),
                    "species": entry.get("species"),
                    "type": entry.get("type"),
                }
            )
            if len(hits) >= limit:
                return hits
    return hits
