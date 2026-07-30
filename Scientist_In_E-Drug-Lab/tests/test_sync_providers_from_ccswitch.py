from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path

import yaml


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "sync_providers_from_ccswitch.py"
SPEC = importlib.util.spec_from_file_location("sync_providers_from_ccswitch", SCRIPT)
assert SPEC and SPEC.loader
SYNC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SYNC)


def _ccswitch_db(path: Path) -> Path:
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE providers ("
        "id TEXT, name TEXT, app_type TEXT, is_current INTEGER, "
        "settings_config TEXT, website_url TEXT)"
    )
    settings = {
        "env": {
            "ANTHROPIC_API_KEY": "secret",
            "ANTHROPIC_AUTH_TOKEN": "secret",
            "ANTHROPIC_BASE_URL": "https://api.deepseek.com/anthropic",
            "ANTHROPIC_MODEL": "deepseek-v4-pro",
        },
        "model": "sonnet",
    }
    connection.execute(
        "INSERT INTO providers VALUES (?, ?, ?, ?, ?, ?)",
        (
            "deepseek-id",
            "DeepSeek Official",
            "claude",
            0,
            json.dumps(settings),
            "https://platform.deepseek.com",
        ),
    )
    connection.commit()
    connection.close()
    return path


def test_selects_ccswitch_provider_by_name(tmp_path: Path) -> None:
    database = _ccswitch_db(tmp_path / "cc-switch.db")

    provider = SYNC._claude_provider(
        database,
        tmp_path / "missing-settings.json",
        "DeepSeek Official",
    )

    assert provider is not None
    assert provider["id"] == "deepseek-id"
    assert provider["env"]["ANTHROPIC_MODEL"] == "deepseek-v4-pro"


def test_activates_deepseek_with_one_million_context(tmp_path: Path, monkeypatch) -> None:
    database = _ccswitch_db(tmp_path / "cc-switch.db")
    provider = SYNC._claude_provider(
        database,
        tmp_path / "missing-settings.json",
        "DeepSeek Official",
    )
    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    monkeypatch.setattr(SYNC, "TEMPLATE", tmp_path / "template.yaml")
    SYNC.TEMPLATE.write_text("model: {}\nproviders: {}\n", encoding="utf-8")

    config_path = SYNC._ensure_config(
        hermes_home,
        provider,
        activate_selected=True,
        context_length=1_000_000,
    )

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert config["model"] == {
        "provider": "deepseek-official",
        "default": "deepseek-v4-pro",
        "context_length": 1_000_000,
    }
    deepseek = config["providers"]["deepseek-official"]
    assert deepseek["base_url"] == "https://api.deepseek.com/anthropic"
    assert deepseek["api_mode"] == "anthropic_messages"
    assert deepseek["key_env"] == "ANTHROPIC_API_KEY"
    assert deepseek["models"]["deepseek-v4-pro"]["context_length"] == 1_000_000


def test_configures_both_volcengine_protocols(tmp_path: Path, monkeypatch) -> None:
    provider = {
        "id": "volcengine-id",
        "name": "火山Agentplan",
        "env": {
            "ANTHROPIC_AUTH_TOKEN": "secret",
            "ANTHROPIC_BASE_URL": "https://ark.cn-beijing.volces.com/api/coding",
            "ANTHROPIC_MODEL": "ark-code-latest",
        },
    }
    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    monkeypatch.setattr(SYNC, "TEMPLATE", tmp_path / "template.yaml")
    SYNC.TEMPLATE.write_text("model: {}\nproviders: {}\n", encoding="utf-8")

    config_path = SYNC._ensure_config(
        hermes_home,
        provider,
        activate_selected=True,
        context_length=1_000_000,
        model_override="deepseek-v4-pro-260425[1M]",
    )

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert config["model"] == {
        "provider": "volcano-anthropic",
        "default": "deepseek-v4-pro-260425[1M]",
        "context_length": 1_000_000,
    }
    anthropic = config["providers"]["volcano-anthropic"]
    openai = config["providers"]["volcengine-plan"]
    assert anthropic["base_url"] == "https://ark.cn-beijing.volces.com/api/coding"
    assert anthropic["api_mode"] == "anthropic_messages"
    assert openai["base_url"] == "https://ark.cn-beijing.volces.com/api/coding/v3"
    assert openai["api_mode"] == "chat_completions"
    assert openai["models"]["deepseek-v4-pro-260425[1M]"]["context_length"] == 1_000_000


def test_activates_named_provider_with_reasoning(tmp_path: Path, monkeypatch) -> None:
    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    monkeypatch.setattr(SYNC, "TEMPLATE", tmp_path / "template.yaml")
    SYNC.TEMPLATE.write_text(
        "model: {}\nproviders:\n  relay:\n    default_model: old\n"
        "    models: {old: {}}\nagent: {}\n",
        encoding="utf-8",
    )

    config_path = SYNC._ensure_config(
        hermes_home,
        None,
        configured_provider="relay",
        model_override="gpt-5.6-sol",
        context_length=1_050_000,
        reasoning_effort="xhigh",
    )

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert config["model"] == {
        "provider": "relay",
        "default": "gpt-5.6-sol",
        "context_length": 1_050_000,
    }
    assert config["agent"]["reasoning_effort"] == "xhigh"
    assert config["providers"]["relay"]["models"]["gpt-5.6-sol"]["context_length"] == 1_050_000


def test_prunes_providers_absent_from_template(tmp_path: Path, monkeypatch) -> None:
    hermes_home = tmp_path / ".hermes"
    hermes_home.mkdir()
    (hermes_home / "config.yaml").write_text(
        "model: {}\nproviders:\n  openai-relay: {}\n  stale-volcano: {}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(SYNC, "TEMPLATE", tmp_path / "template.yaml")
    SYNC.TEMPLATE.write_text(
        "model: {}\nproviders:\n  openai-relay: {}\n", encoding="utf-8"
    )

    config_path = SYNC._ensure_config(
        hermes_home,
        None,
        prune_unlisted_providers=True,
    )

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert set(config["providers"]) == {"openai-relay"}


def test_strips_provider_environment_without_removing_runtime_flags() -> None:
    cleaned = SYNC._strip_provider_env(
        {
            "OPENAI_API_KEY": "old",
            "ANTHROPIC_AUTH_TOKEN": "old",
            "MASLD_LLM_API_KEY": "old",
            "CLAUDE_CODE_EFFORT_LEVEL": "high",
            "MASLD_COMPETITION_EVAL_MODE": "true",
        }
    )
    assert cleaned == {"MASLD_COMPETITION_EVAL_MODE": "true"}
