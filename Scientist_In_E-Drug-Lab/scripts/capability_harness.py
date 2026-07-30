#!/usr/bin/env python3
"""Capability harness: send commands / call tools, detect completion, score PASS|PARTIAL|GATE|FAIL.

Usage:
  python scripts/capability_harness.py
  python scripts/capability_harness.py --cases scripts/capability_cases/core.yaml
  python scripts/capability_harness.py --api-base http://127.0.0.1:8001

Writes:
  memory/TOOL_CAPABILITY.md
  reports/capability_harness_<timestamp>.md
  Soft-appends GLOBAL_HISTORY.md
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib import error, request

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

DEFAULT_API = os.environ.get("EDRUG_API_BASE", "http://127.0.0.1:8001").rstrip("/")
SCORES = ("PASS", "PARTIAL", "GATE", "FAIL")


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _http(method: str, url: str, body: Optional[dict] = None, timeout: float = 60.0) -> tuple[int, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = request.Request(url, data=data, headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw else {})
    except error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {"detail": raw}
        return exc.code, parsed
    except Exception as exc:  # noqa: BLE001
        return 0, {"error": f"{type(exc).__name__}: {exc}"}


def _load_yaml(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text) or {}
    except ImportError:
        # Minimal YAML subset for our harness files (no nested complexity beyond lists/dicts)
        return _minimal_yaml(text)


def _minimal_yaml(text: str) -> dict[str, Any]:
    """Very small YAML loader for harness cases if PyYAML missing."""
    # Prefer json if file is actually json
    stripped = text.strip()
    if stripped.startswith("{"):
        return json.loads(stripped)
    # Fallback: require PyYAML
    raise RuntimeError("PyYAML required to parse capability YAML (pip install pyyaml)")


def score_md_response(payload: dict[str, Any], *, expect_status: Optional[str] = None) -> str:
    status = str(payload.get("status") or "")
    if status in {"stub"} or payload.get("stub") is True:
        return "FAIL"
    if expect_status and status == expect_status:
        return "PASS"
    if status == "unavailable":
        return "GATE"
    if status == "gated":
        return "GATE"
    if status == "completed" and payload.get("engine") == "schrodinger_desmond":
        return "PASS"
    if status == "completed" and "dry_prep" in str(payload.get("message") or "").lower():
        return "PASS"
    if status in {"completed", "queued", "running"}:
        return "PASS" if not expect_status or status == expect_status else "PARTIAL"
    if status == "failed":
        return "FAIL"
    return "PARTIAL"


def run_case(case: dict[str, Any], *, api_base: str) -> dict[str, Any]:
    cid = case.get("id") or "unnamed"
    kind = case.get("kind") or "http"
    enabled = case.get("enabled", True)
    if not enabled or case.get("not_run_yet"):
        return {
            "id": cid,
            "kind": kind,
            "score": "GATE",
            "message": case.get("skip_reason") or "not_run_yet / disabled template",
            "evidence": {},
            "duration_s": 0.0,
        }

    t0 = time.time()
    try:
        if kind == "http_md_submit":
            body = case.get("body") or {"mode": "dry_prep", "confirm": False}
            code, payload = _http("POST", f"{api_base}/api/v1/affinity/md", body, timeout=90)
            expect = case.get("expect_status") or "completed"
            score = score_md_response(payload if isinstance(payload, dict) else {}, expect_status=expect)
            if code == 0:
                score = "FAIL"
            if isinstance(payload, dict) and payload.get("status") == "stub":
                score = "FAIL"
            return {
                "id": cid,
                "kind": kind,
                "score": score,
                "http_status": code,
                "message": (payload or {}).get("message") if isinstance(payload, dict) else str(payload),
                "evidence": payload,
                "duration_s": round(time.time() - t0, 3),
            }

        if kind == "http_md_status":
            task_id = case.get("task_id")
            if not task_id:
                # use previous submit from evidence file? require explicit
                return {
                    "id": cid,
                    "kind": kind,
                    "score": "FAIL",
                    "message": "task_id required",
                    "evidence": {},
                    "duration_s": round(time.time() - t0, 3),
                }
            code, payload = _http("GET", f"{api_base}/api/v1/affinity/md/{task_id}", timeout=30)
            score = score_md_response(payload if isinstance(payload, dict) else {})
            if code == 404:
                score = "FAIL"
            return {
                "id": cid,
                "kind": kind,
                "score": score,
                "http_status": code,
                "message": (payload or {}).get("message") if isinstance(payload, dict) else str(payload),
                "evidence": payload,
                "duration_s": round(time.time() - t0, 3),
            }

        if kind == "agent_md_dry_prep":
            from masld_agent.platform.schrodinger_md_tools import schrodinger_md_submit, schrodinger_md_status

            submit = schrodinger_md_submit(
                mode="dry_prep",
                confirm=False,
                target_id=case.get("target_id") or "HSD17B13",
                api_base=api_base,
            )
            score = score_md_response(submit, expect_status="completed")
            status_ev = None
            if submit.get("task_id"):
                status_ev = schrodinger_md_status(
                    task_id=str(submit["task_id"]),
                    target_id=case.get("target_id") or "HSD17B13",
                    api_base=api_base,
                )
                if status_ev.get("status") not in {"completed", "queued", "running", "gated"}:
                    if status_ev.get("status") == "stub":
                        score = "FAIL"
            return {
                "id": cid,
                "kind": kind,
                "score": score,
                "message": submit.get("message"),
                "evidence": {
                    "submit": submit,
                    "status": status_ev,
                    "note": (
                        "Direct Python call of agent tool helpers (HTTP to MD API). "
                        "Does NOT launch Hermes chat or load funnel-desmond-* SKILL.md."
                    ),
                },
                "duration_s": round(time.time() - t0, 3),
            }

        if kind == "hermes_md_tools_registered":
            # Call hermes_plugin.register with a mock ctx — no live Hermes LLM / skill load.
            import masld_agent.hermes_plugin as hp

            required = {"schrodinger_md_submit", "schrodinger_md_status"}
            registered: dict[str, Any] = {}

            class _Ctx:
                def register_tool(self, name=None, toolset=None, schema=None, handler=None, **_kw):
                    registered[str(name)] = {
                        "toolset": toolset,
                        "schema_name": (schema or {}).get("name") if isinstance(schema, dict) else None,
                        "handler_callable": callable(handler),
                    }

                def register_command(self, *a, **k):
                    return None

                def register_cli_command(self, *a, **k):
                    return None

            hp.register(_Ctx())
            missing = sorted(required - set(registered))
            handlers_ok = all(
                registered.get(n, {}).get("handler_callable") for n in required if n in registered
            )
            score = "PASS" if not missing and handlers_ok else "FAIL"
            return {
                "id": cid,
                "kind": kind,
                "score": score,
                "message": (
                    "Hermes plugin registered MD tools (mock ctx); not live skill/Hermes chat"
                    if score == "PASS"
                    else f"missing={missing} handlers_ok={handlers_ok}"
                ),
                "evidence": {
                    "required": sorted(required),
                    "registered_md": {k: registered[k] for k in required if k in registered},
                    "tool_count": len(registered),
                    "live_hermes": False,
                    "skill_invocation": False,
                },
                "duration_s": round(time.time() - t0, 3),
            }

        if kind == "funnel_autopilot_tools_registered":
            import masld_agent.hermes_plugin as hp

            required = {
                "funnel_plan",
                "funnel_preflight",
                "funnel_run_stage",
                "funnel_validate_stage",
                "funnel_status",
                "funnel_autopilot",
                "funnel_autopilot_status",
            }
            registered: dict[str, Any] = {}

            class _Ctx:
                def register_tool(self, name=None, schema=None, handler=None, **_kw):
                    registered[str(name)] = {
                        "schema": schema,
                        "handler_callable": callable(handler),
                    }

                def register_command(self, *a, **k):
                    return None

            hp.register(_Ctx())
            missing = sorted(required - set(registered))
            final_count_only = (
                registered.get("funnel_autopilot", {})
                .get("schema", {})
                .get("parameters", {})
                .get("required")
                == ["final_count"]
            )
            profile_schema = (
                registered.get("funnel_autopilot", {})
                .get("schema", {})
                .get("parameters", {})
                .get("properties", {})
                .get("profile", {})
            )
            dual_profiles = profile_schema.get("enum") == ["full", "test"]
            handlers_ok = all(
                registered.get(name, {}).get("handler_callable") for name in required
            )
            score = (
                "PASS"
                if not missing and handlers_ok and final_count_only and dual_profiles
                else "FAIL"
            )
            return {
                "id": cid,
                "kind": kind,
                "score": score,
                "message": (
                    "Final-count-only funnel autopilot and persistent status tools registered"
                    if score == "PASS"
                    else (
                        f"missing={missing} handlers_ok={handlers_ok} "
                        f"final_count_only={final_count_only} dual_profiles={dual_profiles}"
                    )
                ),
                "evidence": {
                    "required": sorted(required),
                    "profile_schema": profile_schema,
                    "missing": missing,
                    "handlers_ok": handlers_ok,
                    "final_count_only": final_count_only,
                    "live_hermes": False,
                },
                "duration_s": round(time.time() - t0, 3),
            }

        if kind == "hermes_handler_md_dry_prep":
            # Exercise Hermes plugin handler wrappers (same entry as register_tool handlers).
            import masld_agent.hermes_plugin as hp

            raw = hp._schrodinger_md_submit(
                {
                    "mode": "dry_prep",
                    "confirm": False,
                    "target_id": case.get("target_id") or "HSD17B13",
                    "api_base": api_base,
                }
            )
            submit = json.loads(raw) if isinstance(raw, str) else (raw or {})
            score = score_md_response(submit if isinstance(submit, dict) else {}, expect_status="completed")
            return {
                "id": cid,
                "kind": kind,
                "score": score,
                "message": (submit or {}).get("message") if isinstance(submit, dict) else str(submit),
                "evidence": {
                    "submit": submit,
                    "via_handler": "hermes_plugin._schrodinger_md_submit",
                    "note": "Handler path only; still not funnel-desmond-* skill / live Hermes chat.",
                },
                "duration_s": round(time.time() - t0, 3),
            }

        if kind == "skill_md_presence":
            skill_names = case.get("skills") or [
                "funnel-desmond-short-md",
                "funnel-desmond-long-md",
                "dd-md-desmond",
                "edrug-capability-check",
            ]
            search_roots = [
                Path(p)
                for p in (
                    case.get("skill_roots")
                    or [
                        str(Path.home() / ".claude" / "skills"),
                        str(Path.home() / ".cursor" / "skills"),
                        str(ROOT / "skills"),
                    ]
                )
            ]
            must_contain = case.get("must_contain") or [
                "schrodinger_md_submit",
                "SCHRODINGER",
            ]
            conda_note_markers = case.get("conda_note_markers") or [
                "conda",
                "diffdynamic",
            ]
            found: dict[str, Any] = {}
            missing_skills: list[str] = []
            weak_docs: list[str] = []
            for name in skill_names:
                path = None
                for root in search_roots:
                    cand = root / name / "SKILL.md"
                    if cand.is_file():
                        path = cand
                        break
                if path is None:
                    missing_skills.append(name)
                    found[name] = {"path": None, "ok": False}
                    continue
                text = path.read_text(encoding="utf-8")
                has_markers = all(m in text for m in must_contain)
                # Desmond skills must clarify: Desmond uses SCHRODINGER, not conda create;
                # conda diffdynamic is only for DiffDynamic / Python analysis side paths.
                has_conda_clarity = all(m.lower() in text.lower() for m in conda_note_markers)
                ok = has_markers and has_conda_clarity
                if not ok:
                    weak_docs.append(name)
                found[name] = {
                    "path": str(path),
                    "ok": ok,
                    "has_markers": has_markers,
                    "has_conda_clarity": has_conda_clarity,
                }
            if missing_skills:
                score = "FAIL"
                msg = f"missing skills: {missing_skills}"
            elif weak_docs:
                score = "PARTIAL"
                msg = f"skills present but conda/SCHRODINGER notes weak: {weak_docs}"
            else:
                score = "PASS"
                msg = "Desmond/capability skills found with agent-tool + conda clarity notes"
            return {
                "id": cid,
                "kind": kind,
                "score": score,
                "message": msg,
                "evidence": {
                    "found": found,
                    "skill_invocation": False,
                    "note": "File presence/docs check only — harness does not execute SKILL.md via Hermes.",
                },
                "duration_s": round(time.time() - t0, 3),
            }

        if kind == "env_probe_desmond_conda":
            # Desmond MD does NOT require conda activate/create; DiffDynamic does.
            # Avoid importing masld_agent.platform.paths (pulls pydantic_settings via config).
            sch = Path(
                os.environ.get("SCHRODINGER")
                or os.environ.get("MASLD_SCHRODINGER")
                or "/opt/schrodinger2023-3"
            )
            conda_name = os.environ.get("MASLD_DIFFDYNAMIC_CONDA_NAME", "diffdynamic")
            conda_root = Path(
                os.environ.get(
                    "MASLD_DIFFDYNAMIC_CONDA",
                    f"/home/user/anaconda3/envs/{conda_name}",
                )
            )
            multisim = sch / "utilities" / "multisim"
            conda_py = conda_root / "bin" / "python"
            multisim_ok = multisim.is_file()
            conda_ok = conda_py.is_file()
            evidence = {
                "desmond_needs_conda": False,
                "desmond_needs_schrodinger": True,
                "SCHRODINGER": str(sch),
                "schrodinger_dir_ok": sch.is_dir(),
                "multisim_ok": multisim_ok,
                "diffdynamic_conda_name": conda_name,
                "diffdynamic_conda": str(conda_root),
                "diffdynamic_conda_python_ok": conda_ok,
                "note": (
                    "Agent MD path (schrodinger_md_*) does not activate/create conda. "
                    "Use $SCHRODINGER for Desmond; conda env 'diffdynamic' is for DiffDynamic only."
                ),
            }
            # PASS if we correctly probe + document split; GATE if SCHRODINGER missing (env unavailable)
            if not sch.is_dir():
                score = "GATE"
                msg = "SCHRODINGER install missing — Desmond gated; conda not required for MD"
            elif not multisim_ok:
                score = "PARTIAL"
                msg = "SCHRODINGER present but multisim missing; conda still N/A for Desmond"
            else:
                score = "PASS"
                msg = (
                    f"Desmond env OK (multisim); conda '{conda_name}' "
                    f"{'present' if conda_ok else 'absent'} (DiffDynamic only, not MD)"
                )
            return {
                "id": cid,
                "kind": kind,
                "score": score,
                "message": msg,
                "evidence": evidence,
                "duration_s": round(time.time() - t0, 3),
            }

        if kind == "ui_navigate":
            from masld_agent.ui_command_bus import drain_ui_commands, ui_navigate

            sid = case.get("session_id") or f"harness-{int(time.time())}"
            path = case.get("path") or "/workflow"
            nav = ui_navigate(sid, path)
            cmds = drain_ui_commands(sid)
            local_ok = nav.get("status") == "ok" or any(
                c.get("type") == "navigate" and c.get("path") == path for c in cmds
            )
            code, payload = _http(
                "POST",
                f"{api_base}/api/v1/agent/ui-commands",
                {"session_id": sid, "type": "navigate", "path": path},
                timeout=15,
            )
            http_ok = code in {200, 201} or (
                isinstance(payload, dict) and payload.get("status") in {"ok", "queued", None}
            )
            score = "PASS" if (local_ok or http_ok) else "FAIL"
            return {
                "id": cid,
                "kind": kind,
                "score": score,
                "message": f"navigate {path}",
                "evidence": {"nav": nav, "http": payload, "http_status": code, "session_id": sid},
                "duration_s": round(time.time() - t0, 3),
            }

        if kind == "ui_set_target":
            from masld_agent.ui_command_bus import ui_set_target

            sid = case.get("session_id") or f"harness-{int(time.time())}"
            tid = case.get("target_id") or "HSD17B13"
            out = ui_set_target(sid, tid, case.get("name") or tid)
            code, payload = _http(
                "POST",
                f"{api_base}/api/v1/agent/ui-commands",
                {"session_id": sid, "type": "set_target", "target_id": tid, "name": tid},
                timeout=15,
            )
            score = "PASS" if code in {200, 201} or out.get("ok", True) else "PARTIAL"
            return {
                "id": cid,
                "kind": kind,
                "score": score,
                "message": f"set_target {tid}",
                "evidence": {"out": out, "http": payload, "http_status": code},
                "duration_s": round(time.time() - t0, 3),
            }

        if kind == "template":
            return {
                "id": cid,
                "kind": kind,
                "score": "GATE",
                "message": case.get("skip_reason") or "template placeholder — not-run-yet",
                "evidence": {"tool": case.get("tool"), "api_path": case.get("api_path")},
                "duration_s": 0.0,
            }

        return {
            "id": cid,
            "kind": kind,
            "score": "FAIL",
            "message": f"unknown kind: {kind}",
            "evidence": {},
            "duration_s": round(time.time() - t0, 3),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "id": cid,
            "kind": kind,
            "score": "FAIL",
            "message": f"{type(exc).__name__}: {exc}",
            "evidence": {"traceback": traceback.format_exc()[-2000:]},
            "duration_s": round(time.time() - t0, 3),
        }


def render_markdown(results: list[dict[str, Any]], *, api_base: str, title: str) -> str:
    counts = {s: 0 for s in SCORES}
    for r in results:
        counts[r.get("score", "FAIL")] = counts.get(r.get("score", "FAIL"), 0) + 1
    lines = [
        f"# {title}",
        "",
        f"- generated: `{_utc()}`",
        f"- api_base: `{api_base}`",
        f"- totals: PASS={counts['PASS']} PARTIAL={counts['PARTIAL']} GATE={counts['GATE']} FAIL={counts['FAIL']}",
        "",
        "## Scoring legend",
        "",
        "- **PASS**: tool behaved correctly (incl. Desmond dry_prep completed)",
        "- **PARTIAL**: partial success / degraded path",
        "- **GATE**: intentionally blocked / unavailable / not-run-yet template",
        "- **FAIL**: stub treated as success, crash, or wrong semantics",
        "",
        "## What this harness does / does not do",
        "",
        "- **Does**: HTTP MD dry_prep; Python `schrodinger_md_*` helpers; Hermes plugin `register()` mock; skill file presence; SCHRODINGER vs conda probe; UI bus",
        "- **Does not**: launch Hermes chat, load/execute `funnel-desmond-*` / `dd-md-desmond` SKILL.md, or `conda activate`/`conda create` for Desmond",
        "- Desmond uses `$SCHRODINGER`/`multisim`; conda `diffdynamic` is DiffDynamic-only (not MD)",
        "",
        "## Completion criteria (Desmond)",
        "",
        "- production PASS: `cms` + `traj` + `md_summary` + done flag",
        "- dry_prep / smoke gate ≠ production PASS",
        "- never treat `stub` / fake completed as success",
        "",
        "## Results",
        "",
        "| id | kind | score | seconds | message |",
        "|----|------|-------|---------|---------|",
    ]
    for r in results:
        msg = str(r.get("message") or "").replace("|", "/").replace("\n", " ")[:120]
        lines.append(
            f"| `{r.get('id')}` | `{r.get('kind')}` | **{r.get('score')}** | {r.get('duration_s')} | {msg} |"
        )
    lines.append("")
    lines.append("## Evidence (compact)")
    lines.append("")
    for r in results:
        ev = r.get("evidence") or {}
        compact = {
            "status": ev.get("status") if isinstance(ev, dict) else None,
            "task_id": ev.get("task_id") if isinstance(ev, dict) else None,
            "job_dir": ev.get("job_dir") if isinstance(ev, dict) else None,
        }
        if isinstance(ev, dict) and "submit" in ev:
            compact = {
                "submit_status": (ev.get("submit") or {}).get("status"),
                "task_id": (ev.get("submit") or {}).get("task_id"),
                "job_dir": (ev.get("submit") or {}).get("job_dir"),
                "via": (ev.get("submit") or {}).get("via"),
                "via_handler": ev.get("via_handler"),
                "note": ev.get("note"),
            }
        elif isinstance(ev, dict) and ("registered_md" in ev or "found" in ev or "desmond_needs_conda" in ev):
            compact = {k: ev.get(k) for k in list(ev.keys())[:12]}
        lines.append(f"### `{r.get('id')}` — {r.get('score')}")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(compact, indent=2, ensure_ascii=False, default=str))
        lines.append("```")
        lines.append("")
    return "\n".join(lines) + "\n"


def soft_append_global_history(line: str) -> None:
    path = ROOT / "memory" / "GLOBAL_HISTORY.md"
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    marker = "## 任务摘要（新→旧）"
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entry = f"- **{stamp} capability harness**: {line}\n"
    if entry.strip() in text:
        return
    if marker in text:
        text = text.replace(marker + "\n", marker + "\n\n" + entry, 1)
    else:
        text += "\n" + entry
    path.write_text(text, encoding="utf-8")


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="E-Drug Lab tool capability harness")
    ap.add_argument(
        "--cases",
        nargs="+",
        default=[
            str(ROOT / "scripts/capability_cases/core.yaml"),
            str(ROOT / "scripts/capability_cases/tool_matrix_templates.yaml"),
        ],
    )
    ap.add_argument("--api-base", default=DEFAULT_API)
    ap.add_argument("--report-dir", default=str(ROOT / "reports"))
    args = ap.parse_args(argv)

    all_cases: list[dict[str, Any]] = []
    for cpath in args.cases:
        p = Path(cpath)
        if not p.is_file():
            print(f"[skip missing] {p}", file=sys.stderr)
            continue
        doc = _load_yaml(p)
        cases = doc.get("cases") or []
        all_cases.extend(cases)

    results: list[dict[str, Any]] = []
    last_task_id: Optional[str] = None
    for case in all_cases:
        # Wire md status case to previous submit
        if case.get("kind") == "http_md_status" and not case.get("task_id") and last_task_id:
            case = {**case, "task_id": last_task_id}
        result = run_case(case, api_base=args.api_base.rstrip("/"))
        results.append(result)
        ev = result.get("evidence") or {}
        if isinstance(ev, dict) and ev.get("task_id"):
            last_task_id = str(ev["task_id"])
        if isinstance(ev, dict) and isinstance(ev.get("submit"), dict) and ev["submit"].get("task_id"):
            last_task_id = str(ev["submit"]["task_id"])
        print(f"[{result['score']}] {result['id']} — {result.get('message')}")

    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = report_dir / f"capability_harness_{stamp}.md"
    md = render_markdown(results, api_base=args.api_base, title="Tool Capability Harness Report")
    report_path.write_text(md, encoding="utf-8")

    # Also write under hsvpol if present
    hsv = Path("/home/user/Desktop/Ye/DiffDynamic/hsvpol/reports")
    if hsv.parent.is_dir():
        hsv.mkdir(parents=True, exist_ok=True)
        (hsv / f"capability_harness_{stamp}.md").write_text(md, encoding="utf-8")

    cap_path = ROOT / "memory" / "TOOL_CAPABILITY.md"
    cap_path.parent.mkdir(parents=True, exist_ok=True)
    cap_path.write_text(
        render_markdown(results, api_base=args.api_base, title="TOOL_CAPABILITY — live harness matrix"),
        encoding="utf-8",
    )

    counts = {s: sum(1 for r in results if r.get("score") == s) for s in SCORES}
    soft_append_global_history(
        f"PASS={counts['PASS']} PARTIAL={counts['PARTIAL']} GATE={counts['GATE']} FAIL={counts['FAIL']}; "
        f"report `{report_path}`"
    )
    print(f"Wrote {cap_path}")
    print(f"Wrote {report_path}")
    # Non-zero only if any FAIL among enabled non-template critical cases
    critical_fail = any(
        r["score"] == "FAIL"
        and r.get("kind")
        in {
            "http_md_submit",
            "http_md_status",
            "agent_md_dry_prep",
            "hermes_md_tools_registered",
            "hermes_handler_md_dry_prep",
            "skill_md_presence",
        }
        for r in results
    )
    return 1 if critical_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
