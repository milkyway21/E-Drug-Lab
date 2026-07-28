#!/usr/bin/env python3
"""端到端 DiffDynamic 网页工作流测试（镜像前端 PipelineRunner local 模式）。

步骤：靶点下载 → DiffDynamic 生成+提取 → 入库 → ADMET → Vina → 正交排序

用法：
  python3 backend/scripts/e2e_diffdynamic_web_workflow.py
  python3 backend/scripts/e2e_diffdynamic_web_workflow.py --base-url http://localhost:8001 --pdb 4HHB
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any


def api(
    base: str,
    method: str,
    path: str,
    body: dict | None = None,
    timeout: int = 120,
) -> dict[str, Any]:
    url = f"{base.rstrip('/')}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()
        raise RuntimeError(f"{method} {path} -> HTTP {exc.code}: {detail}") from exc


def poll_job(base: str, job_id: str, label: str, max_wait: int = 7200) -> dict[str, Any]:
    start = time.time()
    while time.time() - start < max_wait:
        job = api(base, "GET", f"/api/v1/diffdynamic/jobs/{job_id}")
        status = job.get("status")
        elapsed = int(time.time() - start)
        print(f"  [{label}] {status} ({elapsed}s)", flush=True)
        if status == "completed":
            return job.get("result") or {}
        if status == "failed":
            raise RuntimeError(f"{label} failed: {job.get('error')}")
        time.sleep(5)
    raise TimeoutError(f"{label} timeout after {max_wait}s")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8001")
    parser.add_argument("--pdb", default="4HHB", help="测试用 PDB ID（小结构，下载快）")
    parser.add_argument("--round-id", type=int, default=9001)
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument("--skip-generate", action="store_true", help="跳过 GPU 生成（仅测后续步骤）")
    args = parser.parse_args()
    base = args.base_url

    print("=" * 60)
    print("DiffDynamic 网页全流程 E2E 测试")
    print(f"API: {base}")
    print("=" * 60)

    # 0. 健康检查
    health = api(base, "GET", "/health", timeout=10)
    print(f"\n[0] Health: {health}")

    status = api(base, "GET", "/api/v1/diffdynamic/status", timeout=30)
    print(f"[0] DiffDynamic status: conda={status.get('conda_env_exists')} root={status.get('root_exists')}")
    if not status.get("conda_env_exists"):
        print("WARN: conda env diffdynamic 未检测到，生成步骤可能失败")

    # 1. 靶点准备
    print(f"\n[1] Target prep: download PDB {args.pdb}")
    dl = api(base, "POST", "/api/v1/targets/download", {"pdb_id": args.pdb})
    print(f"    download: {dl.get('status')} -> {dl.get('file_path')}")

    target = api(
        base,
        "POST",
        "/api/v1/targets",
        {"pdb_id": args.pdb, "name": f"E2E {args.pdb}", "source": "pdb"},
    )
    target_id = target["id"]
    print(f"    target_id: {target_id}")

    pre = api(base, "POST", f"/api/v1/targets/{target_id}/preprocess", {})
    print(f"    preprocess: {pre.get('status')}")

    # 重新读取 target 拿 structure_path
    targets = api(base, "GET", "/api/v1/targets?page_size=5")
    structure_path = None
    for t in targets.get("targets", []):
        if t["id"] == target_id:
            structure_path = t.get("structure_path")
            break
    print(f"    structure_path: {structure_path}")

    sdf_filename = f"diffdynamic_round_{args.round_id}.sdf"

    if not args.skip_generate:
        # 2. DiffDynamic 生成
        print(f"\n[2] DiffDynamic generate (batch_size={args.batch_size}, auto_extract=True)")
        gen = api(
            base,
            "POST",
            "/api/v1/diffdynamic/generate",
            {
                "mode": "custom",
                "target_id": target_id,
                "round_id": args.round_id,
                "batch_size": args.batch_size,
                "auto_extract": True,
                "max_samples": 5,
                "remove_fragments": True,
                "async_run": True,
            },
            timeout=60,
        )
        job_id = gen.get("job_id")
        if not job_id:
            raise RuntimeError(f"未获得 job_id: {gen}")
        print(f"    job_id: {job_id}")
        result = poll_job(base, job_id, "DiffDynamic generate+extract", max_wait=7200)
        sdf_path = result.get("sdf_path") or (result.get("extract") or {}).get("sdf_path")
        print(f"    ok={result.get('ok')} sdf={sdf_path}")

        # 3. 入库
        print("\n[3] Ingest SDF to molecule DB")
        ingest = api(
            base,
            "POST",
            "/api/v1/diffdynamic/ingest",
            {"round_id": args.round_id, "sdf_path": sdf_path},
        )
        print(f"    ingest: {ingest.get('sdf_path')} sync={ingest.get('sync', {}).get('total_conformers_added')}")
    else:
        print("\n[2-3] SKIP generate (using existing SDF in DB)")

    # 4. 读取分子
    print("\n[4] Load molecules from DB")
    mols_resp = api(
        base,
        "GET",
        f"/api/v1/molecule-db/molecules?page_size=50&sdf_filename={sdf_filename}",
    )
    molecules = [m for m in mols_resp.get("molecules", []) if m.get("smiles")]
    print(f"    loaded: {len(molecules)} molecules")
    if not molecules:
        raise RuntimeError("无可用分子，生成/入库失败")

    smiles = [m["smiles"] for m in molecules]
    names = [m.get("name") or m["smiles"][:20] for m in molecules]
    mol_ids = [m["id"] for m in molecules]

    # 5. ADMET
    print("\n[5] ADMET filter (RDKit Lipinski/Veber)")
    admet = api(
        base,
        "POST",
        "/api/v1/admet/filter",
        {"smiles": smiles, "names": names, "rules": ["lipinski", "veber"]},
    )
    passed = sum(1 for r in admet.get("results", []) if r.get("passed"))
    print(f"    passed: {passed}/{len(smiles)}")

    # 6. Vina 对接
    print("\n[6] Vina batch dock (timeout=20s/mol)")
    dock = api(
        base,
        "POST",
        "/api/v1/affinity/dock/batch",
        {
            "molecules": [
                {
                    "molecule_id": mol_ids[i],
                    "smiles": smiles[i],
                    "name": names[i],
                }
                for i in range(len(smiles))
            ],
            "target_id": target_id,
            "target_pdb_id": args.pdb,
            "exhaustiveness": 4,
            "timeout_per_molecule": 20,
            "concurrency": 2,
        },
        timeout=600,
    )
    vina_ok = dock.get("vina_available")
    succeeded = sum(1 for r in dock.get("results", []) if r.get("success"))
    print(f"    vina_available={vina_ok} docked={succeeded}/{len(smiles)}")
    if not vina_ok or succeeded == 0:
        print("WARN: Vina 不可用或全部失败，排序步骤可能跳过")

    # 7. 正交排序
    print("\n[7] Orthogonal ranking")
    candidates = []
    for i, mid in enumerate(mol_ids):
        item = next((r for r in dock.get("results", []) if r.get("molecule_id") == mid), None)
        if not item or not item.get("success"):
            continue
        aff = item.get("affinity_kcal_mol")
        if aff is None:
            continue
        admet_r = admet.get("results", [{}])[i] if i < len(admet.get("results", [])) else {}
        admet_score = 0.7 if admet_r.get("passed") else 0.3
        candidates.append(
            {
                "molecule_id": mid,
                "name": names[i],
                "metrics": [
                    {
                        "metric_name": "docking_affinity",
                        "value": aff,
                        "model_name": "vina",
                        "method_family": "docking",
                        "direction": "lower_is_better",
                        "priority": 1,
                    },
                    {
                        "metric_name": "admet_composite_score",
                        "value": admet_score,
                        "model_name": "rdkit-filter",
                        "method_family": "admet",
                        "direction": "higher_is_better",
                        "priority": 2,
                    },
                ],
            }
        )

    if not candidates:
        print("    SKIP: 无可用对接分数")
    else:
        rank = api(
            base,
            "POST",
            "/api/v1/ranking/orthogonal-rescore",
            {
                "candidates": candidates,
                "primary_metric": "docking_affinity",
                "orthogonal_metric": "admet_composite_score",
                "target_pdb_id": args.pdb,
            },
        )
        ranked = rank.get("ranked", [])
        print(f"    ranked: {len(ranked)} candidates")
        for i, row in enumerate(ranked[:5]):
            print(
                f"      #{i+1} {row.get('standard_name') or row.get('name')} "
                f"score={row.get('final_score')} vina={row.get('primary_value')}"
            )

    print("\n" + "=" * 60)
    print("E2E 测试完成")
    print(f"网页验证: http://localhost:3001/workflow")
    print("  选择预设「DiffDynamic Full Pipeline」→ Local 模式 → Run")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"\nE2E FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
