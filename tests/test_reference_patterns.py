"""Integration tests for reference pattern extraction and generation."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pyghx.compute import ComputeInputValue, evaluate_document, extract_numeric_result
from pyghx.generate import generate_addition_document
from pyghx.inspect import inspect_document
from pyghx.reference import extract_patterns, generate_from_pattern, load_pattern_catalog
from pyghx.validate import validate_document
from tests.helpers import (
    ADDITION_FIXTURE_PATH,
    DEFAULT_RHINO_COMPUTE_URL,
    VARIATION_FIXTURE_PATH,
    is_rhino_compute_available,
    parse_cli_json,
    run_pyghx_cli,
)

EXPECTED_ADDITION_COMPUTE_INPUTS = [
    {
        "nickname": "X",
        "compute_param_name": "X",
        "kind": "number",
        "optional": False,
        "supported": True,
    },
    {
        "nickname": "Y",
        "compute_param_name": "Y",
        "kind": "number",
        "optional": False,
        "supported": True,
    },
]


def test_generate_addition_does_not_produce_pattern_catalog(tmp_path: Path) -> None:
    generated_path = generate_addition_document(tmp_path / "addition.ghx")
    catalog_path = tmp_path / "catalog.json"
    assert generated_path.exists()
    assert not catalog_path.exists()


def test_extract_patterns_from_addition_fixture(tmp_path: Path) -> None:
    catalog_path = extract_patterns(ADDITION_FIXTURE_PATH, output_dir=tmp_path)
    catalog = load_pattern_catalog(catalog_path)
    pattern_ids = {pattern.pattern_id for pattern in catalog.patterns}
    assert "addition_binary" in pattern_ids
    assert catalog.source_basename == "addition.ghx"

    addition_pattern = next(
        pattern for pattern in catalog.patterns if pattern.pattern_id == "addition_binary"
    )
    assert addition_pattern.rhino_compute_ready is True
    assert addition_pattern.compute_contract["outputs"]
    assert addition_pattern.compute_contract["outputs"][0]["label"] == "addition"


def test_generate_from_extracted_addition_pattern(tmp_path: Path) -> None:
    catalog_path = extract_patterns(ADDITION_FIXTURE_PATH, output_dir=tmp_path / "patterns")
    output_path = generate_from_pattern(
        "addition_binary",
        catalog_directory=catalog_path.parent,
        output_path=tmp_path / "generated.ghx",
    )
    summary = inspect_document(output_path)
    assert summary["compute_contract"]["inputs"] == EXPECTED_ADDITION_COMPUTE_INPUTS
    assert summary["compute_contract"]["outputs"][0]["label"] == "addition"

    validation_result = validate_document(output_path)
    assert validation_result.valid is True
    assert "LoggerManager" not in output_path.read_text(encoding="utf-8")


def test_extract_patterns_from_variation_fixture_finds_multiple_patterns(tmp_path: Path) -> None:
    catalog_path = extract_patterns(VARIATION_FIXTURE_PATH, output_dir=tmp_path)
    catalog = load_pattern_catalog(catalog_path)
    assert len(catalog.patterns) >= 2
    pattern_ids = [pattern.pattern_id for pattern in catalog.patterns]
    assert len(pattern_ids) == len(set(pattern_ids))


def test_generate_from_variation_pattern(tmp_path: Path) -> None:
    catalog_path = extract_patterns(VARIATION_FIXTURE_PATH, output_dir=tmp_path / "patterns")
    catalog = load_pattern_catalog(catalog_path)
    target_pattern = next(
        pattern
        for pattern in catalog.patterns
        if pattern.pattern_id == "contextual_input_bake_line"
    )
    assert target_pattern.rhino_compute_ready is False

    output_path = generate_from_pattern(
        target_pattern.pattern_id,
        catalog_directory=catalog_path.parent,
        output_path=tmp_path / "generated_variation.ghx",
    )
    validation_result = validate_document(output_path)
    assert validation_result.valid is True
    summary = inspect_document(output_path)
    assert summary["object_count"] == target_pattern.object_count


def test_reference_pattern_agent_loop_on_addition(tmp_path: Path) -> None:
    patterns_directory = tmp_path / "patterns"
    extract_process = run_pyghx_cli(
        [
            "extract-patterns",
            str(ADDITION_FIXTURE_PATH),
            "--output-dir",
            str(patterns_directory),
        ]
    )
    assert extract_process.returncode == 0
    catalog_path = patterns_directory / "catalog.json"
    assert catalog_path.exists()

    list_process = run_pyghx_cli(
        ["list-patterns", "--catalog", str(catalog_path), "--json"]
    )
    assert list_process.returncode == 0
    catalog_payload = parse_cli_json(list_process.stdout)
    assert any(
        pattern["pattern_id"] == "addition_binary"
        for pattern in catalog_payload["patterns"]
    )

    inspect_pattern_process = run_pyghx_cli(
        [
            "inspect-pattern",
            "addition_binary",
            "--catalog",
            str(catalog_path),
            "--json",
        ]
    )
    assert inspect_pattern_process.returncode == 0

    generated_path = tmp_path / "generated_addition.ghx"
    generate_process = run_pyghx_cli(
        [
            "generate-from-pattern",
            "addition_binary",
            "--catalog",
            str(catalog_path),
            "--output",
            str(generated_path),
        ]
    )
    assert generate_process.returncode == 0

    validate_process = run_pyghx_cli(["validate", str(generated_path)])
    assert validate_process.returncode == 0

    inspect_process = run_pyghx_cli(["inspect", str(generated_path), "--json"])
    assert inspect_process.returncode == 0
    summary = parse_cli_json(inspect_process.stdout)
    assert summary["compute_contract"]["inputs"] == EXPECTED_ADDITION_COMPUTE_INPUTS

    if is_rhino_compute_available():
        compute_process = run_pyghx_cli(
            [
                "compute",
                str(generated_path),
                "--number",
                "X=2",
                "--number",
                "Y=3",
                "--json",
            ]
        )
        assert compute_process.returncode == 0
        compute_payload = parse_cli_json(compute_process.stdout)
        assert compute_payload["success"] is True
        assert compute_payload["numeric_summary"] == 5


@pytest.mark.integration
def test_generated_addition_pattern_runs_on_rhino_compute(tmp_path: Path) -> None:
    if not is_rhino_compute_available():
        pytest.skip("RhinoCompute is not available at http://localhost:5000/")

    catalog_path = extract_patterns(ADDITION_FIXTURE_PATH, output_dir=tmp_path / "patterns")
    output_path = generate_from_pattern(
        "addition_binary",
        catalog_directory=catalog_path.parent,
        output_path=tmp_path / "generated.ghx",
    )
    compute_result = evaluate_document(
        output_path,
        input_values=[
            ComputeInputValue(nickname="X", value=2),
            ComputeInputValue(nickname="Y", value=3),
        ],
        compute_url=DEFAULT_RHINO_COMPUTE_URL,
    )
    assert compute_result.success is True, (
        "RhinoCompute failed for extracted addition_binary: "
        + "; ".join(diagnostic["message"] for diagnostic in compute_result.diagnostics)
    )
    assert extract_numeric_result(compute_result.outputs) == 5


@pytest.mark.private_reference
def test_extract_patterns_from_private_reference_when_configured(tmp_path: Path) -> None:
    reference_path = os.environ.get("PYGHX_REFERENCE_GHX")
    if not reference_path:
        pytest.skip("PYGHX_REFERENCE_GHX is not set.")

    source_path = Path(reference_path)
    if not source_path.is_file():
        pytest.skip(f"PYGHX_REFERENCE_GHX does not exist: {source_path}")

    catalog_path = extract_patterns(source_path, output_dir=tmp_path)
    catalog = load_pattern_catalog(catalog_path)
    assert len(catalog.patterns) >= 3
    compute_ready_patterns = [
        pattern for pattern in catalog.patterns if pattern.rhino_compute_ready
    ]
    assert len(compute_ready_patterns) >= 3
    assert all(
        pattern.compute_contract["outputs"]
        for pattern in compute_ready_patterns
    )
