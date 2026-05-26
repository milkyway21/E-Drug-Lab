"""TAME-VS 接口客户端"""
from dataclasses import dataclass
from httpx import AsyncClient


@dataclass
class TameVSConfig:
    api_key: str
    base_url: str = "https://api.tamevs.org/v1"
    timeout: int = 600


class TameVSClient:
    def __init__(self, config: TameVSConfig):
        self.config = config
        self._client = None

    async def get_client(self) -> AsyncClient:
        if self._client is None:
            self._client = AsyncClient(
                base_url=self.config.base_url,
                timeout=self.config.timeout,
                headers={"Authorization": f"Bearer {self.config.api_key}"},
            )
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()


def get_tame_vs_client(config: TameVSConfig) -> TameVSClient:
    return TameVSClient(config)
