"""Markdown / JSON / PDF reporting."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Iterable

from masld_agent.agents.proposal_writer import write_method_md, write_proposal_md
from masld_agent.models import CompetitionProfile, TargetHypothesis


def write_json_report(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def write_warnings_md(path: Path, warnings: Iterable[str]) -> None:
    lines = ["# Warnings", ""]
    for w in warnings:
        lines.append(f"- {w}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def try_export_pdf(md_path: Path, pdf_path: Path) -> str:
    if shutil.which("pandoc") is None:
        cmd = f"pandoc {md_path} -o {pdf_path}"
        return f"skipped_missing_dependency: pandoc not found. Run: `{cmd}`"
    subprocess.run(
        ["pandoc", str(md_path), "-o", str(pdf_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if pdf_path.exists():
        return f"wrote {pdf_path}"
    return f"pandoc_failed; try manually: pandoc {md_path} -o {pdf_path}"


def write_standard_reports(
    out_dir: Path,
    *,
    profile: CompetitionProfile,
    hypotheses: list[TargetHypothesis],
    offline: bool,
    extra_warnings: list[str] | None = None,
) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    proposal = out_dir / "proposal.md"
    method = out_dir / "method.md"
    write_proposal_md(proposal, profile=profile, hypotheses=hypotheses)
    write_method_md(method, profile=profile, offline=offline)

    report = {
        "competition": profile.model_dump(mode="json"),
        "targets": [h.model_dump(mode="json") for h in hypotheses],
        "competition_scope_warning": profile.competition_scope_warning,
    }
    write_json_report(out_dir / "machine_readable_report.json", report)

    warns = [profile.competition_scope_warning]
    warns.extend(extra_warnings or [])
    for h in hypotheses:
        warns.extend(h.warnings)
    write_warnings_md(out_dir / "warnings.md", warns)

    pdf_note = try_export_pdf(proposal, out_dir / "proposal.pdf")
    return {"proposal": str(proposal), "method": str(method), "pdf": pdf_note}
