"""Contracts for installable project metadata and dependency ownership."""

import re
import shutil
import subprocess
import sys
import tomllib
import zipfile
from pathlib import Path

import pytest

import smart_retail
from smart_retail.config import load_config

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def project_metadata() -> dict[str, object]:
    return tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def _dependency_names(dependencies: list[str]) -> set[str]:
    return {
        re.split(r"[<>=!~;\[]", value, maxsplit=1)[0].strip().lower()
        for value in dependencies
    }


def test_project_metadata_describes_supported_install(project_metadata) -> None:
    project = project_metadata["project"]

    assert project["name"] == "smart-retail-checkout"
    assert project["version"] == "1.0.0"
    assert project["description"] == (
        "Local YOLOv8 and ByteTrack retail checkout simulation"
    )
    assert project["requires-python"] == ">=3.11"


def test_dependency_groups_match_runtime_boundaries(project_metadata) -> None:
    project = project_metadata["project"]
    optional = project["optional-dependencies"]

    assert _dependency_names(project["dependencies"]) == {
        "fastapi",
        "pydantic",
        "uvicorn",
    }
    assert _dependency_names(optional["vision"]) == {
        "lap",
        "numpy",
        "opencv-python",
        "pyyaml",
        "torch",
        "ultralytics",
    }
    assert _dependency_names(optional["dev"]) == {
        "coverage",
        "httpx2",
        "pytest",
        "pytest-cov",
        "ruff",
    }
    assert "test" not in optional
    assert "ci" not in optional
    assert "httpx" not in {
        name
        for dependencies in optional.values()
        for name in _dependency_names(dependencies)
    }


def test_console_scripts_call_existing_application_entrypoints(
    project_metadata,
) -> None:
    assert project_metadata["project"]["scripts"] == {
        "smart-retail": "smart_retail.app:main",
        "smart-retail-api": "smart_retail.api.service:main",
    }


def test_pyproject_is_the_only_dependency_declaration() -> None:
    assert not (PROJECT_ROOT / "requirements.txt").exists()
    assert not (PROJECT_ROOT / "requirements-api.txt").exists()


def test_default_runtime_configs_are_owned_by_the_installed_package() -> None:
    package_root = Path(smart_retail.__file__).resolve().parent
    config = load_config({})

    assert config.products_config_path.is_relative_to(package_root)
    assert config.tracker.config_path.is_relative_to(package_root)


def test_wheel_contains_default_runtime_configs(tmp_path: Path) -> None:
    isolated_source = tmp_path / "source"
    isolated_source.mkdir()
    shutil.copy2(PROJECT_ROOT / "pyproject.toml", isolated_source)
    shutil.copy2(PROJECT_ROOT / "README.md", isolated_source)
    shutil.copytree(
        PROJECT_ROOT / "src",
        isolated_source / "src",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info"),
    )
    wheel_directory = tmp_path / "wheel"
    wheel_directory.mkdir()
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--quiet",
            "--no-deps",
            "--no-build-isolation",
            "--wheel-dir",
            str(wheel_directory),
            str(isolated_source),
        ],
        check=True,
        cwd=isolated_source,
    )
    wheel_path = next(wheel_directory.glob("smart_retail_checkout-*.whl"))

    with zipfile.ZipFile(wheel_path) as wheel:
        members = set(wheel.namelist())

    assert "smart_retail/configs/products.json" in members
    assert "smart_retail/configs/bytetrack_retail.yaml" in members
    assert not (PROJECT_ROOT / "build").exists()
