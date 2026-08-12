"""AI4S life-science competition brief helpers (offline-first)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from masld_agent.config import DEFAULT_COMPETITION, PKG_ROOT, load_competition_config

BRIEF_DEFAULT = PKG_ROOT / "config" / "briefs" / "life_zh.md"


def normalize_output_language(language: Optional[str] = None) -> str:
    """Return the supported human-report language code."""
    return "en" if str(language or "zh").lower().startswith("en") else "zh"


def load_ai4s_config(path: Optional[Path] = None) -> dict[str, Any]:
    return load_competition_config(path or DEFAULT_COMPETITION)


def resolve_brief_path(cfg: Optional[dict[str, Any]] = None) -> Path:
    data = cfg or load_ai4s_config()
    rel = data.get("brief_local") or "config/briefs/life_zh.md"
    p = PKG_ROOT / rel
    return p if p.is_file() else BRIEF_DEFAULT


def format_competition_brief(
    cfg: Optional[dict[str, Any]] = None,
    *,
    language: str = "zh",
) -> str:
    """Render the competition brief in Chinese by default or English on request."""
    data = cfg or load_ai4s_config()
    output_language = normalize_output_language(language)
    if output_language == "en":
        return _format_competition_brief_english(data)
    scoring = data.get("scoring_dimensions") or {}
    readouts = data.get("experimental_readouts") or {}
    artifacts = data.get("submission_artifacts") or []
    resources = data.get("resources") or {}
    schedule = data.get("schedule_notes") or {}
    mechs = data.get("mechanisms_of_interest") or []
    constraints = data.get("hard_constraints") or {}

    lines: list[str] = [
        f"# {data.get('competition_name', 'AI4S Life Science')}",
        "",
        f"- 官网赛道: {data.get('competition_url', '')}",
        f"- 赛事主页: {data.get('home_url', resources.get('competition_home', ''))}",
        f"- 官方简报: {data.get('rules_url', '')}",
        f"- 本地缓存: {resolve_brief_path(data)}",
        f"- 默认疾病预设: {data.get('disease_default', 'MASLD')}",
        "",
        "## 实验双读出（HepG2-FFA）",
        "",
        f"- 体系: {readouts.get('system', 'HepG2-FFA')}",
    ]
    for r in readouts.get("readouts") or []:
        lines.append(f"- {r.get('id')}: {r.get('label')}")
    lines += [
        "",
        f"**有效命中**: {str(readouts.get('effective_hit_definition', '')).strip()}",
        "",
        "## 评分维度",
        "",
    ]
    for key, meta in scoring.items():
        if isinstance(meta, dict):
            lines.append(
                f"- {key}: **{meta.get('weight', '?')}** — {meta.get('description', '')}"
            )
    lines += ["", "## 提交物", ""]
    for art in artifacts:
        req = "必交" if art.get("required") else "可选"
        lines.append(f"- [{req}] {art.get('label')} (`{art.get('id')}`): {art.get('notes', '')}")
    lines += ["", "## 硬约束", ""]
    for cid, text in constraints.items():
        lines.append(f"- **{cid}**: {text}")
    lines += ["", "## 机制通路关注点", "", ", ".join(str(m) for m in mechs), "", "## 赛程（以官网为准）", ""]
    for k, v in schedule.items():
        lines.append(f"- {k}: {v}")
    lines += ["", "## 资源入口", ""]
    for k, v in resources.items():
        lines.append(f"- {k}: {v}")
    lines += [
        "",
        "## 边界说明",
        "",
        "- 本 Agent 人设仍是 e-drug-lab 通用药物发现助手（见 config/SOUL.md）。",
        "- AI4S/MASLD 仅为竞赛工具预设；库内 Top10（C1）需填官方 SDF 来源分子，",
        "  未填时校验标记 `pending_library_nomination`。",
        "",
    ]
    return "\n".join(lines)


def _format_competition_brief_english(data: dict[str, Any]) -> str:
    scoring = data.get("scoring_dimensions") or {}
    readouts = data.get("experimental_readouts") or {}
    artifacts = data.get("submission_artifacts") or []
    resources = data.get("resources") or {}
    schedule = data.get("schedule_notes") or {}
    mechs = data.get("mechanisms_of_interest") or []
    constraints = data.get("hard_constraints") or {}
    lines = [
        f"# {data.get('competition_name', 'AI4S Life Science')}",
        "",
        f"- Competition URL: {data.get('competition_url', '')}",
        f"- Home page: {data.get('home_url', resources.get('competition_home', ''))}",
        f"- Official brief: {data.get('rules_url', '')}",
        f"- Local brief: {resolve_brief_path(data)}",
        f"- Default disease preset: {data.get('disease_default', 'MASLD')}",
        "",
        "## HepG2-FFA dual readout",
        "",
        f"- System: {readouts.get('system', 'HepG2-FFA')}",
    ]
    for readout in readouts.get("readouts") or []:
        lines.append(f"- {readout.get('id')}: {readout.get('label')}")
    lines += [
        "",
        f"**Effective hit**: {str(readouts.get('effective_hit_definition', '')).strip()}",
        "",
        "## Scoring dimensions",
        "",
    ]
    for key, meta in scoring.items():
        if isinstance(meta, dict):
            lines.append(
                f"- {key}: **{meta.get('weight', '?')}** — {meta.get('description', '')}"
            )
    lines += ["", "## Submission artifacts", ""]
    for artifact in artifacts:
        required = "required" if artifact.get("required") else "optional"
        lines.append(
            f"- [{required}] {artifact.get('label')} (`{artifact.get('id')}`): "
            f"{artifact.get('notes', '')}"
        )
    lines += ["", "## Hard constraints", ""]
    for constraint_id, text in constraints.items():
        lines.append(f"- **{constraint_id}**: {text}")
    lines += [
        "",
        "## Mechanism pathways",
        "",
        ", ".join(str(mechanism) for mechanism in mechs),
        "",
        "## Schedule (official rules control)",
        "",
    ]
    lines.extend(f"- {key}: {value}" for key, value in schedule.items())
    lines += ["", "## Resource entry points", ""]
    lines.extend(f"- {key}: {value}" for key, value in resources.items())
    lines += [
        "",
        "## Scope boundary",
        "",
        "- The agent identity remains the general E-Drug Lab drug-discovery assistant.",
        "- AI4S/MASLD is a competition preset; Top10 candidates must come from the official library.",
        "",
    ]
    return "\n".join(lines)


def dual_readout_keywords(cfg: Optional[dict[str, Any]] = None) -> dict[str, list[str]]:
    data = cfg or load_ai4s_config()
    out: dict[str, list[str]] = {}
    for r in (data.get("experimental_readouts") or {}).get("readouts") or []:
        rid = str(r.get("id") or "")
        out[rid] = [str(k).lower() for k in (r.get("keywords") or [])]
    return out


def lint_dual_readout(text: str, cfg: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Return whether text covers lipid + viability dual readout."""
    lower = (text or "").lower()
    keys = dual_readout_keywords(cfg)
    lipid_keys = keys.get("lipid_accumulation") or [
        "lipid",
        "降脂",
        "脂滴",
        "lipid droplet",
        "nile red",
        "steatosis",
        "ffa",
        "脂质蓄积",
    ]
    tox_keys = keys.get("cell_viability") or [
        "viability",
        "活力",
        "毒性",
        "cytotoxicity",
        "celltiter",
        "mtt",
        "假阳性",
    ]
    lipid_hits = [k for k in lipid_keys if k.lower() in lower]
    tox_hits = [k for k in tox_keys if k.lower() in lower]
    ok = bool(lipid_hits) and bool(tox_hits)
    missing: list[str] = []
    if not lipid_hits:
        missing.append("lipid_accumulation")
    if not tox_hits:
        missing.append("cell_viability")
    return {
        "ok": ok,
        "missing": missing,
        "lipid_hits": lipid_hits,
        "viability_hits": tox_hits,
        "message": (
            "双读出齐全（降脂 + 细胞活力/毒性）"
            if ok
            else f"缺少读出维度: {', '.join(missing)}（仅写降脂不写活力易产生毒性假阳性）"
        ),
    }


