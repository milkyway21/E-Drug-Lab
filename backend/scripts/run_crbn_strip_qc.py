#!/usr/bin/env python3
"""对专利/wetlab/101D 跑 CRBN strip QC，写出 features_v1/strip_qc/。"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.pipelines.vav1_rl.crbn_strip import (  # noqa: E402
    has_crbn_module_remain,
    has_ortho_cl_anchor,
    strip_crbn_anchor_module,
)
from rdkit import Chem  # noqa: E402

BINDING = ROOT / "outputs/vav1_rl_project/binding_RL"
OUT = BINDING / "features_v1" / "strip_qc"
PAT101 = ROOT / "outputs/vav1_rl_project/PAT_training_database_101D.csv"
PAT_LABELS = BINDING / "patent_docking" / "patent_403_labels.csv"
WETLAB = BINDING / "wetlab_docking" / "wetlab_13_labels.csv"


def _run_set(name: str, rows: list[dict], smi_key: str) -> dict:
    modes = Counter()
    fails = []
    remain_glu = 0
    ok_n = 0
    with_anchor = 0
    collisions: dict[str, list] = {}
    detail = []
    for row in rows:
        smi = row.get(smi_key) or row.get("Canonical_SMILES") or row.get("smiles") or ""
        mid = row.get("molecule_id") or row.get("Cpd.") or row.get("SDF_ID") or ""
        r = strip_crbn_anchor_module(smi)
        modes[r["strip_mode"]] += 1
        if r.get("had_glutarimide"):
            with_anchor += 1
        if r["ok"]:
            ok_n += 1
            mol = Chem.MolFromSmiles(r["smiles_stripped"])
            # 残留判定：仍带氯苯式 CRBN 锚定才计 fail
            if mol and has_crbn_module_remain(mol) and has_ortho_cl_anchor(mol):
                remain_glu += 1
            ik = r.get("inchikey_stripped") or ""
            if ik:
                collisions.setdefault(ik, []).append(str(mid))
        else:
            fails.append({"id": mid, "smiles": smi, "error": r.get("error")})
        detail.append(
            {
                "id": mid,
                "smiles_raw": smi,
                "smiles_stripped": r.get("smiles_stripped"),
                "strip_mode": r.get("strip_mode"),
                "ok": r.get("ok"),
                "error": r.get("error"),
            }
        )
    main_keys = (
        "C_orthoCl",
        "N_orthoCl",
        "C_orthoCl_alt",
        "N_du_Cl",
        "N_du_Cl_meta",
        "N_du_Cl_ortho",
    )
    main_hit = sum(modes[m] for m in main_keys)
    # 含锚定分子中「主模式+合理 fallback」成功率
    ok_anchor = ok_n - modes.get("no_anchor", 0)
    main_rate = (main_hit / with_anchor) if with_anchor else 1.0
    success_rate = (ok_anchor / with_anchor) if with_anchor else 1.0
    coll = {k: v for k, v in collisions.items() if len(v) > 1}
    report = {
        "name": name,
        "n": len(rows),
        "ok": ok_n,
        "with_glutarimide": with_anchor,
        "modes": dict(modes),
        "main_orthoCl_rate": main_rate,
        "anchor_success_rate": success_rate,
        "glutarimide_remain_after_strip": remain_glu,
        "n_fail": len(fails),
        "fails": fails[:50],
        "n_collision_inchikey": len(coll),
        "gate_pass": (
            (success_rate >= 0.98 if with_anchor else True)
            and remain_glu == 0
            and len(fails) == 0
        ),
    }
    with (OUT / f"{name}_detail.csv").open("w", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["id", "smiles_raw", "smiles_stripped", "strip_mode", "ok", "error"],
        )
        w.writeheader()
        w.writerows(detail)
    with (OUT / f"{name}_collisions.json").open("w") as f:
        json.dump(coll, f, indent=2, ensure_ascii=False)
    return report


def _read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    reports = []
    if PAT101.is_file():
        reports.append(_run_set("pat101", _read_csv(PAT101), "Canonical_SMILES"))
    if PAT_LABELS.is_file():
        rows = _read_csv(PAT_LABELS)
        key = "neutralized_smiles" if "neutralized_smiles" in rows[0] else "canonical_smiles"
        reports.append(_run_set("patent403", rows, key))
    if WETLAB.is_file():
        reports.append(_run_set("wetlab13", _read_csv(WETLAB), "SMILES"))
    summary = {"reports": reports, "all_pass": all(r["gate_pass"] for r in reports)}
    (OUT / "strip_qc_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if not summary["all_pass"]:
        # 仍写出产物，但不以非零退出阻塞后续开发；训练前再强制
        print("WARNING: strip QC gate not fully passed", file=sys.stderr)


if __name__ == "__main__":
    main()
