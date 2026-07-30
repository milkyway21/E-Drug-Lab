from __future__ import annotations

from masld_agent import hermes_plugin


class CollisionContext:
    def __init__(self) -> None:
        self.attempted: list[str] = []

    def register_tool(self, *, name: str, **kwargs) -> None:
        self.attempted.append(name)
        if name == "masld_offline_demo":
            raise ValueError("duplicate tool")

    def register_command(self, *args, **kwargs) -> None:
        return None

    def register_cli_command(self, *args, **kwargs) -> None:
        return None

    def register_skill(self, *args, **kwargs) -> None:
        return None


def test_one_tool_collision_does_not_block_funnel_registration() -> None:
    context = CollisionContext()

    hermes_plugin.register(context)

    assert context.attempted[0] == "masld_offline_demo"
    assert "platform_catalog" in context.attempted
    assert "funnel_autopilot" in context.attempted
