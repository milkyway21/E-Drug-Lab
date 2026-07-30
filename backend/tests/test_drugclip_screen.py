"""DrugCLIP screen error handling tests."""
from unittest.mock import MagicMock, patch

from app.services.drugclip_docker import DrugClipDockerRunner


def test_screen_handles_http_error():
    runner = DrugClipDockerRunner(
        package_path="deliverables/drugclip-package",
        image_name="drugclip-api:latest",
        service_url="http://localhost:8500",
        output_dir="outputs/drugclip",
    )
    with patch("app.services.drugclip_docker.urlopen") as mock_urlopen:
        from urllib.error import HTTPError
        from io import BytesIO

        mock_urlopen.side_effect = HTTPError(
            "http://localhost:8500/screen",
            500,
            "Internal Server Error",
            hdrs=None,
            fp=BytesIO(b'{"detail":"GPU OOM"}'),
        )
        result = runner.screen("/app/work/a.sdf", "/app/work/b.pdb", top_k=3)

    assert result["ok"] is False
    assert result["status_code"] == 500
    assert "GPU OOM" in result["detail"]
