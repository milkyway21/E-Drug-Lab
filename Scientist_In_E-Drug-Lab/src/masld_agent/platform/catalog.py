"""Load and query config/platform/catalog.yaml."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml

from masld_agent.platform.paths import CATALOG_PATH

# Plan-required catalog ids (must exist for completeness tests)
REQUIRED_IDS = [
    "dd.env",
    "dd.cfg.sampling",
    "dd.cfg.fast_denovo",
    "dd.cfg.fast_scaffold",
    "dd.cfg.prudent",
    "dd.script.sample",
    "dd.script.batch",
    "dd.script.eval",
    "dd.script.extract",
    "dd.script.pocket_quality",
    "dd.mode.denovo_fast",
    "dd.mode.scaffold_fast",
    "dd.mode.prudent",
    "dd.gpu.policy",
    "dd.inputs",
    "dd.outputs",
    "dd.funnel.link",
    "ed.root",
    "ed.svc.diffdynamic",
    "ed.svc.schrodinger",
    "ed.svc.vina",
    "ed.local.schrodinger",
    "ed.http.diffdynamic",
    "ed.http.affinity",
    "ed.integrations.stub",
    "ed.cfg",
    "ed.pipelines.vav1",
    "sz.env",
    "sz.bin.glide",
    "sz.bin.ligprep",
    "sz.bin.qikprop",
    "sz.bin.prime_mmgbsa",
    "sz.bin.ifd",
    "sz.bin.prepwizard",
    "sz.bin.run",
    "sz.prepwizard",
    "sz.ligprep",
    "sz.grid",
    "sz.glide_sp",
    "sz.glide_xp",
    "sz.qikprop",
    "sz.mmgbsa",
    "sz.ifd",
    "sz.funnel.ddfast",
    "sz.pitfalls",
]


@lru_cache(maxsize=1)
def load_catalog(path: Optional[str] = None) -> dict[str, Any]:
    p = Path(path) if path else CATALOG_PATH
    if not p.is_file():
        return {"version": 0, "entries": [], "error": f"missing {p}"}
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    data.setdefault("entries", [])
    return data


def list_entries(
    *,
    system: Optional[str] = None,
    stage: Optional[str] = None,
    path: Optional[str] = None,
) -> list[dict[str, Any]]:
    entries = list(load_catalog(path).get("entries") or [])
    if system:
        sys = system.lower()
        if sys in {"dd", "diffdynamic"}:
            sys = "dd"
        elif sys in {"ed", "edrug", "e-drug-lab", "edrug-lab"}:
            sys = "ed"
        elif sys in {"sz", "schrodinger", "schrödinger"}:
            sys = "sz"
        entries = [e for e in entries if str(e.get("system")) == sys]
    if stage:
        entries = [e for e in entries if str(e.get("stage")) == stage]
    return entries


def get_entry(entry_id: str, *, path: Optional[str] = None) -> Optional[dict[str, Any]]:
    for e in list_entries(path=path):
        if e.get("id") == entry_id:
            return e
    return None


def summarize_systems(*, path: Optional[str] = None) -> dict[str, Any]:
    cat = load_catalog(path)
    entries = list(cat.get("entries") or [])
    by: dict[str, int] = {}
    for e in entries:
        s = str(e.get("system") or "?")
        by[s] = by.get(s, 0) + 1
    missing = [i for i in REQUIRED_IDS if get_entry(i, path=path) is None]
    return {
        "version": cat.get("version"),
        "n_entries": len(entries),
        "by_system": by,
        "required_ids": len(REQUIRED_IDS),
        "missing_required_ids": missing,
        "catalog_path": str(path or CATALOG_PATH),
    }


def format_entry(entry: dict[str, Any]) -> str:
    lines = [
        f"## {entry.get('id')}",
        "",
        f"- system: `{entry.get('system')}`",
        f"- stage: `{entry.get('stage')}`",
        f"- summary: {entry.get('summary')}",
    ]
    if entry.get("invoke"):
        lines.append(f"- invoke: `{entry.get('invoke')}`")
    if entry.get("env"):
        lines.append(f"- env: `{entry.get('env')}`")
    if entry.get("inputs"):
        lines.append(f"- inputs: {entry.get('inputs')}")
    if entry.get("outputs"):
        lines.append(f"- outputs: {entry.get('outputs')}")
    if entry.get("risks"):
        lines.append(f"- risks: {entry.get('risks')}")
    if entry.get("skill_ref"):
        lines.append(f"- skill_ref: {entry.get('skill_ref')}")
    lines.append("")
    return "\n".join(lines)
