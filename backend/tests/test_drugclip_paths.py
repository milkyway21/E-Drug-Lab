"""DrugCLIP path resolution tests."""
from pathlib import Path

from app.api.routes import drugclip as drugclip_routes
from app.services.drugclip_docker import PROJECT_ROOT, DrugClipDockerRunner


def test_project_root_points_to_repo():
    repo_root = Path(__file__).resolve().parents[2]
    assert PROJECT_ROOT == repo_root
    assert (PROJECT_ROOT / "deliverables" / "drugclip-package").exists()


def test_runner_resolves_package_path():
    class _Settings:
        class drugclip:
            package_path = "deliverables/drugclip-package"
            output_dir = "outputs/drugclip"
            image_name = "drugclip-api:latest"
            service_url = "http://localhost:8500"
            wsl_exe = r"C:\Windows\System32\wsl.exe"
            wsl_distro = "eDrugUbuntu"
            timeout = 600

    class _App:
        state = type("State", (), {"settings": _Settings()})()

    request = type("Request", (), {"app": _App()})()
    runner = drugclip_routes._runner(request)
    assert runner.package_path.exists()
    assert runner.package_path.name == "drugclip-package"


def test_write_sample_sdf(tmp_path):
    runner = DrugClipDockerRunner(
        package_path=str(tmp_path),
        image_name="drugclip-api:latest",
        service_url="http://localhost:8500",
        output_dir=str(tmp_path / "out"),
    )
    sdf_path = tmp_path / "work" / "sample.sdf"
    sdf_path.parent.mkdir(parents=True)
    count = runner.write_sample_sdf(sdf_path)
    assert count == 3
    assert sdf_path.exists()
