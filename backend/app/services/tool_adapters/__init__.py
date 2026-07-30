"""Tool adapters — bridge pipeline orchestrator to existing services."""
from __future__ import annotations

from typing import Any

from app.core.tool_registry import get_tool


class ToolAdapterError(Exception):
    pass


async def execute_tool(
    tool_id: str,
    context: dict[str, Any],
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Execute a single tool against pipeline context. Returns result metadata."""
    params = params or {}
    tool = get_tool(tool_id)
    molecules = context.get("molecules") or []

    if tool_id == "pdb-fetch":
        return {"message": "Target prep recorded", "target": context.get("target")}

    if tool_id == "sdf-upload":
        import os

        from app.config import get_settings
        from app.core.paths import get_repo_root
        from app.db import get_sessionmaker
        from app.services.sdf_sync import sync_sdf_library

        settings = get_settings()
        if settings.sdf_directory:
            sdf_dir = os.path.abspath(settings.sdf_directory)
        else:
            sdf_dir = os.path.abspath(get_repo_root() / "molecules" / "sdf")
        db = get_sessionmaker()()
        try:
            result = sync_sdf_library(db, sdf_dir)
            return {
                "message": f"Synced {result.total_conformers_added} conformers",
                "sync_result": result.to_dict(),
            }
        finally:
            db.close()

    if tool_id == "rdkit-descriptors" and molecules:
        from app.services.admet_service import apply_druglikeness_filter

        smiles = [m.get("smiles", "") for m in molecules]
        names = [m.get("name") or m.get("smiles", "")[:20] for m in molecules]
        results = apply_druglikeness_filter(smiles, rules=["lipinski", "veber"], names=names)
        passed = sum(1 for r in results if r.passed)
        return {
            "message": f"ADMET filter: {passed}/{len(results)} passed",
            "filter": {"total": len(results), "passed": passed, "results": [r.to_dict() for r in results]},
        }

    if tool_id == "admet-ai" and molecules:
        from app.services.admet_service import predict_batch

        smiles = [m.get("smiles", "") for m in molecules]
        names = [m.get("name") or m.get("smiles", "")[:20] for m in molecules]
        predictions = predict_batch(smiles, names=names)
        return {
            "message": f"ADMET-AI: {len(predictions)} predictions",
            "predictions": [p.to_dict() for p in predictions],
        }

    if tool_id == "vina-dock" and molecules:
        from app.services.docking_prep import dock_smiles_batch

        target = context.get("target") or {}
        target_id = target.get("id")
        target_pdb_id = target.get("pdbId") or target.get("pdb_id") or params.get("pdb_id")
        dock_mols = [
            {
                "molecule_id": m.get("id", f"mol-{i}"),
                "smiles": m.get("smiles", ""),
                "name": m.get("name") or m.get("smiles", "")[:20],
            }
            for i, m in enumerate(molecules)
        ]
        result = await dock_smiles_batch(
            dock_mols,
            target_id=target_id,
            target_pdb_id=target_pdb_id,
            exhaustiveness=4,
            timeout_per_molecule=20,
            concurrency=2,
        )
        succeeded = sum(1 for r in result.get("results", []) if r.get("success"))
        return {"message": f"Vina: {succeeded} docked", "dock": result}

    if tool_id == "orthogonal-rank" and molecules:
        from app.services.orthogonal_scoring import rank_by_orthogonal_rescore

        candidates = []
        for m in molecules:
            step_results = m.get("stepResults") or m.get("step_results") or {}
            vina = step_results.get("vina-dock") or {}
            affinity = vina.get("affinity_kcal_mol")
            metric_name = "docking_affinity"
            if affinity is None:
                for key in ("drugclip", "tame-vs"):
                    vs = step_results.get(key) or {}
                    if isinstance(vs.get("score"), (int, float)):
                        affinity = vs["score"]
                        metric_name = "vs_screen_score"
                        break
            if affinity is None:
                continue
            candidates.append({
                "molecule_id": m.get("id"),
                "name": m.get("name") or m.get("smiles", "")[:20],
                "metrics": [
                    {
                        "metric_name": metric_name,
                        "value": float(affinity),
                        "model_name": "vina" if metric_name == "docking_affinity" else "vs",
                        "method_family": "docking" if metric_name == "docking_affinity" else "screening",
                        "direction": "lower_is_better",
                        "priority": 1,
                    }
                ],
            })
        if not candidates:
            raise ToolAdapterError("No rankable candidates")
        ranked = rank_by_orthogonal_rescore(
            candidates=candidates,
            primary_metric=candidates[0]["metrics"][0]["metric_name"],
        )
        return {"message": f"Ranked {len(ranked.get('ranked', []))} candidates", "ranking": ranked}

    if tool_id == "vav1-pipeline":
        return {"message": "VAV1 pipeline delegated to /api/v1/vav1-rl/run", "delegated": True}

    if tool.status == "placeholder":
        return {"message": f"{tool.name} is not yet implemented", "skipped": True}

    return {"message": f"Tool {tool_id} executed (no-op adapter)", "tool_id": tool_id}
