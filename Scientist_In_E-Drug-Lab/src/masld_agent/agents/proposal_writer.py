"""Proposal / method writers."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from masld_agent.models import CompetitionProfile, TargetHypothesis
from masld_agent.tools.ai4s_brief import normalize_output_language


def write_proposal_md(
    path: Path,
    *,
    profile: CompetitionProfile,
    hypotheses: Iterable[TargetHypothesis],
    language: str = "zh",
) -> None:
    hyps = list(hypotheses)
    english = normalize_output_language(language) == "en"
    if english:
        lines = [
            f"# Proposal — {profile.competition_name}",
            "",
            f"> **{profile.competition_scope_warning.strip()}**",
            "",
            f"- Competition URL: {profile.competition_url}",
            f"- Active disease scope: **{profile.disease_active.value}**",
            "- Agent role: target hypothesis and mechanism; compound Top10 library nomination is handled by the evidence route.",
            "",
            "## Executive summary",
            "",
            "This proposal ranks mechanistic small-molecule inhibitor targets relevant to early hepatocyte lipid overload and lipotoxicity. Claims are evidence-gated; unverified literature is excluded from final tables.",
            "",
            "## Ranked target hypotheses",
            "",
        ]
    else:
        lines = [
            f"# 候选方案 — {profile.competition_name}",
            "",
            f"> **{profile.competition_scope_warning.strip()}**",
            "",
            f"- 赛事网址：{profile.competition_url}",
            f"- 当前疾病范围：**{profile.disease_active.value}**",
            "- Agent 角色：靶点假说与机制分析；化合物 Top10 库内提名由证据流程负责。",
            "",
            "## 摘要",
            "",
            "本方案对与早期肝细胞脂质负荷和脂毒性相关的机制性小分子靶点进行排序。所有结论均受证据门禁约束，未经核验的文献不进入最终表格。",
            "",
            "## 靶点假说排序",
            "",
        ]
    for i, h in enumerate(hyps, 1):
        total = h.scores.total
        if english:
            lines += [
                f"### {i}. {h.gene_symbol} ({h.uniprot_id or 'UniProt n/a'})",
                "",
                f"- Novelty class: `{h.novelty_class.value}`",
                f"- Score total: {total if total is not None else 'n/a'} (missing dims: {', '.join(h.scores.missing_dimensions) or 'none'})",
                f"- Scientific significance: {h.scientific_significance or 'see evidence table'}",
                f"- Clinical significance: {h.clinical_significance or 'see evidence table'}",
                f"- Uncertainty: {h.uncertainty}",
                "",
                "Evidence (verified only):",
                "",
            ]
        else:
            lines += [
                f"### {i}. {h.gene_symbol}（{h.uniprot_id or 'UniProt 未提供'}）",
                "",
                f"- 新颖性分类：`{h.novelty_class.value}`",
                f"- 总分：{total if total is not None else '未提供'}（缺失维度：{', '.join(h.scores.missing_dimensions) or '无'}）",
                f"- 科学意义：{h.scientific_significance or '见证据表'}",
                f"- 临床意义：{h.clinical_significance or '见证据表'}",
                f"- 不确定性：{h.uncertainty}",
                "",
                "已核验证据：",
                "",
            ]
        for e in h.evidence:
            if not e.verified:
                continue
            cite = e.pmid or e.doi or e.url or "source-only"
            lines.append(f"- {e.title or e.supports_claim} [{cite}] ({e.source})")
        if h.structures:
            lines.append("")
            lines.append("Structures:" if english else "结构：")
            for s in h.structures:
                af = " [AlphaFold prediction]" if s.is_alphafold else ""
                lines.append(
                    f"- {s.pdb_id} reso={s.resolution_A} method={s.method}{af} — {s.selection_reason}"
                )
        if h.pockets:
            lines.append("")
            lines.append("Pockets:" if english else "口袋：")
            for p in h.pockets:
                lines.append(
                    f"- {p.pocket_type}: residues {', '.join(p.key_residues)} ({p.selection_reason})"
                )
        if h.ligands:
            lines.append("")
            lines.append("Reference ligands:" if english else "参考配体：")
            for lig in h.ligands:
                lines.append(
                    f"- {lig.name} role=`{lig.role.value}` CID={lig.pubchem_cid} "
                    f"SMILES=`{lig.smiles}`"
                )
        lines.append("")

    if english:
        lines += [
            "## Validation outline",
            "",
            "For each top target, use HepG2-FFA lipid accumulation plus parallel viability, orthogonal mechanism assays, and optional organoid or animal follow-up. Do not claim established efficacy without clinical citations.",
            "",
        ]
    else:
        lines += [
            "## 验证概要",
            "",
            "每个优先靶点均应采用 HepG2-FFA 脂质蓄积与平行细胞活力读出，配合正交机制实验，必要时再做类器官或动物研究。没有临床引用时不得声称已证明有效。",
            "",
        ]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_method_md(
    path: Path,
    *,
    profile: CompetitionProfile,
    offline: bool,
    language: str = "zh",
) -> None:
    if normalize_output_language(language) == "en":
        text = f"""# Method — Scientist_In_E-Drug-Lab

