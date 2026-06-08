"""Shared test helpers and fixture paths."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

FIXTURES_DIRECTORY = Path(__file__).parent / "fixtures"
ADDITION_FIXTURE_PATH = FIXTURES_DIRECTORY / "addition.ghx"
VARIATION_FIXTURE_PATH = FIXTURES_DIRECTORY / "variation.ghx"
MALFORMED_FIXTURE_PATH = FIXTURES_DIRECTORY / "malformed.ghx"
UNKNOWN_STRUCTURE_FIXTURE_PATH = FIXTURES_DIRECTORY / "unknown_structure.ghx"
DEFAULT_RHINO_COMPUTE_URL = "http://localhost:5000/"


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
