"""CLI integration tests."""

from __future__ import annotations

import json
from pathlib import Path

from pyghx.generate import generate_minimal_document
from pyghx.validate import validate_document
from tests.helpers import (
    ADDITION_FIXTURE_PATH,
    MALFORMED_FIXTURE_PATH,
    VARIATION_FIXTURE_PATH,
    parse_cli_json,
    run_pyghx_cli,
)


def test_cli_help() -> None:
    completed_process = run_pyghx_cli(["--help"])
    assert completed_process.returncode == 0
    assert "inspect" in completed_process.stdout


def test_cli_inspect_json_addition() -> None:
    completed_process = run_pyghx_cli(["inspect", str(ADDITION_FIXTURE_PATH), "--json"])
    assert completed_process.returncode == 0
    summary = parse_cli_json(completed_process.stdout)
    assert summary["document_metadata"]["document_name"] == "addition.ghx"
    assert summary["schema_version"] == "2"
    assert summary["compute_contract"]["outputs"][0]["label"] == "addition"
    assert "objects" not in summary


def test_cli_inspect_full_json_addition() -> None:
    completed_process = run_pyghx_cli(["inspect", str(ADDITION_FIXTURE_PATH), "--json", "--full"])
    assert completed_process.returncode == 0
    summary = parse_cli_json(completed_process.stdout)
    assert "objects" in summary


def test_cli_validate_addition() -> None:
    completed_process = run_pyghx_cli(["validate", str(ADDITION_FIXTURE_PATH)])
    assert completed_process.returncode == 0


def test_cli_validate_malformed() -> None:
    completed_process = run_pyghx_cli(["validate", str(MALFORMED_FIXTURE_PATH)])
    assert completed_process.returncode == 1


def test_cli_generate_minimal_round_trip(tmp_path: Path) -> None:
    output_path = tmp_path / "generated.ghx"
    completed_process = run_pyghx_cli(["generate-minimal", "--output", str(output_path)])
    assert completed_process.returncode == 0
    assert output_path.exists()

    validation_result = validate_document(output_path)
    assert validation_result.valid is True

    inspect_process = run_pyghx_cli(["inspect", str(output_path), "--json"])
    assert inspect_process.returncode == 0
    summary = json.loads(inspect_process.stdout)
    assert summary["object_count"] == 0


def test_cli_inspect_variation_json() -> None:
    completed_process = run_pyghx_cli(["inspect", str(VARIATION_FIXTURE_PATH), "--json"])
    assert completed_process.returncode == 0
    summary = parse_cli_json(completed_process.stdout)
    assert len(summary["context_bake_outputs"]) == 6