def lint_hepg2_validation_plan(text: str) -> dict[str, Any]:
    """Check that a proposed HepG2-FFA plan is experimentally actionable."""
    lower = (text or "").lower()
    requirements = {
        "model": ("hepg2", "hep g2"),
        "ffa_induction": ("ffa", "free fatty acid"),
        "concentration_response": ("concentration", "dose-response", "dose response"),
        "controls": ("vehicle", "溶剂对照"),
        "replicates": ("replicate", "重复", "independent experiment"),
        "lipid_readout": ("lipid", "脂质", "脂滴", "nile red"),
        "viability_readout": ("viability", "活力", "细胞毒性"),
        "hit_threshold": ("80%", "80 %", "threshold", "阈值", "不明显损伤"),
        "false_positive_rule": ("false positive", "假阳性", "cytotoxic"),
        "mechanism_follow_up": ("target engagement", "mechanism", "机制", "通路"),
    }
    hits = {
        key: [term for term in terms if term.lower() in lower]
        for key, terms in requirements.items()
    }
    missing = [key for key, values in hits.items() if not values]
    return {
        "ok": not missing,
        "missing": missing,
        "hits": hits,
        "message": (
            "HepG2-FFA 方案包含模型、双读出、对照、剂量反应、重复、判定阈值和机制复核"
            if not missing
            else f"HepG2-FFA 方案缺少: {', '.join(missing)}"
        ),
    }
