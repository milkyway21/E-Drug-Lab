from __future__ import annotations

from pathlib import Path

from masld_agent import hermes_plugin


class CollisionContext:
    def __init__(self) -> None:
        self.attempted: list[str] = []
        self.skills: list[str] = []

    def register_tool(self, *, name: str, **kwargs) -> None:
        self.attempted.append(name)
        if name == "masld_offline_demo":
            raise ValueError("duplicate tool")

    def register_command(self, *args, **kwargs) -> None:
        return None

    def register_cli_command(self, *args, **kwargs) -> None:
        return None

    def register_skill(self, path: str, *args, **kwargs) -> None:
        self.skills.append(path)


def test_one_tool_collision_does_not_block_funnel_registration() -> None:
    context = CollisionContext()

    hermes_plugin.register(context)

    assert context.attempted[0] == "masld_offline_demo"
    assert "platform_catalog" in context.attempted
    assert "funnel_autopilot" in context.attempted
    assert "target_biology_search" in context.attempted
    assert "structure_prepare_native" in context.attempted
    assert "nominate_compounds" in context.attempted
    assert len(context.skills) >= 46
    assert any(Path(path).name == "drug-discovery-orchestrator" for path in context.skills)
    assert any(Path(path).name == "target-discovery" for path in context.skills)
    assert any(Path(path).name == "funnel-glide-sp" for path in context.skills)
    assert all(Path(path).parent.name == "skills" or Path(path).parent.parent.name == "skills" for path in context.skills)
