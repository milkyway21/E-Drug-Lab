"""Platform adapters: DiffDynamic / e-drug-lab / Schrödinger.

Keep imports lazy so lightweight tools (e.g. Desmond MD HTTP client) work
without pydantic_settings / heavy deps installed in the calling env.
"""
from __future__ import annotations

__all__ = [
    "REQUIRED_IDS",
    "get_entry",
    "list_entries",
    "load_catalog",
    "summarize_systems",
    "platform_health",
]


def __getattr__(name: str):
    if name in {
        "REQUIRED_IDS",
        "get_entry",
        "list_entries",
        "load_catalog",
        "summarize_systems",
    }:
        from masld_agent.platform import catalog as _catalog

        return getattr(_catalog, name)
    if name == "platform_health":
        from masld_agent.platform.health import platform_health

        return platform_health
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
