"""Minimal MCP stdio server exposing masld tools (optional extra)."""
from __future__ import annotations

import json

from masld_agent.paths import UnsafePathError, resolve_under


def main() -> None:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise SystemExit(
            "mcp package not installed. pip install 'scientist-in-e-drug-lab[mcp]'"
        ) from exc

    from masld_agent.config import PKG_ROOT
    from masld_agent.models import DiseaseScope
    from masld_agent.submission import pack_submission, validate_submission, write_validation_report
    from masld_agent.supervisor import run_offline_demo, run_pipeline
    from masld_agent.tools.ai4s_brief import format_competition_brief, load_ai4s_config

    mcp = FastMCP("scientist-in-e-drug-lab")

    @mcp.tool()
    def masld_offline_demo(fixture: str = "", output: str = "") -> str:
        try:
            fix = resolve_under(
                PKG_ROOT,
                fixture or None,
                default=PKG_ROOT / "tests/fixtures/hsd17b13",
            )
            out = resolve_under(
                PKG_ROOT,
                output or None,
                default=PKG_ROOT / "runs",
            )
        except UnsafePathError as exc:
            return json.dumps({"status": "error", "error": str(exc)})
        path = run_offline_demo(fix, out)
        return json.dumps({"status": "ok", "output_dir": str(path)})

    @mcp.tool()
    def masld_run(disease: str = "MASLD", top_targets: int = 10, online: bool = False) -> str:
        try:
            out_root = resolve_under(
                PKG_ROOT,
                "runs/demo",
                default=PKG_ROOT / "runs" / "demo",
            )
            path = run_pipeline(
                out_root,
                disease=DiseaseScope(disease),
                top_targets=top_targets,
                online=online,
            )
        except (UnsafePathError, ValueError) as exc:
            return json.dumps({"status": "error", "error": str(exc)})
        return json.dumps({"status": "ok", "output_dir": str(path)})

    @mcp.tool()
    def masld_competition_brief() -> str:
        return format_competition_brief(load_ai4s_config())

    @mcp.tool()
    def masld_validate_submission(run_dir: str = "", top10_csv: str = "") -> str:
        try:
            rd = resolve_under(
                PKG_ROOT,
                run_dir or None,
                default=PKG_ROOT / "runs",
            )
            t10 = None
            if top10_csv:
                t10 = resolve_under(PKG_ROOT, top10_csv, default=rd / "top10_nomination.csv")
        except UnsafePathError as exc:
            return json.dumps({"status": "error", "error": str(exc)})
        result = validate_submission(rd, top10_csv=t10)
        write_validation_report(rd, result)
        return json.dumps({"status": "ok", **result}, default=str)

    @mcp.tool()
    def masld_pack_submission(run_dir: str = "", output: str = "") -> str:
        try:
            rd = resolve_under(
                PKG_ROOT,
                run_dir or None,
                default=PKG_ROOT / "runs",
            )
            out = resolve_under(
                PKG_ROOT,
                output or None,
                default=rd / "submission" / "ai4s_bundle.zip",
            )
        except UnsafePathError as exc:
            return json.dumps({"status": "error", "error": str(exc)})
        path = pack_submission(rd, out)
        return json.dumps({"status": "ok", "zip": str(path)})

    @mcp.tool()
    def platform_catalog(system: str = "", entry_id: str = "", stage: str = "") -> str:
        from masld_agent.platform.catalog import get_entry, list_entries, summarize_systems

        if entry_id:
            e = get_entry(entry_id)
            return json.dumps({"status": "ok" if e else "error", "entry": e}, default=str)
        entries = list_entries(
            system=system or None,
            stage=stage or None,
        )
        return json.dumps(
            {"status": "ok", "summary": summarize_systems(), "entries": entries},
            default=str,
        )

    @mcp.tool()
    def platform_health() -> str:
        from masld_agent.platform.health import platform_health as _health

        return json.dumps(_health(), default=str)

    @mcp.tool()
    def diffdynamic_status() -> str:
        from masld_agent.platform.diffdynamic_tools import diffdynamic_status as _st

        return json.dumps(_st(), default=str)

    @mcp.tool()
    def diffdynamic_generate(
        protein_path: str = "",
        ligand_path: str = "",
        mode: str = "denovo_fast",
        molecule_path: str = "",
        batch_size: int = 20,
        sample_only: bool = True,
        confirm: bool = False,
        dry_run: bool = True,
        output_dir: str = "",
    ) -> str:
        from masld_agent.platform.diffdynamic_tools import diffdynamic_generate as _gen

        return json.dumps(
            _gen(
                protein_path=protein_path,
                ligand_path=ligand_path,
                mode=mode,
                molecule_path=molecule_path or None,
                batch_size=batch_size,
                sample_only=sample_only,
                confirm=confirm,
                dry_run=dry_run,
                output_dir=output_dir or None,
            ),
            default=str,
        )

    @mcp.tool()
    def diffdynamic_extract(
        pt_path: str = "",
        vina_modes: str = "none",
        output_dir: str = "",
        dry_run: bool = True,
    ) -> str:
        from masld_agent.platform.diffdynamic_tools import diffdynamic_extract as _ex

        return json.dumps(
            _ex(
                pt_path=pt_path,
                vina_modes=vina_modes,
                output_dir=output_dir or None,
                dry_run=dry_run,
            ),
            default=str,
        )

    @mcp.tool()
    def schrodinger_status() -> str:
        from masld_agent.platform.schrodinger_tools import schrodinger_status as _st

        return json.dumps(_st(), default=str)

    @mcp.tool()
    def schrodinger_dock(
        receptor_pdb: str = "",
        smiles: str = "",
        ligand_sdf: str = "",
        precision: str = "SP",
        confirm: bool = False,
        dry_run: bool = True,
        output_dir: str = "",
    ) -> str:
        from masld_agent.platform.schrodinger_tools import schrodinger_dock as _dock

        smi_list = [s.strip() for s in smiles.split(",") if s.strip()] if smiles else []
        return json.dumps(
            _dock(
                receptor_pdb=receptor_pdb,
                smiles=smi_list or None,
                ligand_sdf=ligand_sdf or None,
                precision=precision,
                confirm=confirm,
                dry_run=dry_run,
                output_dir=output_dir or None,
            ),
            default=str,
        )

    @mcp.tool()
    def schrodinger_mmgbsa(
        pose_path: str = "",
        confirm: bool = False,
        dry_run: bool = True,
        output_dir: str = "",
    ) -> str:
        from masld_agent.platform.schrodinger_tools import schrodinger_mmgbsa as _mm

        return json.dumps(
            _mm(
                pose_path=pose_path,
                confirm=confirm,
                dry_run=dry_run,
                output_dir=output_dir or None,
            ),
            default=str,
        )

    mcp.run()


if __name__ == "__main__":
    main()
