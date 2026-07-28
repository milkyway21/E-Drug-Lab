"""AI4S submission helpers: Top10 CSV template, validate, pack, HepG2 plan."""
from __future__ import annotations

import csv
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from masld_agent.config import DEFAULT_COMPETITION, PKG_ROOT, load_competition_config
from masld_agent.tools.ai4s_brief import lint_dual_readout, load_ai4s_config

TOP10_COLUMNS_DEFAULT = [
    "rank",
    "id_or_name",
    "smiles_or_inchikey",
    "lipid_rationale",
    "tox_rationale",
    "mechanism_hypothesis",
    "evidence_refs",
    "library_source",
]


def top10_columns(cfg: Optional[dict[str, Any]] = None) -> list[str]:
    data = cfg or load_ai4s_config()
    cols = data.get("top10_csv_columns") or TOP10_COLUMNS_DEFAULT
    return [str(c) for c in cols]


def export_top10_template(output: Path, cfg: Optional[dict[str, Any]] = None) -> Path:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    cols = top10_columns(cfg)
    with output.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        # Example empty rows 1..10 with library_source placeholder
        for i in range(1, 11):
            row = {c: "" for c in cols}
            row["rank"] = str(i)
            row["library_source"] = "official_sdf_library"
            row["id_or_name"] = f"PENDING_{i:02d}"
            w.writerow(row)
    return output


