"""薛定谔接口客户端"""
from dataclasses import dataclass
from httpx import AsyncClient
import logging

logger = logging.getLogger(__name__)


@dataclass
class SchrodingerConfig:
    api_key: str
    base_url: str = "https://api.schrodinger.com/v1"
    timeout: int = 300


class SchrodingerClient:
    def __init__(self, config: SchrodingerConfig):
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


def get_schrodinger_client(config: SchrodingerConfig) -> SchrodingerClient:
    return SchrodingerClient(config)
