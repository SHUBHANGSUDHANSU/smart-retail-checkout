"""Static contracts for the production container artifacts."""

import tomllib
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ContainerArtifactTests(unittest.TestCase):
    def test_production_image_is_headless_non_root_and_health_checked(self) -> None:
        dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")

        self.assertIn("FROM python:3.11-slim AS api-base", dockerfile)
        self.assertIn("FROM api-base AS test", dockerfile)
        self.assertIn("FROM api-base AS production", dockerfile)
        self.assertIn("USER smartretail", dockerfile)
        self.assertIn("EXPOSE 8000", dockerfile)
        self.assertIn("HEALTHCHECK", dockerfile)
        self.assertIn(
            'CMD ["python", "-m", "smart_retail.api.service"]',
            dockerfile,
        )
        self.assertNotIn("requirements.txt\n", dockerfile)

    def test_docker_installs_headless_and_test_extras_from_pyproject(self) -> None:
        dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")

        self.assertIn("RUN pip install --no-cache-dir .", dockerfile)
        self.assertIn('RUN pip install --no-cache-dir ".[dev]"', dockerfile)
        self.assertIn(
            "COPY tests/integration/test_headless_service.py "
            "./tests/integration/test_headless_service.py",
            dockerfile,
        )
        self.assertIn(
            'CMD ["python", "-m", "pytest", '
            '"tests/integration/test_headless_service.py", "-q", '
            '"-p", "no:cacheprovider"]',
            dockerfile,
        )
        self.assertNotIn("requirements-api.txt", dockerfile)
        self.assertNotIn("httpx==", dockerfile)

    def test_package_metadata_separates_api_vision_and_test_dependencies(self) -> None:
        metadata = tomllib.loads(
            (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )
        base = "\n".join(metadata["project"]["dependencies"]).lower()
        optional = metadata["project"]["optional-dependencies"]

        for dependency in ("opencv", "ultralytics", "lap", "httpx"):
            self.assertNotIn(dependency, base)
        self.assertIn("opencv", "\n".join(optional["vision"]).lower())
        self.assertIn("ultralytics", "\n".join(optional["vision"]).lower())
        self.assertIn("httpx2==2.12.0", "\n".join(optional["dev"]).lower())
        self.assertFalse((PROJECT_ROOT / "requirements.txt").exists())
        self.assertFalse((PROJECT_ROOT / "requirements-api.txt").exists())

    def test_docker_context_excludes_local_and_large_runtime_artifacts(self) -> None:
        dockerignore = (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8")

        for pattern in (
            ".git",
            ".venv",
            ".env",
            "*.db",
            "*.pt",
            "__pycache__",
            ".DS_Store",
        ):
            self.assertIn(pattern, dockerignore)


if __name__ == "__main__":
    unittest.main()
