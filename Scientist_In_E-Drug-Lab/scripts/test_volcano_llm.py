#!/usr/bin/env python3
"""Smoke-test Volcano Coding Plan credentials from project .env."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv
import os

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


def main() -> int:
    key = os.environ.get("MASLD_LLM_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
    oa_base = os.environ.get("MASLD_LLM_BASE_URL", "https://ark.cn-beijing.volces.com/api/coding/v3").rstrip("/")
    model = os.environ.get("MASLD_LLM_MODEL", "ark-code-latest")
    if not key:
        print("FAIL: no MASLD_LLM_API_KEY / ANTHROPIC_AUTH_TOKEN in .env", file=sys.stderr)
        return 1

    url = f"{oa_base}/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with exactly: VOLCANO_OK"}],
        "max_tokens": 32,
    }
    print(f"POST {url} model={model}")
    with httpx.Client(timeout=60.0) as client:
        r = client.post(
            url,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload,
        )
    print(f"HTTP {r.status_code}")
    try:
        data = r.json()
    except Exception:
        print(r.text[:500])
        return 1
    print(json.dumps({k: data.get(k) for k in ("id", "model", "object", "usage")}, ensure_ascii=False))
    content = (((data.get("choices") or [{}])[0].get("message") or {}).get("content")) or ""
    print(f"content={content!r}")
    if r.status_code != 200 or "VOLCANO_OK" not in content and "OK" not in content:
        print("FAIL: unexpected response", file=sys.stderr)
        print(json.dumps(data, ensure_ascii=False)[:800], file=sys.stderr)
        return 1
    print("PASS: Volcano Coding Plan OpenAI-compatible chat works")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
