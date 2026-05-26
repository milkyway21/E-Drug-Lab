"""DiffDynamic 接口客户端"""
from dataclasses import dataclass
from httpx import AsyncClient


@dataclass
class DiffDynamicConfig:
    api_key: str
    base_url: str = "https://api.diffdynamic.org/v1"
    timeout: int = 900


@dataclass
class GenerationConstraints:
    max_molecular_weight: float = 500.0
    min_logp: float = -2.0
    max_logp: float = 5.0
    max_h_bond_donors: int = 5
    max_h_bond_acceptors: int = 10
    max_rotatable_bonds: int = 10
    qed_threshold: float = 0.4
    diversity_factor: float = 0.8


@dataclass
class TargetProperties:
    target_property: str
    target_value: float
    weight: float = 1.0
    tolerance: float = 0.1


class DiffDynamicClient:
    def __init__(self, config: DiffDynamicConfig):
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


def get_diffdynamic_client(config: DiffDynamicConfig) -> DiffDynamicClient:
    return DiffDynamicClient(config)
