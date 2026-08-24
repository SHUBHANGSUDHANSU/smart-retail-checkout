"""Static policy checks for the deterministic GitHub Actions pipeline."""

import re
import tomllib
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = PROJECT_ROOT / ".github/workflows/ci.yml"
TESTING_GUIDE_PATH = PROJECT_ROOT / "docs/TESTING.md"


class ContinuousIntegrationConfigurationTests(unittest.TestCase):
    STABILITY_COMMAND = ".venv/bin/python -m pytest tests -q"
    LOCAL_CI_COMMANDS = (
        '.venv/bin/python -m pip install --editable ".[vision,dev]"',
        ".venv/bin/python -m ruff check app.py src tests training",
        ".venv/bin/python -m ruff format --check app.py src tests training",
        ".venv/bin/python -m coverage erase",
        ".venv/bin/python -m pytest tests/unit tests/contracts -q "
        "--cov=smart_retail --cov-branch --cov-fail-under=0 --cov-report=",
        ".venv/bin/python -m pytest tests/integration -q --cov=smart_retail "
        "--cov-branch --cov-append --cov-fail-under=0 --cov-report=",
        ".venv/bin/python -m coverage xml -o coverage.xml",
        ".venv/bin/python -m coverage report --show-missing --fail-under=85",
    )

    @staticmethod
    def _section(markdown: str, heading: str, next_heading: str) -> str:
        start = markdown.index(heading)
        end = markdown.index(next_heading, start + len(heading))
        return markdown[start:end]

    @staticmethod
    def _subsection(markdown: str, start_marker: str, end_marker: str) -> str:
        start = markdown.index(start_marker)
        end = markdown.index(end_marker, start + len(start_marker))
        return markdown[start:end]

    @staticmethod
    def _bash_commands(markdown: str) -> list[str]:
        commands: list[str] = []
        for block in re.findall(r"```bash\n(.*?)\n```", markdown, flags=re.DOTALL):
            normalized_block = re.sub(r"\\\n[ \t]*", " ", block)
            commands.extend(
                " ".join(line.split())
                for line in normalized_block.splitlines()
                if line.strip()
            )
        return commands

    @classmethod
    def _has_valid_stability_commands(cls, commands: list[str]) -> bool:
        return commands == [cls.STABILITY_COMMAND] * 3 and all(
            "retry" not in command and "rerun" not in command for command in commands
        )

    @classmethod
    def _has_valid_local_ci_commands(cls, commands: list[str]) -> bool:
        return commands == list(cls.LOCAL_CI_COMMANDS)

    def test_ci_tooling_is_pinned_and_configured(self) -> None:
        metadata = tomllib.loads(
            (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )
        dev_dependencies = "\n".join(
            metadata["project"]["optional-dependencies"]["dev"]
        ).lower()

        self.assertIn("pytest==9.1.1", dev_dependencies)
        self.assertIn("pytest-cov==7.1.0", dev_dependencies)
        self.assertIn("coverage[toml]==7.15.4", dev_dependencies)
        self.assertIn("ruff==0.16.4", dev_dependencies)
        self.assertIn("httpx2==2.12.0", dev_dependencies)
        self.assertEqual(metadata["tool"]["ruff"]["target-version"], "py311")
        self.assertEqual(metadata["tool"]["coverage"]["report"]["fail_under"], 85)

    def test_workflow_enforces_quality_tests_and_coverage_without_hardware(
        self,
    ) -> None:
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

        for required in (
            "actions/checkout@v6",
            "actions/setup-python@v6",
            "actions/upload-artifact@v7",
            "python-version: '3.11'",
            "YOLO_CONFIG_DIR: /tmp/ultralytics",
            "python -m ruff check",
            "python -m ruff format --check",
            "--cov-fail-under=0",
            "coverage.xml",
            "headless-install",
            "python -m pip install --editable .",
            'python -m pip install --editable ".[dev]"',
            "tests/integration/test_headless_service.py",
            "smart_retail.api.service",
        ):
            self.assertIn(required, workflow)

        for required in (
            "python -m pytest tests/unit tests/contracts",
            "python -m pytest tests/integration",
            "--cov-append",
            "--fail-under=85",
        ):
            self.assertIn(required, workflow)

        for obsolete in (
            "--ignore=tests/test_api.py",
            "tests/test_api_service.py",
            "tests/test_persistence.py",
        ):
            self.assertNotIn(obsolete, workflow)

        for forbidden in (
            "python app.py",
            "yolov8n.pt",
            "${{ secrets.",
            "docker build",
            "${{ runner.temp }}",
        ):
            self.assertNotIn(forbidden, workflow)

        self.assertEqual(workflow.count("--cov-fail-under=0"), 2)

    def test_unknown_repository_does_not_publish_a_speculative_badge(self) -> None:
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("actions/workflows/ci.yml/badge.svg", readme)

    def test_testing_documentation_explains_ci_scope_and_local_commands(self) -> None:
        guide = TESTING_GUIDE_PATH.read_text(encoding="utf-8")

        for required in (
            "tests/unit",
            "tests/integration",
            "tests/contracts",
            "Pure domain/service behavior and mocked adapter behavior",
            "SQLite, FastAPI, orchestration, lifecycle, and concurrency",
            "Packaging, CI, and container policy artifacts",
            "function-scoped",
            "85%",
            ".venv/bin/python -m pytest tests/unit -q",
            ".venv/bin/python -m pytest tests/integration -q",
            ".venv/bin/python -m pytest tests/contracts -q",
            "Ultralytics",
            "webcam",
            "GUI",
            "MPS/GPU",
            "live Uvicorn",
        ):
            self.assertIn(required, guide)

        exclusions = self._section(
            guide,
            "## Intentional exclusions and manual smoke coverage",
            "## Weak deterministic coverage areas",
        )
        weak_areas = self._section(
            guide,
            "## Weak deterministic coverage areas",
            "## What CI executes",
        )
        for excluded_module in (
            "src/smart_retail/vision/detector.py",
            "src/smart_retail/api/server.py",
        ):
            self.assertIn(excluded_module, exclusions)
            self.assertNotIn(excluded_module, weak_areas)

        self.assertSetEqual(
            set(re.findall(r"`(src/smart_retail/[^`]+\.py)`", weak_areas)),
            {
                "src/smart_retail/api/service.py",
                "src/smart_retail/app.py",
                "src/smart_retail/infrastructure/logging_config.py",
                "src/smart_retail/infrastructure/sqlite_repository.py",
            },
        )

    def test_stability_documentation_has_exactly_three_no_retry_runs(self) -> None:
        guide = TESTING_GUIDE_PATH.read_text(encoding="utf-8")
        stability = self._section(
            guide,
            "## Stability check",
            "## Intentional exclusions and manual smoke coverage",
        )

        self.assertTrue(
            self._has_valid_stability_commands(self._bash_commands(stability))
        )
        self.assertIn("no-retry", stability)

    def test_local_ci_documentation_lists_independent_quality_policy(self) -> None:
        guide = TESTING_GUIDE_PATH.read_text(encoding="utf-8")
        local_ci = self._section(
            guide,
            "## Local CI-equivalent checks",
            "## Stability check",
        )

        self.assertTrue(
            self._has_valid_local_ci_commands(self._bash_commands(local_ci))
        )
        self.assertIn("no-retry", local_ci)

    def test_readme_keeps_the_primary_full_suite_command(self) -> None:
        readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
        running_section = self._section(
            readme,
            "## Running the application",
            "## Continuous integration",
        )
        deterministic_tests = self._subsection(
            running_section,
            "Run the deterministic test suite:",
            "Run the same code-quality checks as CI:",
        )

        self.assertEqual(
            self._bash_commands(deterministic_tests),
            ["python -m pytest tests -q"],
        )

    def test_documented_command_policy_rejects_retry_and_reordered_commands(
        self,
    ) -> None:
        guide = TESTING_GUIDE_PATH.read_text(encoding="utf-8")
        stability = self._section(
            guide,
            "## Stability check",
            "## Intentional exclusions and manual smoke coverage",
        )
        local_ci = self._section(
            guide,
            "## Local CI-equivalent checks",
            "## Stability check",
        )

        retry_commands = self._bash_commands(stability)
        retry_commands[-1] = f"{retry_commands[-1]} --reruns 1"
        self.assertFalse(self._has_valid_stability_commands(retry_commands))

        reordered_commands = self._bash_commands(local_ci)
        reordered_commands[1], reordered_commands[2] = (
            reordered_commands[2],
            reordered_commands[1],
        )
        self.assertFalse(self._has_valid_local_ci_commands(reordered_commands))


if __name__ == "__main__":
    unittest.main()