## Scope warning

{profile.competition_scope_warning.strip()}

## Pipeline

1. Competition Requirement Parser → structured `CompetitionProfile` (JSON).
2. Target Candidate Generator → curated mechanism seed panel (not LLM-only memory).
3. Evidence Retrieval → Europe PMC / PubMed / UniProt / Open Targets (when online).
4. Novelty Critic → established / emerging / novel_hypothesis.
5. Structure & Pocket → RCSB PDB (+ explicit AlphaFold labeling).
6. Ligand Reference → PubChem / optional ChEMBL with role tags.
7. Molecular Evaluation → RDKit descriptors + PAINS; docking optional (Vina).
8. Deterministic scoring (`config/scoring.yaml`) — missing dims never scored as 1.0.
9. Evidence Critic → opposing risks / uncertainty.
10. Proposal Writer → proposal.md, method.md, machine_readable_report.json.

## Reproducibility

- Offline mode: `masld-agent offline-demo --fixture tests/fixtures/hsd17b13`
- Online mode: `masld-agent run --competition config/competition_life_science.yaml`
- HTTP responses cached under `.cache/http` with SHA256 metadata.
- Hermes competition eval mode disables auto skill mutation / uncontrolled memory.

## Offline flag

offline={offline}
"""
    else:
        text = f"""# 方法 — Scientist_In_E-Drug-Lab

## 范围警告

{profile.competition_scope_warning.strip()}

## 流程

1. 赛事要求解析器 → 结构化 `CompetitionProfile`（JSON）。
2. 靶点候选生成器 → 机制种子面板，不依赖 LLM 记忆。
3. 证据检索 → 在线时使用 Europe PMC、PubMed、UniProt、Open Targets。
4. 新颖性审查 → established、emerging、novel_hypothesis。
5. 结构与口袋 → RCSB PDB，并明确标记 AlphaFold 预测。
6. 配体参考 → PubChem，以及可选的 ChEMBL 角色标记。
7. 分子评价 → RDKit 描述符与 PAINS；对接仅在适用时执行。
8. 确定性评分（`config/scoring.yaml`）→ 缺失维度不得按 1.0 计分。
9. 证据审查 → 记录相反风险与不确定性。
10. 报告写入 → `proposal.md`、`method.md`、`machine_readable_report.json`。

## 可复现性

- 离线模式：`masld-agent offline-demo --fixture tests/fixtures/hsd17b13`
- 在线模式：`masld-agent run --competition config/competition_life_science.yaml`
- HTTP 响应缓存于 `.cache/http`，并保存 SHA256 元数据。
- Hermes 竞赛评估模式关闭自动 skill 修改和无控制记忆。

## 离线标记

offline={offline}
"""
    path.write_text(text, encoding="utf-8")
