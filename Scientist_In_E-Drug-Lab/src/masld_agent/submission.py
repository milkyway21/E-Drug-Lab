"""AI4S submission helpers: Top10 CSV template, validate, pack, HepG2 plan."""
from __future__ import annotations

import csv
import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from masld_agent.config import DEFAULT_COMPETITION, load_competition_config
from masld_agent.tools.ai4s_brief import (
    lint_dual_readout,
    lint_hepg2_validation_plan,
    load_ai4s_config,
    normalize_output_language,
)

TOP10_COLUMNS_DEFAULT = [
    "rank",
    "library_id",
    "id_or_name",
    "canonical_smiles",
    "parent_inchikey",
    "smiles_or_inchikey",
    "target_or_pathway",
    "evidence_level",
    "lipid_score",
    "safety_score",
    "uncertainty_penalty",
    "ranking_basis",
    "score_components",
    "structure_applicability",
    "lipid_rationale",
    "tox_rationale",
    "toxicity_evidence_status",
    "mechanism_hypothesis",
    "validation_readouts",
    "evidence_refs",
    "library_source",
    "library_sha256",
    "nomination_status",
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


def _find_library_path(run_dir: Path, manifest: dict[str, Any]) -> Optional[Path]:
    candidates = [
        manifest.get("library_path"),
        manifest.get("official_library"),
        manifest.get("inputs", {}).get("official_library")
        if isinstance(manifest.get("inputs"), dict)
        else None,
    ]
    for raw in candidates:
        if not raw:
            continue
        candidate = Path(str(raw)).expanduser()
        if not candidate.is_absolute():
            candidate = run_dir / candidate
        if candidate.is_file():
            return candidate.resolve()
    return None


def _library_hash(path: Optional[Path]) -> Optional[str]:
    if path is None or not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _identity_fields_ok(row: dict[str, str]) -> bool:
    return bool(
        row.get("library_id")
        and row.get("parent_inchikey")
        and row.get("canonical_smiles")
        and row.get("library_source")
        and row.get("library_sha256")
    )


def _library_identity_index(path: Optional[Path]) -> dict[str, tuple[str, str]]:
    if path is None:
        return {}
    try:
        from masld_agent.tools.compound_evidence import load_compound_library

        cards = load_compound_library(path)
    except (OSError, ValueError, RuntimeError):
        return {}
    return {
        card.library_id: (card.parent_inchikey or "", card.canonical_smiles or "")
        for card in cards
        if card.identity_valid
    }


def validate_submission(
    run_dir: Path,
    *,
    top10_csv: Optional[Path] = None,
    competition_config: Optional[Path] = None,
) -> dict[str, Any]:
    run_dir = Path(run_dir)
    cfg = load_competition_config(competition_config or DEFAULT_COMPETITION)
    cols = top10_columns(cfg)
    manifest_path = run_dir / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        manifest = {}
    library_path = _find_library_path(run_dir, manifest)
    expected_library_hash = manifest.get("library_sha256") or _library_hash(library_path)
    expected_library_source = str(
        manifest.get("library_source") or "official_sdf_library"
    )
    library_identity_index = _library_identity_index(library_path)
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

    plan_path = run_dir / "hepg2_validation_plan.md"
    plan_lint = lint_hepg2_validation_plan(_read_text_if_exists(plan_path))
    checks.append(
        {
            "id": "hepg2_validation_plan",
            "ok": plan_lint["ok"],
            "detail": plan_lint["message"],
            "missing": plan_lint["missing"],
        }
    )
    if not plan_lint["ok"]:
        status_flags.append("hepg2_validation_plan_incomplete")

    library_identity_ok = bool(library_path and expected_library_hash)
    if library_path and expected_library_hash:
        library_identity_ok = _library_hash(library_path) == expected_library_hash
    checks.append(
        {
            "id": "official_library_identity",
            "ok": library_identity_ok,
            "detail": (
                f"path={library_path}; sha256={expected_library_hash}"
                if library_identity_ok
                else "manifest library_path/library_sha256 could not be verified"
            ),
        }
    )
    if not library_identity_ok:
        status_flags.append("official_library_identity_unverified")

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
    valid_ranks: list[int] = []
    parent_keys: list[str] = []
    detailed_rows = 0
    identity_rows = 0
    ranking_rows = 0
    mechanism_rows = 0
    experimental_rows = 0
    row_hashes: list[str] = []
    identity_mismatches: list[str] = []
    source_mismatches: list[str] = []
    score_values: list[float] = []
    score_parse_errors: list[str] = []
    for row in rows:
        name = row.get("id_or_name") or ""
        struct = (
            row.get("canonical_smiles")
            or row.get("parent_inchikey")
            or row.get("smiles_or_inchikey")
            or ""
        )
        lipid = row.get("lipid_rationale") or ""
        tox = row.get("tox_rationale") or ""
        try:
            valid_ranks.append(int(row.get("rank") or ""))
        except ValueError:
            status_flags.append(f"row_{row.get('rank', '?')}_invalid_rank")
        parent_key = row.get("parent_inchikey") or ""
        if parent_key:
            parent_keys.append(parent_key)
        if name.startswith("PENDING_") or not struct:
            pending_placeholder += 1
        if _identity_fields_ok(row):
            identity_rows += 1
        if row.get("library_source") != expected_library_source:
            source_mismatches.append(row.get("library_id", "?"))
        library_identity = library_identity_index.get(row.get("library_id", ""))
        if library_identity and (
            row.get("parent_inchikey") != library_identity[0]
            or row.get("canonical_smiles") != library_identity[1]
        ):
            identity_mismatches.append(row.get("library_id", "?"))
        if row.get("library_sha256"):
            row_hashes.append(row["library_sha256"])
        if name and struct and lipid and tox:
            filled += 1
            # per-row dual readout
            row_lint = lint_dual_readout(
                "\n".join(
                    [
                        lipid,
                        tox,
                        row.get("mechanism_hypothesis") or "",
                        row.get("validation_readouts") or "",
                    ]
                ),
                cfg,
            )
            if not row_lint["ok"]:
                status_flags.append(f"row_{row.get('rank', '?')}_dual_readout")
            score_components = row.get("score_components") or ""
            if row.get("ranking_basis") and score_components:
                ranking_rows += 1
            try:
                parsed_score = json.loads(score_components)
                final_score = float(parsed_score["final_score"])
                score_values.append(final_score)
            except (TypeError, ValueError, KeyError, json.JSONDecodeError):
                score_parse_errors.append(row.get("rank", "?"))
            mechanism = (row.get("mechanism_hypothesis") or "").lower()
            if mechanism and "unresolved" not in mechanism and "requires target" not in mechanism:
                mechanism_rows += 1
            if row.get("validation_readouts"):
                experimental_rows += 1
            detail_fields = [
                "library_id",
                "parent_inchikey",
                "target_or_pathway",
                "evidence_level",
                "lipid_score",
                "safety_score",
                "uncertainty_penalty",
                "mechanism_hypothesis",
                "validation_readouts",
                "evidence_refs",
                "library_source",
            ]
            missing_details = [field for field in detail_fields if field in cols and not row.get(field)]
            if missing_details:
                status_flags.append(
                    f"row_{row.get('rank', '?')}_missing_evidence_fields:{','.join(missing_details)}"
                )
            else:
                detailed_rows += 1

    checks.append(
        {
            "id": "top10_filled",
            "ok": filled >= 10,
            "detail": f"filled_rows={filled}/10 placeholders_or_empty_struct={pending_placeholder}",
        }
    )
    if filled < 10:
        status_flags.append("pending_library_nomination")
    ranks_ok = sorted(valid_ranks) == list(range(1, 11))
    checks.append(
        {
            "id": "top10_ranks",
            "ok": ranks_ok,
            "detail": f"ranks={sorted(valid_ranks)}",
        }
    )
    if not ranks_ok:
        status_flags.append("top10_rank_sequence_invalid")
    unique_parents_ok = len(parent_keys) == len(set(parent_keys)) and len(parent_keys) >= 10
    checks.append(
        {
            "id": "top10_parent_identity_unique",
            "ok": unique_parents_ok,
            "detail": f"parent_keys={len(parent_keys)} unique={len(set(parent_keys))}",
        }
    )
    if not unique_parents_ok:
        status_flags.append("top10_parent_identity_incomplete_or_duplicate")
    checks.append(
        {
            "id": "top10_evidence_complete",
            "ok": detailed_rows >= 10,
            "detail": f"detailed_rows={detailed_rows}/10",
        }
    )
    if detailed_rows < 10:
        status_flags.append("top10_evidence_fields_incomplete")

    identity_check = identity_rows >= 10 and bool(row_hashes) and all(
        value == expected_library_hash for value in row_hashes
    ) and not identity_mismatches and not source_mismatches
    checks.append(
        {
            "id": "top10_library_identity_fields",
            "ok": identity_check,
            "detail": (
                f"rows_with_identity={identity_rows}/10; hashes={len(row_hashes)}; "
                f"identity_mismatches={identity_mismatches[:5]}; "
                f"source_mismatches={source_mismatches[:5]}"
            ),
        }
    )
    if not identity_check:
        status_flags.append("top10_library_identity_fields_incomplete")
    ranking_check = (
        ranking_rows >= 10
        and len(score_values) >= 10
        and not score_parse_errors
        and all(left >= right for left, right in zip(score_values, score_values[1:]))
    )
    checks.append(
        {
            "id": "top10_ranking_basis",
            "ok": ranking_check,
            "detail": (
                f"rows_with_ranking_basis={ranking_rows}/10; "
                f"scores={score_values[:10]}; parse_errors={score_parse_errors}"
            ),
        }
    )
    if not ranking_check:
        status_flags.append("top10_ranking_basis_incomplete")
    mechanism_check = mechanism_rows >= 10
    checks.append(
        {
            "id": "top10_mechanism_hypotheses",
            "ok": mechanism_check,
            "detail": f"rows_with_mechanism_hypothesis={mechanism_rows}/10",
        }
    )
    if not mechanism_check:
        status_flags.append("top10_mechanism_hypotheses_incomplete")
    experimental_check = experimental_rows >= 10
    checks.append(
        {
            "id": "top10_experimental_mapping",
            "ok": experimental_check,
            "detail": f"rows_with_validation_readouts={experimental_rows}/10",
        }
    )
    if not experimental_check:
        status_flags.append("top10_experimental_mapping_incomplete")

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


def write_validation_report(
    run_dir: Path,
    result: dict[str, Any],
    *,
    language: str = "zh",
) -> Path:
    run_dir = Path(run_dir)
    sub = run_dir / "submission"
    sub.mkdir(parents=True, exist_ok=True)
    output_language = normalize_output_language(language)
    json_path = sub / "validate_submission.json"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if output_language == "en":
        title = "# AI4S submission validation"
        ok_label = "ok"
        flags_label = "flags"
        check_header = "| check | ok | detail |"
        yes = "yes"
        no = "NO"
    else:
        title = "# AI4S 提交校验"
        ok_label = "是否通过"
        flags_label = "状态标记"
        check_header = "| 检查项 | 通过 | 详情 |"
        yes = "是"
        no = "否"
    md_lines = [
        title,
        "",
        f"- {ok_label}: **{result['ok']}**",
        f"- {flags_label}: `{', '.join(result.get('status_flags') or []) or 'none'}`",
        "",
        check_header,
        "|---|---|---|",
    ]
    for c in result.get("checks") or []:
        md_lines.append(
            f"| `{c['id']}` | {yes if c['ok'] else no} | {c.get('detail', '')} |"
        )
    md_path = sub / "validate_submission.md"
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    return md_path


def write_ai4s_readme(run_dir: Path, *, language: str = "zh") -> Path:
    run_dir = Path(run_dir)
    sub = run_dir / "submission"
    sub.mkdir(parents=True, exist_ok=True)
    path = sub / "README_AI4S.md"
    if normalize_output_language(language) == "en":
        lines = [
            "# AI4S Submission Helper",
            "",
            "The agent identity remains the general E-Drug Lab drug-discovery policy in `config/SOUL.md`.",
            "Use these commands only for the life-science competition submission context.",
            "",
            "```bash",
            "masld-agent competition-brief --language en",
            "masld-agent export-top10-template --output submission/top10_nomination.csv",
            "masld-agent hepg2-plan --run-dir . --language en",
            "masld-agent dual-readout-lint --text proposal.md",
            "masld-agent validate-submission --run-dir . --language en",
            "masld-agent pack-submission --run-dir . --output submission/ai4s_bundle.zip --language en",
            "```",
            "",
            "- Top10 candidates must come from the official SDF; empty identity fields remain pending.",
            "- Mechanism and method Markdown may be exported to PDF after validation.",
            "",
        ]
    else:
        lines = [
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
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def write_hepg2_plan(
    run_dir: Path,
    *,
    competition_config: Optional[Path] = None,
    language: str = "zh",
) -> Path:
    run_dir = Path(run_dir)
    cfg = load_competition_config(competition_config or DEFAULT_COMPETITION)
    readouts = cfg.get("experimental_readouts") or {}
    plan = cfg.get("experimental_validation_plan") or {}
    mechs = cfg.get("mechanisms_of_interest") or []

    genes: list[str] = []
    targets_csv = run_dir / "targets_ranked.csv"
    if targets_csv.is_file():
        with targets_csv.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                gene = (row.get("gene_symbol") or "").strip()
                if gene:
                    genes.append(gene)

    english = normalize_output_language(language) == "en"
    if english:
        lines = [
            "# HepG2-FFA Dual-Readout Validation Plan",
            "",
            f"> System: {readouts.get('system', 'HepG2-FFA')}",
            "",
            str(readouts.get("effective_hit_definition", "")).strip(),
            "",
            "## Readouts",
            "",
            "1. Lipid accumulation/lipid-lowering effect: retain neutral-lipid or lipid-droplet raw and normalized values.",
            "2. Cell viability/cytotoxicity: collect matched viability and morphology controls to exclude cytotoxic false positives.",
            "",
            "## Experimental design",
            "",
            f"- Model: {plan.get('model', 'HepG2 cells with FFA-induced lipid accumulation')}.",
            f"- FFA induction: {plan.get('induction', 'Optimize the induction window and viability in a pilot')}.",
            f"- Concentration-response: {plan.get('concentration_response', 'Use the same concentration series for lipid and viability readouts')}.",
            f"- Exposure: {plan.get('exposure', 'Pre-register and keep exposure identical across candidates')}.",
            f"- Replicates: {plan.get('replicates', 'Use independent experiments with technical replicates')}.",
            f"- Lipid readout: {plan.get('lipid_readout', 'Normalize lipid-droplet or neutral-lipid signal to viable-cell number')}.",
            f"- Viability readout: {plan.get('viability_readout', 'Use matched viability and morphology readouts')}.",
            f"- Provisional hit rule: {plan.get('provisional_hit_rule', 'Require lipid reduction with preserved viability; reject cytotoxic false positives')}.",
            f"- Toxicity exclusion: {plan.get('toxicity_rule', 'Exclude lipid reduction accompanied by viability loss')}.",
            "- Report lipid lowering and viability together.",
            "- Controls:",
        ]
    else:
        lines = [
            "# HepG2-FFA 双读出验证方案",
            "",
            f"> 体系：{readouts.get('system', 'HepG2-FFA')}",
            "",
            str(readouts.get("effective_hit_definition", "")).strip(),
            "",
            "## 读出指标",
            "",
            "1. 脂质蓄积/降脂效应：保留中性脂或脂滴原始值与归一化值。",
            "2. 细胞活力/细胞毒性：同步活力和形态对照，排除细胞毒性假阳性。",
            "",
            "## 实验设计",
            "",
            f"- 模型：{plan.get('model', 'HepG2 cells with FFA-induced lipid accumulation')}。",
            f"- FFA 诱导：{plan.get('induction', '先做诱导窗口和活力预实验')}。",
            f"- 浓度反应：{plan.get('concentration_response', '同一浓度梯度同步检测脂质与活力')}。",
            f"- 暴露时间：{plan.get('exposure', '预注册并对所有候选保持一致')}。",
            f"- 重复：{plan.get('replicates', '独立重复实验并保留技术重复')}。",
            f"- 脂质读出：{plan.get('lipid_readout', '脂滴/中性脂读出并按活细胞数归一化')}。",
            f"- 活力读出：{plan.get('viability_readout', '同步细胞活力与形态读出')}。",
            f"- 暂定命中规则：{plan.get('provisional_hit_rule', '脂质下降且活力保持，不把毒性假阳性算作命中')}。",
            f"- 毒性排除：{plan.get('toxicity_rule', '活力下降伴随脂质下降时排除')}。",
            "- 必须同步报告降脂与活力。",
            "- 对照：",
        ]
    for control in plan.get("controls") or ["vehicle_control", "FFA_model_control"]:
        lines.append(f"  - {control}")
    if english:
        lines += ["", "## Target and mechanism linkage", ""]
        if genes:
            lines.append("Targets represented in this run:")
            lines.extend(
                f"- {gene}: add target/pathway expression, phosphorylation, or flux readouts."
                for gene in genes
            )
        else:
            lines.append("- No targets_ranked.csv was supplied; resolve the target or record phenotype-first uncertainty.")
        lines += [
            "",
            "## Mechanism pathway checklist",
            "",
            ", ".join(str(mechanism) for mechanism in mechs),
            "",
            "## False-positive exclusion",
            "",
            "- Do not count a candidate as an effective low-toxicity hit when viability materially decreases.",
            "- Pre-register toxicity thresholds, replicate strategy, and confirmatory retesting rules.",
            "",
            "## Per-candidate validation mapping",
            "",
            "Each Top10 row must retain the official library ID, parent InChIKey, library hash, ranking basis, toxicity evidence status, mechanism hypothesis, and linked readouts; experimental results must be appended without overwriting nomination fields.",
            "",
            f"Mechanism follow-up: {plan.get('mechanism_follow_up', 'Test target engagement and pathway direction while retaining alternative mechanisms and falsifiers')}.",
            "",
        ]
    else:
        lines += ["", "## 与靶点/机制衔接", ""]
        if genes:
            lines.append("本 run 涉及靶点：")
            lines.extend(f"- {gene}：补充该靶点/通路下的表达、磷酸化或通量读出。" for gene in genes)
        else:
            lines.append("- 未提供 targets_ranked.csv；需解析靶点，或明确记录 phenotype-first 不确定性。")
        lines += [
            "",
            "## 机制通路 checklist",
            "",
            ", ".join(str(mechanism) for mechanism in mechs),
            "",
            "## 假阳性排除",
            "",
            "- 活力明显下降时，候选不计为有效低毒命中。",
            "- 实验前写明毒性阈值、重复策略和确认性复测规则。",
            "",
            "## 候选逐行验证映射",
            "",
            "每个 Top10 行必须保留官方库 ID、parent InChIKey、库哈希、排序依据、毒性证据状态、机制假说和对应读出；实验结果追加时不得覆盖提名字段。",
            "",
            f"机制跟进：{plan.get('mechanism_follow_up', '对存活候选进行靶点参与和通路方向验证，并保留替代机制与证伪条件')}。",
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
    language: str = "zh",
) -> Path:
    run_dir = Path(run_dir)
    output_zip = Path(output_zip)
    output_zip.parent.mkdir(parents=True, exist_ok=True)

    write_ai4s_readme(run_dir, language=language)
    write_hepg2_plan(run_dir, competition_config=competition_config, language=language)

    sub = run_dir / "submission"
    sub.mkdir(parents=True, exist_ok=True)
    tmpl = sub / "top10_nomination.csv"
    if not tmpl.is_file() and not (top10_csv and Path(top10_csv).is_file()):
        export_top10_template(tmpl, load_competition_config(competition_config or DEFAULT_COMPETITION))

    result = validate_submission(
        run_dir, top10_csv=top10_csv, competition_config=competition_config
    )
    write_validation_report(run_dir, result, language=language)

    if normalize_output_language(language) == "en":
        checklist_lines = [
            "# SUBMISSION_CHECKLIST",
            "",
            f"- validation_ok: {result['ok']}",
            f"- status_flags: {', '.join(result.get('status_flags') or []) or 'none'}",
            "",
            "Required submission evidence:",
            "1. Top10 CSV with official-library identities and lipid/toxicity evidence.",
            "2. Mechanism and validation plan (PDF; proposal plus HepG2 plan is acceptable).",
            "3. Method and reproducibility materials (method.md / Docker / repository).",
            "",
            "See validate_submission.md.",
            "",
        ]
    else:
        checklist_lines = [
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
    checklist = sub / "SUBMISSION_CHECKLIST.md"
    checklist.write_text("\n".join(checklist_lines), encoding="utf-8")

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
        "nomination_contract.json",
        "evidence_task_plan.json",
        "target_evidence.json",
        "structure_candidates.csv",
        "selected_structure.json",
        "pocket_manifest.json",
        "compound_evidence.jsonl",
        "toxicity_evidence.csv",
        "nomination_scorecard.csv",
        "top10_nomination.csv",
        "mechanism_validation.md",
        "mechanism_validation.pdf",
        "evidence_provenance.json",
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