def _read_text_if_exists(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _parse_top10_csv(path: Path, cols: list[str]) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = []
        for row in reader:
            rows.append({c: (row.get(c) or "").strip() for c in cols})
        return rows


def validate_submission(
    run_dir: Path,
    *,
    top10_csv: Optional[Path] = None,
    competition_config: Optional[Path] = None,
) -> dict[str, Any]:
    run_dir = Path(run_dir)
    cfg = load_competition_config(competition_config or DEFAULT_COMPETITION)
    cols = top10_columns(cfg)
    csv_path = Path(top10_csv) if top10_csv else run_dir / "top10_nomination.csv"
    if not csv_path.is_file():
        # fall back to template location inside run
        alt = run_dir / "submission" / "top10_nomination.csv"
        if alt.is_file():
            csv_path = alt

    checks: list[dict[str, Any]] = []
    status_flags: list[str] = []

    # Artifact presence
    for name, label in [
        ("proposal.md", "mechanism/proposal markdown"),
        ("method.md", "methodology markdown"),
        ("machine_readable_report.json", "machine-readable report"),
        ("manifest.json", "run manifest"),
    ]:
        ok = (run_dir / name).is_file()
        checks.append({"id": f"file:{name}", "ok": ok, "detail": label})
        if not ok:
            status_flags.append(f"missing_{name}")

    # Dual readout on proposal + method
    blob = _read_text_if_exists(run_dir / "proposal.md") + "\n" + _read_text_if_exists(
        run_dir / "method.md"
    )
    if (run_dir / "hepg2_validation_plan.md").is_file():
        blob += "\n" + _read_text_if_exists(run_dir / "hepg2_validation_plan.md")
    lint = lint_dual_readout(blob, cfg)
    checks.append(
        {
            "id": "dual_readout",
            "ok": lint["ok"],
            "detail": lint["message"],
            "missing": lint["missing"],
        }
    )
    if not lint["ok"]:
        status_flags.append("dual_readout_incomplete")

    # Top10 CSV
    rows = _parse_top10_csv(csv_path, cols)
    csv_exists = csv_path.is_file()
    checks.append(
        {
            "id": "top10_csv_present",
            "ok": csv_exists,
            "detail": str(csv_path) if csv_exists else "top10_nomination.csv not found",
        }
    )
    if not csv_exists:
        status_flags.append("pending_library_nomination")

    filled = 0
    pending_placeholder = 0
    for row in rows:
        name = row.get("id_or_name") or ""
        struct = row.get("smiles_or_inchikey") or ""
        lipid = row.get("lipid_rationale") or ""
        tox = row.get("tox_rationale") or ""
        if name.startswith("PENDING_") or not struct:
            pending_placeholder += 1
        if name and struct and lipid and tox:
            filled += 1
            # per-row dual readout
            row_lint = lint_dual_readout(f"{lipid}\n{tox}", cfg)
            if not row_lint["ok"]:
                status_flags.append(f"row_{row.get('rank', '?')}_dual_readout")

    checks.append(
        {
            "id": "top10_filled",
            "ok": filled >= 10,
            "detail": f"filled_rows={filled}/10 placeholders_or_empty_struct={pending_placeholder}",
        }
    )
    if filled < 10:
        status_flags.append("pending_library_nomination")

    # Hard constraints surface
    for cid, text in (cfg.get("hard_constraints") or {}).items():
        checks.append({"id": f"constraint:{cid}", "ok": True, "detail": text, "advisory": True})

    ok = all(c["ok"] for c in checks if not c.get("advisory"))
    result = {
        "ok": ok,
        "run_dir": str(run_dir),
        "top10_csv": str(csv_path) if csv_exists else None,
        "checks": checks,
        "status_flags": sorted(set(status_flags)),
        "scoring_dimensions": cfg.get("scoring_dimensions"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    return result


def write_validation_report(run_dir: Path, result: dict[str, Any]) -> Path:
    run_dir = Path(run_dir)
    sub = run_dir / "submission"
    sub.mkdir(parents=True, exist_ok=True)
    json_path = sub / "validate_submission.json"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md_lines = [
        "# AI4S submission validation",
        "",
        f"- ok: **{result['ok']}**",
        f"- flags: `{', '.join(result.get('status_flags') or []) or 'none'}`",
        "",
        "| check | ok | detail |",
        "|---|---|---|",
    ]
    for c in result.get("checks") or []:
        md_lines.append(
            f"| `{c['id']}` | {'yes' if c['ok'] else 'NO'} | {c.get('detail', '')} |"
        )
    md_path = sub / "validate_submission.md"
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    return md_path


def write_ai4s_readme(run_dir: Path) -> Path:
    run_dir = Path(run_dir)
    sub = run_dir / "submission"
    sub.mkdir(parents=True, exist_ok=True)
    path = sub / "README_AI4S.md"
    path.write_text(
        "\n".join(
            [
                "# AI4S 提交辅助",
                "",
                "人设仍以仓库 `config/SOUL.md`（e-drug-lab 通用药物发现）为准；",
                "以下命令仅在进入生命科学赛道提交语境时使用。",
                "",
                "```bash",
                "masld-agent competition-brief",
                "masld-agent export-top10-template --output submission/top10_nomination.csv",
                "masld-agent hepg2-plan --run-dir .",
                "masld-agent dual-readout-lint --text proposal.md",
                "masld-agent validate-submission --run-dir .",
                "masld-agent pack-submission --run-dir . --output submission/ai4s_bundle.zip",
                "```",
                "",
                "- 库内 Top10（C1）必须来自官方 SDF；未填结构前校验会标记 `pending_library_nomination`。",
                "- 机制/方法 Markdown 可再导出为 PDF 后提交。",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def write_hepg2_plan(run_dir: Path, *, competition_config: Optional[Path] = None) -> Path:
    run_dir = Path(run_dir)
    cfg = load_competition_config(competition_config or DEFAULT_COMPETITION)
    readouts = cfg.get("experimental_readouts") or {}
    mechs = cfg.get("mechanisms_of_interest") or []

    genes: list[str] = []
    targets_csv = run_dir / "targets_ranked.csv"
    if targets_csv.is_file():
        with targets_csv.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                g = (row.get("gene_symbol") or "").strip()
                if g:
                    genes.append(g)

    lines = [
        "# HepG2-FFA 双读出验证方案骨架",
        "",
        f"> 体系: {readouts.get('system', 'HepG2-FFA')}",
        "",
        str(readouts.get("effective_hit_definition", "")).strip(),
        "",
        "## 读出指标",
        "",
        "1. **脂质蓄积（降脂效应）**：化合物处理后细胞内脂滴 / 中性脂含量变化。",
        "2. **细胞活力（毒性对照）**：相同条件下细胞活力；排除杀伤导致的脂滴假阳性。",
        "",
        "## 实验设计要点",
        "",
        "- 模型：HepG2 + FFA 诱导脂质蓄积。",
        "- 必须同时报告降脂与活力；仅脂滴下降不计为有效命中。",
        "- 设置溶剂对照与（如有）阳性对照。",
        "- 浓度梯度与重复孔；记录细胞形态异常。",
        "",
        "## 与靶点假说的衔接",
        "",
    ]
    if genes:
        lines.append("本 run 涉及靶点：")
        for g in genes:
            lines.append(f"- {g}：补充该靶点/通路下可检验的读出（表达、磷酸化、通量等）")
    else:
        lines.append("- （无 targets_ranked.csv；请先运行 offline-demo / run）")
    lines += [
        "",
        "## 机制通路 checklist（官方举例）",
        "",
        ", ".join(str(m) for m in mechs),
        "",
        "## 假阳性排除",
        "",
        "- 活力显著下降 → 不计入有效降脂命中。",
        "- 需在方案中写明毒性阈值与复测策略。",
        "",
    ]
    out = run_dir / "hepg2_validation_plan.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def pack_submission(
    run_dir: Path,
    output_zip: Path,
    *,
    top10_csv: Optional[Path] = None,
    competition_config: Optional[Path] = None,
) -> Path:
    run_dir = Path(run_dir)
    output_zip = Path(output_zip)
    output_zip.parent.mkdir(parents=True, exist_ok=True)

    write_ai4s_readme(run_dir)
    if not (run_dir / "hepg2_validation_plan.md").is_file():
        write_hepg2_plan(run_dir, competition_config=competition_config)

    sub = run_dir / "submission"
    sub.mkdir(parents=True, exist_ok=True)
    tmpl = sub / "top10_nomination.csv"
    if not tmpl.is_file() and not (top10_csv and Path(top10_csv).is_file()):
        export_top10_template(tmpl, load_competition_config(competition_config or DEFAULT_COMPETITION))

    result = validate_submission(
        run_dir, top10_csv=top10_csv, competition_config=competition_config
    )
    write_validation_report(run_dir, result)

    checklist = sub / "SUBMISSION_CHECKLIST.md"
    checklist.write_text(
        "\n".join(
            [
                "# SUBMISSION_CHECKLIST",
                "",
                f"- validation_ok: {result['ok']}",
                f"- status_flags: {', '.join(result.get('status_flags') or []) or 'none'}",
                "",
                "必交对照（官网）:",
                "1. Top10 CSV（官方库分子 + 降脂/毒性依据）",
                "2. 机制与验证方案（PDF；可用 proposal + hepg2 plan）",
                "3. 方法学与复现材料（method.md / Docker / 仓库）",
                "",
                "详见 validate_submission.md",
                "",
            ]
        ),
        encoding="utf-8",
    )

    include_names = [
        "proposal.md",
        "method.md",
        "machine_readable_report.json",
        "manifest.json",
        "warnings.md",
        "targets_ranked.csv",
        "ligands.csv",
        "evidence.json",
        "events.jsonl",
        "config_snapshot.yaml",
        "hepg2_validation_plan.md",
    ]
    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in include_names:
            p = run_dir / name
            if p.is_file():
                zf.write(p, arcname=name)
        for p in sorted(sub.rglob("*")):
            if p.is_file():
                zf.write(p, arcname=f"submission/{p.relative_to(sub)}")
        if top10_csv and Path(top10_csv).is_file():
            zf.write(Path(top10_csv), arcname="submission/top10_nomination.csv")

    return output_zip
