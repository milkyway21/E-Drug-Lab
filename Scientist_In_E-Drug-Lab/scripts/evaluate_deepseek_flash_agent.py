#!/usr/bin/env python3
"""Run and document a bounded Scientist evaluation on DeepSeek V4 Flash."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sqlite3
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
HERMES_HOME = ROOT / ".hermes"
STATE_DB = HERMES_HOME / "state.db"
HERMES = ROOT / ".venv/bin/hermes"
MODEL = "deepseek-v4-flash"
PROVIDER = "deepseek-official"
TOKEN_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "reasoning_tokens",
    "total_tokens",
    "api_calls",
)
SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(
        r"(?i)((?:api[_-]?key|auth[_-]?token|authorization|password|secret)"
        r"\s*[:=]\s*)[^\s,;\"']+"
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--include-usage",
        action="append",
        type=Path,
        default=[],
        help="Include an earlier Hermes --usage-file session in the transcript.",
    )
    parser.add_argument("--timeout", type=int, default=600)
    return parser.parse_args()


def redact(value: Any) -> str:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    for pattern in SECRET_PATTERNS:
        text = pattern.sub(
            lambda match: (match.group(1) if match.lastindex else "") + "[REDACTED]",
            text,
        )
    return text


def load_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'").strip('"')
    return values


def runtime_env() -> dict[str, str]:
    env = dict(os.environ)
    env.update(load_dotenv(HERMES_HOME / ".env"))
    env.update(
        {
            "HERMES_HOME": str(HERMES_HOME),
            "PYTHONPATH": f"{ROOT / 'src'}:{env.get('PYTHONPATH', '')}",
            "HERMES_ENABLE_PROJECT_PLUGINS": "true",
            "HERMES_INFERENCE_PROVIDER": PROVIDER,
            "HERMES_INFERENCE_MODEL": MODEL,
        }
    )
    return env


def load_usage(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"failed": True, "error": "usage file missing"}
    return json.loads(path.read_text(encoding="utf-8"))


def session_record(session_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    connection = sqlite3.connect(STATE_DB)
    connection.row_factory = sqlite3.Row
    try:
        session = connection.execute(
            "SELECT * FROM sessions WHERE id=?", (session_id,)
        ).fetchone()
        messages = connection.execute(
            "SELECT id, role, content, tool_call_id, tool_calls, tool_name, "
            "timestamp, token_count, finish_reason, reasoning, reasoning_content "
            "FROM messages WHERE session_id=? ORDER BY id",
            (session_id,),
        ).fetchall()
    finally:
        connection.close()
    if session is None:
        raise RuntimeError(f"Session absent from state DB: {session_id}")
    session_data = dict(session)
    message_data = []
    for row in messages:
        item = dict(row)
        for field in ("content", "tool_calls", "reasoning", "reasoning_content"):
            item[field] = redact(item.get(field) or "")
        message_data.append(item)
    return session_data, message_data


def extract_json(response: str) -> dict[str, Any] | None:
    start = response.find("{")
    end = response.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        payload = json.loads(response[start : end + 1])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def score_exact(response: str, _: dict[str, Any], __: Path) -> tuple[bool, str]:
    passed = response.strip() == "DEEPSEEK_FLASH_OK"
    return passed, "exact sentinel response" if passed else "sentinel mismatch"


def score_config(response: str, session: dict[str, Any], _: Path) -> tuple[bool, str]:
    lowered = response.lower().replace(",", "")
    markers = ("deepseek-official", MODEL, "1000000")
    passed = all(marker in lowered for marker in markers) and session["tool_call_count"] >= 1
    return passed, f"markers={all(marker in lowered for marker in markers)}, tools={session['tool_call_count']}"


def score_offline(response: str, session: dict[str, Any], eval_dir: Path) -> tuple[bool, str]:
    artifact_root = eval_dir / "offline_demo_artifacts"
    files = [path for path in artifact_root.rglob("*") if path.is_file()]
    passed = session["tool_call_count"] >= 1 and len(files) >= 3 and "error" not in response.lower()
    return passed, f"tools={session['tool_call_count']}, artifact_files={len(files)}"


def score_artifact_audit(response: str, session: dict[str, Any], eval_dir: Path) -> tuple[bool, str]:
    actual_names = {
        path.name
        for path in (eval_dir / "offline_demo_artifacts").rglob("*")
        if path.is_file()
    }
    mentioned = {name for name in actual_names if name in response}
    passed = session["tool_call_count"] >= 1 and len(mentioned) >= min(3, len(actual_names))
    return passed, f"tools={session['tool_call_count']}, files_mentioned={len(mentioned)}/{len(actual_names)}"


def score_triage(response: str, _: dict[str, Any], __: Path) -> tuple[bool, str]:
    payload = extract_json(response)
    selected = payload.get("selected", []) if payload else []
    selected_set = {str(item).upper() for item in selected}
    passed = selected_set == {"A", "C"}
    return passed, f"selected={sorted(selected_set)}"


def run_case(
    case: dict[str, Any],
    eval_dir: Path,
    env: dict[str, str],
    timeout: int,
) -> dict[str, Any]:
    case_id = case["id"]
    case_dir = eval_dir / case_id
    case_dir.mkdir(parents=True)
    prompt = case["prompt"]
    (case_dir / "prompt.txt").write_text(prompt + "\n", encoding="utf-8")
    usage_path = case_dir / "usage.json"
    started = time.time()
    command = [
        str(HERMES),
        "-z",
        prompt,
        "--usage-file",
        str(usage_path),
        "--provider",
        PROVIDER,
        "-m",
        MODEL,
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        exit_code = completed.returncode
        stdout = redact(completed.stdout)
        stderr = redact(completed.stderr)
    except subprocess.TimeoutExpired as exc:
        exit_code = 124
        stdout = redact(exc.stdout or "")
        stderr = redact(exc.stderr or "") + f"\nTIMEOUT after {timeout}s\n"
    ended = time.time()
    (case_dir / "response.txt").write_text(stdout, encoding="utf-8")
    (case_dir / "stderr.log").write_text(stderr, encoding="utf-8")

    usage = load_usage(usage_path)
    session_id = str(usage.get("session_id") or "")
    if session_id:
        session, messages = session_record(session_id)
    else:
        session, messages = {}, []
    scorer: Callable[[str, dict[str, Any], Path], tuple[bool, str]] = case["scorer"]
    passed, detail = (
        scorer(stdout, session, eval_dir)
        if exit_code == 0 and session
        else (False, f"exit={exit_code}, session_present={bool(session)}")
    )
    return {
        "case_id": case_id,
        "description": case["description"],
        "exit_code": exit_code,
        "duration_seconds": round(ended - started, 3),
        "passed": passed,
        "score_detail": detail,
        "usage": usage,
        "session": session,
        "messages": messages,
        "response": stdout,
    }


def imported_case(usage_path: Path) -> dict[str, Any]:
    usage = load_usage(usage_path)
    session, messages = session_record(str(usage["session_id"]))
    response = next(
        (message["content"] for message in reversed(messages) if message["role"] == "assistant"),
        "",
    )
    passed, detail = score_exact(response, session, usage_path.parent)
    return {
        "case_id": "00_connectivity",
        "description": "Official endpoint and exact-response connectivity",
        "exit_code": 0,
        "duration_seconds": round((session["ended_at"] or 0) - (session["started_at"] or 0), 3),
        "passed": passed,
        "score_detail": detail,
        "usage": usage,
        "session": session,
        "messages": messages,
        "response": response,
    }


def write_outputs(eval_dir: Path, results: list[dict[str, Any]]) -> None:
    transcript_jsonl = eval_dir / "conversation_transcript.jsonl"
    with transcript_jsonl.open("w", encoding="utf-8") as handle:
        for result in results:
            for message in result["messages"]:
                handle.write(
                    json.dumps(
                        {
                            "case_id": result["case_id"],
                            "session_id": result["usage"].get("session_id", ""),
                            **message,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )

    transcript_md = ["# DeepSeek V4 Flash 完整测试对话", ""]
    for result in results:
        transcript_md.extend(
            [
                f"## {result['case_id']} - {result['description']}",
                "",
                f"- session: `{result['usage'].get('session_id', '')}`",
                f"- result: `{'PASS' if result['passed'] else 'FAIL'}`",
                "",
            ]
        )
        for message in result["messages"]:
            label = message["role"]
            if message.get("tool_name"):
                label += f" ({message['tool_name']})"
            transcript_md.extend([f"### {label}", "", message.get("content") or "", ""])
            if message.get("tool_calls"):
                transcript_md.extend(["```json", message["tool_calls"], "```", ""])
    (eval_dir / "conversation_transcript.md").write_text(
        "\n".join(transcript_md), encoding="utf-8"
    )

    summary_fields = [
        "case_id",
        "session_id",
        "passed",
        "duration_seconds",
        "tool_call_count",
        *TOKEN_FIELDS,
    ]
    summary_rows = []
    for result in results:
        usage = result["usage"]
        session = result["session"]
        summary_rows.append(
            {
                "case_id": result["case_id"],
                "session_id": usage.get("session_id", ""),
                "passed": result["passed"],
                "duration_seconds": result["duration_seconds"],
                "tool_call_count": session.get("tool_call_count", 0),
                **{field: usage.get(field, 0) for field in TOKEN_FIELDS},
            }
        )
    with (eval_dir / "token_summary.csv").open(
        "w", newline="", encoding="utf-8-sig"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=summary_fields)
        writer.writeheader()
        writer.writerows(summary_rows)

    totals = {
        field: sum(int(row.get(field) or 0) for row in summary_rows)
        for field in TOKEN_FIELDS
    }
    passed_count = sum(bool(result["passed"]) for result in results)
    tool_cases = [result for result in results if result["session"].get("tool_call_count", 0)]
    report = [
        "# Scientist / DeepSeek V4 Flash 受控能力测试",
        "",
        f"- provider: `{PROVIDER}`",
        f"- model: `{MODEL}`",
        f"- cases: `{passed_count}/{len(results)} PASS`",
        f"- tool-using cases: `{len(tool_cases)}`",
        f"- input tokens: `{totals['input_tokens']}`",
        f"- output tokens: `{totals['output_tokens']}`",
        f"- reasoning tokens: `{totals['reasoning_tokens']}`",
        f"- total tokens: `{totals['total_tokens']}`",
        f"- API calls: `{totals['api_calls']}`",
        "- cost: provider pricing metadata is unavailable, so no monetary estimate is asserted.",
        "",
        "## Results",
        "",
        "| Case | Result | Tools | Input | Output | API calls | Seconds | Evidence |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for result, row in zip(results, summary_rows):
        report.append(
            f"| `{result['case_id']}` | {'PASS' if result['passed'] else 'FAIL'} | "
            f"{row['tool_call_count']} | {row['input_tokens']} | {row['output_tokens']} | "
            f"{row['api_calls']} | {row['duration_seconds']} | {result['score_detail']} |"
        )
    report.extend(
        [
            "",
            "## Interpretation",
            "",
            (
                "该测试只证明模型在受约束、短程、可验证任务上的表现；即使全部通过，"
                "也不能外推为可无人值守执行长周期药物发现或高成本计算。"
            ),
            "完整消息与工具调用见 `conversation_transcript.md/.jsonl`，逐轮用量见 "
            "`token_summary.csv`。",
            "",
        ]
    )
    (eval_dir / "evaluation_report_zh.md").write_text("\n".join(report), encoding="utf-8")
    manifest = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "provider": PROVIDER,
        "model": MODEL,
        "results": [
            {
                key: value
                for key, value in result.items()
                if key not in {"messages", "session", "response"}
            }
            for result in results
        ],
        "token_totals": totals,
    }
    (eval_dir / "evaluation_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def main() -> int:
    args = parse_args()
    if not HERMES.is_file() or not STATE_DB.is_file() or not (HERMES_HOME / ".env").is_file():
        raise SystemExit("Hermes runtime is not initialized; run scripts/start_agent.sh sync first")
    stamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S")
    eval_dir = ROOT / "runs" / f"deepseek_v4_flash_eval_{stamp}"
    eval_dir.mkdir(parents=True)
    offline_output = eval_dir / "offline_demo_artifacts"
    cases = [
        {
            "id": "01_config_read",
            "description": "Read-only runtime configuration inspection",
            "prompt": (
                "只读能力测试：使用终端读取当前项目的 .hermes/config.yaml，不得修改任何文件。"
                "最后只返回一个 JSON 对象，字段必须为 provider、model、context_length，"
                "值必须来自文件，不得猜测。"
            ),
            "scorer": score_config,
        },
        {
            "id": "02_offline_tool",
            "description": "Scientist offline scientific-tool execution",
            "prompt": (
                "工具执行测试：必须调用 masld_offline_demo，fixture 使用 "
                f"{ROOT / 'tests/fixtures/hsd17b13'}，output 使用 {offline_output}。"
                "禁止联网、禁止 GPU、禁止启动任何分子动力学或对接。工具结束后只返回一个 "
                "JSON 对象，包含 status 和 output_dir。"
            ),
            "scorer": score_offline,
        },
        {
            "id": "03_artifact_audit",
            "description": "Read-only audit of prior tool artifacts",
            "prompt": (
                f"只读审计 {offline_output}。使用终端列出实际生成的文件，不得修改或补造文件。"
                "最后只返回 JSON，字段为 file_count 和 files；files 必须使用实际文件名。"
            ),
            "scorer": score_artifact_audit,
        },
        {
            "id": "04_scientific_triage",
            "description": "Binding-stability and HepG2-risk prioritization",
            "prompt": (
                "科学判断测试：为 HSD17B13 的 HepG2 FFA 细胞实验从 A-D 选2个候选。"
                "A: 200ns晚期配体RMSD 1.8A, 接触占比0.95, MMGBSA -42, HepG2风险低；"
                "B: 1.1A, 0.30, -60, 风险高；C: 2.2A, 0.90, -50, 风险低；"
                "D: 6.5A, 0.80, -55, 风险低。优先要求持续口袋接触、可接受稳定性和低HepG2风险；"
                "不能仅按MMGBSA排序。只返回 JSON：selected 为两个字母的数组，reason 为一句话。"
            ),
            "scorer": score_triage,
        },
    ]

    results = []
    for usage_path in args.include_usage:
        results.append(imported_case(usage_path.resolve()))
    env = runtime_env()
    for case in cases:
        print(f"RUN {case['id']}", flush=True)
        result = run_case(case, eval_dir, env, args.timeout)
        results.append(result)
        print(
            f"{case['id']} {'PASS' if result['passed'] else 'FAIL'} "
            f"tokens={result['usage'].get('total_tokens', 0)} "
            f"tools={result['session'].get('tool_call_count', 0)}",
            flush=True,
        )

    write_outputs(eval_dir, results)
    passed_count = sum(bool(result["passed"]) for result in results)
    print(f"REPORT {eval_dir / 'evaluation_report_zh.md'}")
    print(f"RESULT {passed_count}/{len(results)} PASS")
    return 0 if passed_count == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
