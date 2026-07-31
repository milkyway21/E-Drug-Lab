"""HTTP client with disk cache, timeout, exponential backoff, and rate limiting."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from masld_agent.config import AppSettings


class RateLimiter:
    def __init__(self, min_interval_s: float = 0.34) -> None:
        self.min_interval_s = min_interval_s
        self._last = 0.0

    def wait(self) -> None:
        now = time.monotonic()
        delta = now - self._last
        if delta < self.min_interval_s:
            time.sleep(self.min_interval_s - delta)
        self._last = time.monotonic()


class CachedHttp:
    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        timeout: float = 30.0,
        min_interval_s: float = 0.34,
        cache_only: bool = False,
    ) -> None:
        settings = AppSettings()
        self.cache_dir = Path(cache_dir or settings.masld_http_cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.limiter = RateLimiter(min_interval_s)
        self.cache_only = cache_only

    def _key(
        self,
        method: str,
        url: str,
        params: Optional[dict] = None,
        json_body: Optional[dict] = None,
    ) -> str:
        raw = json.dumps(
            {"m": method, "u": url, "p": params or {}, "j": json_body or {}},
            sort_keys=True,
        )
        return hashlib.sha256(raw.encode()).hexdigest()

    def _paths(self, key: str) -> tuple[Path, Path]:
        return self.cache_dir / f"{key}.json", self.cache_dir / f"{key}.meta.json"

    def get_json(
        self,
        url: str,
        *,
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
        use_cache: bool = True,
        cache_only: bool = False,
    ) -> dict[str, Any]:
        key = self._key("GET", url, params)
        body_path, meta_path = self._paths(key)
        if use_cache and body_path.exists():
            return json.loads(body_path.read_text(encoding="utf-8"))
        if cache_only or self.cache_only:
            raise FileNotFoundError(f"HTTP cache miss for GET {url}")

        payload = self._request_json("GET", url, params=params, headers=headers)
        body_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        meta = {
            "url": url,
            "params": params,
            "sha256": hashlib.sha256(
                json.dumps(payload, sort_keys=True).encode()
            ).hexdigest(),
            "cached_at": time.time(),
        }
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        return payload

    def post_json(
        self,
        url: str,
        *,
        json_body: dict[str, Any],
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
        use_cache: bool = True,
        cache_only: bool = False,
    ) -> dict[str, Any]:
        key = self._key("POST", url, params, json_body)
        body_path, meta_path = self._paths(key)
        if use_cache and body_path.exists():
            return json.loads(body_path.read_text(encoding="utf-8"))
        if cache_only or self.cache_only:
            raise FileNotFoundError(f"HTTP cache miss for POST {url}")

        payload = self._request_json(
            "POST",
            url,
            params=params,
            headers=headers,
            json_body=json_body,
        )
        serialized = json.dumps(payload, ensure_ascii=False, indent=2)
        body_path.write_text(serialized, encoding="utf-8")
        meta_path.write_text(
            json.dumps(
                {
                    "method": "POST",
                    "url": url,
                    "params": params,
                    "request_sha256": hashlib.sha256(
                        json.dumps(json_body, sort_keys=True).encode()
                    ).hexdigest(),
                    "sha256": hashlib.sha256(
                        json.dumps(payload, sort_keys=True).encode()
                    ).hexdigest(),
                    "cached_at": time.time(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return payload

    def get_text(
        self,
        url: str,
        *,
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
        use_cache: bool = True,
        cache_only: bool = False,
    ) -> str:
        key = self._key("GET_TEXT", url, params)
        body_path, meta_path = self._paths(key)
        if use_cache and body_path.exists():
            return body_path.read_text(encoding="utf-8")
        if cache_only or self.cache_only:
            raise FileNotFoundError(f"HTTP cache miss for GET {url}")
        text = self._request_text("GET", url, params=params, headers=headers)
        body_path.write_text(text, encoding="utf-8")
        meta_path.write_text(
            json.dumps(
                {
                    "url": url,
                    "params": params,
                    "sha256": hashlib.sha256(text.encode()).hexdigest(),
                    "cached_at": time.time(),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return text

    @retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=1, max=20))
    def _request_json(
        self,
        method: str,
        url: str,
        *,
        params: Optional[dict] = None,
        headers: Optional[dict] = None,
        json_body: Optional[dict] = None,
    ) -> dict[str, Any]:
        self.limiter.wait()
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            r = client.request(
                method,
                url,
                params=params,
                headers=headers,
                json=json_body,
            )
            r.raise_for_status()
            return r.json()

    @retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=1, min=1, max=20))
    def _request_text(
        self,
        method: str,
        url: str,
        *,
        params: Optional[dict] = None,
        headers: Optional[dict] = None,
    ) -> str:
        self.limiter.wait()
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            r = client.request(method, url, params=params, headers=headers)
            r.raise_for_status()
            return r.text
