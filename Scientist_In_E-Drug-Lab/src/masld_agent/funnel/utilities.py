"""Small deterministic utilities replacing fragile one-off agent code."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from masld_agent.funnel.artifacts import count_sdf_records


def inspect_sdf(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        return {"status": "error", "error": f"SDF not found: {source}"}
    try:
        records = count_sdf_records(source)
    except (OSError, EOFError) as exc:
        return {"status": "error", "error": f"cannot read SDF stream: {exc}"}
    return {
        "status": "ok" if records > 0 else "invalid",
        "path": str(source),
        "bytes": source.stat().st_size,
        "records": records,
        "compressed": source.suffix.lower() in {".gz", ".sdfgz"},
    }


def rank_glide_parents(
    csv_path: str | Path,
    output_path: str | Path,
    *,
    top: int,
    parent_column: str = "parent_id",
    score_column: str = "r_i_glide_gscore",
) -> dict[str, Any]:
    source = Path(csv_path).expanduser().resolve()
    destination = Path(output_path).expanduser().resolve()
    if top <= 0:
        return {"status": "error", "error": "top must be positive"}
    with source.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if not rows:
        return {"status": "error", "error": "Glide CSV has no rows"}
    available = set(rows[0])
    if parent_column not in available or score_column not in available:
        return {
            "status": "error",
            "error": f"required columns missing: {parent_column}, {score_column}",
            "available_columns": sorted(available),
        }
    best: dict[str, tuple[float, dict[str, str]]] = {}
    invalid_scores = 0
    for row in rows:
        parent = (row.get(parent_column) or "").strip()
        try:
            score = float(row.get(score_column) or "")
        except ValueError:
            invalid_scores += 1
            continue
        if not parent:
            continue
        if parent not in best or score < best[parent][0]:
            best[parent] = (score, row)
    ranked = sorted(best.items(), key=lambda item: (item[1][0], item[0]))[:top]
    destination.parent.mkdir(parents=True, exist_ok=True)
    fields = ["rank", parent_column, score_column, "source_row"]
    with destination.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for rank, (parent, (score, row)) in enumerate(ranked, start=1):
            writer.writerow(
                {
                    "rank": rank,
                    parent_column: parent,
                    score_column: score,
                    "source_row": rows.index(row) + 2,
                }
            )
    return {
        "status": "ok",
        "input_rows": len(rows),
        "parents_scored": len(best),
        "selected": len(ranked),
        "invalid_scores": invalid_scores,
        "output": str(destination),
    }
