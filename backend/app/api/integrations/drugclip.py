"""DrugCLIP integration client — proxies to the Dockerized DrugCLIP API service."""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import URLError


@dataclass
class DrugClipConfig:
    service_url: str = "http://localhost:8500"
    timeout: int = 600


class DrugClipClient:
    """Thin client that proxies requests to the DrugCLIP Docker service."""

    def __init__(self, config: DrugClipConfig):
        self.config = config

    def health(self) -> dict:
        url = f"{self.config.service_url}/health"
        try:
            with urlopen(url, timeout=5) as resp:
                return json.loads(resp.read().decode())
        except URLError as exc:
            return {"status": "unreachable", "error": str(exc)}

    def screen(
        self,
        sdf_path: str,
        pocket_pdb_path: str,
        pocket_center: Optional[list[float]] = None,
        pocket_radius: float = 10.0,
        top_k: int = 1000,
    ) -> dict:
        url = f"{self.config.service_url}/screen"
        payload = {
            "sdf_path": sdf_path,
            "pocket_pdb_path": pocket_pdb_path,
            "top_k": top_k,
        }
        if pocket_center:
            payload["pocket_center"] = pocket_center
            payload["pocket_radius"] = pocket_radius

        req = Request(
            url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=self.config.timeout) as resp:
            return json.loads(resp.read().decode())


def get_drugclip_client(config: DrugClipConfig) -> DrugClipClient:
    return DrugClipClient(config)
