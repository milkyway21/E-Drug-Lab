"""DrugClip 接口客户端"""
from dataclasses import dataclass
from httpx import AsyncClient


@dataclass
class DrugClipConfig:
    api_key: str
    base_url: str = "https://api.drugclip.com/v1"


class DrugClipClient:
    def __init__(self, config: DrugClipConfig):
        self.config = config
        self._client = None

    async def get_client(self) -> AsyncClient:
        if self._client is None:
            self._client = AsyncClient(
                base_url=self.config.base_url,
                headers={"Authorization": f"Bearer {self.config.api_key}"},
            )
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()


def get_drugclip_client(config: DrugClipConfig) -> DrugClipClient:
    return DrugClipClient(config)
