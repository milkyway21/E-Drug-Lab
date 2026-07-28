"""AI4S life-science competition brief helpers (offline-first)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from masld_agent.config import DEFAULT_COMPETITION, PKG_ROOT, load_competition_config

BRIEF_DEFAULT = PKG_ROOT / "config" / "briefs" / "life_zh.md"


def load_ai4s_config(path: Optional[Path] = None) -> dict[str, Any]:
    return load_competition_config(path or DEFAULT_COMPETITION)


def resolve_brief_path(cfg: Optional[dict[str, Any]] = None) -> Path:
    data = cfg or load_ai4s_config()
    rel = data.get("brief_local") or "config/briefs/life_zh.md"
    p = PKG_ROOT / rel
    return p if p.is_file() else BRIEF_DEFAULT


def format_competition_brief(cfg: Optional[dict[str, Any]] = None) -> str:
    """Human-readable Chinese brief for CLI / chat tools."""
    data = cfg or load_ai4s_config()
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
