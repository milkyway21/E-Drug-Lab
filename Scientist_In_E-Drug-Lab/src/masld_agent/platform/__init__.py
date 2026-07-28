"""Platform adapters: DiffDynamic / e-drug-lab / Schrödinger."""
from __future__ import annotations

from masld_agent.platform.catalog import (
    REQUIRED_IDS,
    get_entry,
    list_entries,
    load_catalog,
    summarize_systems,
)
from masld_agent.platform.health import platform_health

__all__ = [
    "REQUIRED_IDS",
    "get_entry",
    "list_entries",
    "load_catalog",
    "summarize_systems",
    "platform_health",
]
