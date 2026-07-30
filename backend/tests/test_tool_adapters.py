"""Regression: tool_adapters sdf-upload imports must resolve."""
import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch


def test_sdf_upload_adapter_imports():
    repo = Path("/data/ye/e-drug-lab")
    with (
        patch("app.config.get_settings") as mock_settings,
        patch("app.core.paths.get_repo_root", return_value=repo),
        patch("app.db.get_sessionmaker") as mock_sm,
        patch("app.services.sdf_sync.sync_sdf_library") as mock_sync,
    ):
        mock_settings.return_value.sdf_directory = None
        db = MagicMock()
        mock_sm.return_value = MagicMock(return_value=db)
        mock_sync.return_value = MagicMock(total_conformers_added=0, to_dict=lambda: {})

        from app.services.tool_adapters import execute_tool

        result = asyncio.run(execute_tool("sdf-upload", {"molecules": []}))
        assert "sync_result" in result
        db.close.assert_called_once()
