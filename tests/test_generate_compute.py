"""Tests for RhinoCompute-oriented GHX generation."""

from __future__ import annotations

import urllib.error
import urllib.request
from importlib import resources
from pathlib import Path

import pytest

from pyghx.compute import (
    ComputeInputValue,
    evaluate_document,
    extract_numeric_result,
)
from pyghx.generate import generate_addition_document, generate_minimal_document
from pyghx.inspect import inspect_document
from pyghx.validate import validate_document
from tests.helpers import ADDITION_FIXTURE_PATH, DEFAULT_RHINO_COMPUTE_URL

EXPECTED_ADDITION_COMPUTE_INPUTS = [
    {"nickname": "X", "kind": "number", "optional": False, "supported": True},
    {"nickname": "Y", "kind": "number", "optional": False, "supported": True},
]
EXPECTED_ADDITION_COMPUTE_OUTPUT = {
    "label": "addition",
    "compute_param_name": "Content",
    "source_component_name": "Addition",
}


def _is_rhino_compute_available() -> bool:
    try:
        health_url = DEFAULT_RHINO_COMPUTE_URL.rstrip("/") + "/healthcheck"
        with urllib.request.urlopen(health_url, timeout=3):
            return True
    except (urllib.error.URLError, TimeoutError):
        return False


def _skip_if_rhino_compute_unavailable(compute_result) -> None:
    if compute_result.success:
        return

    diagnostic_messages = "; ".join(
        diagnostic["message"] for diagnostic in compute_result.diagnostics
    )
    pytest.skip(f"RhinoCompute evaluation is unavailable: {diagnostic_messages}")


def test_generate_minimal_has_no_compute_contract(tmp_path: Path) -> None:
    output_path = generate_minimal_document(tmp_path / "minimal.ghx")
    summary = inspect_document(output_path)

    assert summary["compute_contract"]["inputs"] == []
    assert summary["compute_contract"]["outputs"] == []
    assert any(
        diagnostic["code"] == "no_contextual_inputs"
        for diagnostic in summary["diagnostics"]
    )


def test_addition_compute_template_path_exists() -> None:
    template_path = resources.files("pyghx.templates") / "addition_compute.ghx"
    assert template_path.is_file()


@pytest.mark.integration
def test_template_addition_compute_direct() -> None:
    if not _is_rhino_compute_available():
        pytest.skip("RhinoCompute is not available at http://localhost:5000/")

    template_path = resources.files("pyghx.templates") / "addition_compute.ghx"
    compute_result = evaluate_document(
        template_path,
        input_values=[
            ComputeInputValue(nickname="X", value=2),
            ComputeInputValue(nickname="Y", value=3),
        ],
        compute_url=DEFAULT_RHINO_COMPUTE_URL,
    )
    _skip_if_rhino_compute_unavailable(compute_result)

    assert extract_numeric_result(compute_result.outputs) == 5


def test_generate_addition_document_produces_compute_contract(tmp_path: Path) -> None:
    output_path = generate_addition_document(tmp_path / "generated.ghx")
    summary = inspect_document(output_path)

    assert summary["compute_contract"]["inputs"] == EXPECTED_ADDITION_COMPUTE_INPUTS
    assert summary["compute_contract"]["outputs"][0]["label"] == "addition"
    assert (
        summary["compute_contract"]["outputs"][0]["compute_param_name"] == "Content"
    )

    validation_result = validate_document(output_path)
    assert validation_result.valid is True
    assert "LoggerManager" not in output_path.read_text(encoding="utf-8")


def test_generated_addition_matches_addition_compute_contract(tmp_path: Path) -> None:
    output_path = generate_addition_document(tmp_path / "generated.ghx")
    generated_summary = inspect_document(output_path)
    reference_summary = inspect_document(ADDITION_FIXTURE_PATH)

    assert (
        generated_summary["compute_contract"]
        == reference_summary["compute_contract"]
    )


@pytest.mark.integration
def test_generate_addition_runs_on_rhino_compute(tmp_path: Path) -> None:
    if not _is_rhino_compute_available():
        pytest.skip("RhinoCompute is not available at http://localhost:5000/")

    output_path = generate_addition_document(tmp_path / "generated.ghx")
    compute_result = evaluate_document(
        output_path,
        input_values=[
            ComputeInputValue(nickname="X", value=2),
            ComputeInputValue(nickname="Y", value=3),
        ],
        compute_url=DEFAULT_RHINO_COMPUTE_URL,
    )
    _skip_if_rhino_compute_unavailable(compute_result)

    assert extract_numeric_result(compute_result.outputs) == 5
