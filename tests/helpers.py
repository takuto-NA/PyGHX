"""Shared test helpers and fixture paths."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

FIXTURES_DIRECTORY = Path(__file__).parent / "fixtures"
ADDITION_FIXTURE_PATH = FIXTURES_DIRECTORY / "addition.ghx"
CSHARP_ADDITION_FIXTURE_PATH = FIXTURES_DIRECTORY / "csharp_addition.ghx"
CSHARP_ADDITION_RAW_FIXTURE_PATH = FIXTURES_DIRECTORY / "csharp_addition_raw.ghx"
VARIATION_FIXTURE_PATH = FIXTURES_DIRECTORY / "variation.ghx"
IMPORT_MODEL_FIXTURE_PATH = FIXTURES_DIRECTORY / "import_model.ghx"
IMPORT_TWO_MODELS_FIXTURE_PATH = FIXTURES_DIRECTORY / "import_two_models.ghx"
CSHARP_STEP_IMPORT_FIXTURE_PATH = FIXTURES_DIRECTORY / "csharp_step_import.ghx"
CSHARP_STEP_SCALE_FIXTURE_PATH = FIXTURES_DIRECTORY / "csharp_step_scale.ghx"
BREP_POINTS_FIXTURE_PATH = FIXTURES_DIRECTORY / "brep_points.ghx"
MALFORMED_FIXTURE_PATH = FIXTURES_DIRECTORY / "malformed.ghx"
UNKNOWN_STRUCTURE_FIXTURE_PATH = FIXTURES_DIRECTORY / "unknown_structure.ghx"
DEFAULT_RHINO_COMPUTE_URL = "http://localhost:5000/"


def _resolve_existing_file_path_from_environment(environment_variable_name: str) -> Path | None:
    raw_path = os.environ.get(environment_variable_name)
    if not raw_path:
        return None

    path = Path(raw_path)
    if not path.is_file():
        return None

    return path


def import_model_step_path() -> Path | None:
    """Return an optional STEP/3DM file path for Import 3DM integration tests."""
    return _resolve_existing_file_path_from_environment("PYGHX_IMPORT_STEP_PATH")


def import_two_model_step_paths() -> tuple[Path, Path] | None:
    """Return optional STEP/3DM paths for the two-model Import 3DM integration test."""
    target_step_path = _resolve_existing_file_path_from_environment(
        "PYGHX_IMPORT_TARGET_STEP_PATH"
    )
    obstacle_step_path = _resolve_existing_file_path_from_environment(
        "PYGHX_IMPORT_OBSTACLE_STEP_PATH"
    )
    if target_step_path is None or obstacle_step_path is None:
        return None

    return target_step_path, obstacle_step_path


def brep_points_step_path() -> Path | None:
    """Return an optional STEP/3DM file path for Brep Points integration tests."""
    return _resolve_existing_file_path_from_environment("PYGHX_BREP_STEP_PATH")


def brep_points_sample_point_coordinates() -> tuple[float, float, float] | None:
    """Return optional X,Y,Z coordinates for Brep Points integration tests."""
    raw_coordinates = os.environ.get("PYGHX_BREP_SAMPLE_POINT")
    if not raw_coordinates:
        return None

    coordinate_parts = [part.strip() for part in raw_coordinates.split(",")]
    if len(coordinate_parts) != 3:
        return None

    try:
        return (
            float(coordinate_parts[0]),
            float(coordinate_parts[1]),
            float(coordinate_parts[2]),
        )
    except ValueError:
        return None


def run_pyghx_cli(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, "-m", "pyghx", *arguments]
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def parse_cli_json(stdout: str) -> dict:
    return json.loads(stdout)


def is_rhino_compute_available(
    compute_url: str = DEFAULT_RHINO_COMPUTE_URL,
) -> bool:
    """Return True when RhinoCompute responds to a health check."""
    try:
        health_url = compute_url.rstrip("/") + "/healthcheck"
        with urllib.request.urlopen(health_url, timeout=3):
            return True
    except (urllib.error.URLError, TimeoutError):
        return False
