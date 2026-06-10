"""RhinoCompute and end-to-end tests for C# Script GHX files."""

from __future__ import annotations

import shutil

import pytest

from pyghx.compute import ComputeInputValue, evaluate_document, extract_numeric_result
from pyghx.generate import generate_csharp_addition_document
from pyghx.inspect import inspect_document
from pyghx.script_edit import (
    read_script_source_text,
    remove_context_bake_by_instance_guid,
    repair_duplicate_contextual_input_nicknames,
    set_script_source_text,
)
from pyghx.validate import validate_document
from tests.helpers import (
    CSHARP_ADDITION_FIXTURE_PATH,
    CSHARP_ADDITION_RAW_FIXTURE_PATH,
    DEFAULT_RHINO_COMPUTE_URL,
    is_rhino_compute_available,
    parse_cli_json,
    run_pyghx_cli,
)

RAW_CONTEXT_BAKE_OUT_INSTANCE_GUID = "c5bbe4a9-4b2c-4253-9a8c-03da1002ae74"
RAW_GET_NUMBER_X_INSTANCE_GUID = "6ff49b4e-be51-4113-a28d-f99ca930859d"
RAW_GET_NUMBER_Y_INSTANCE_GUID = "19e82177-c780-4c7e-995c-4da6b1579038"


@pytest.mark.integration
def test_raw_csharp_fixture_reports_duplicate_compute_param_names_on_compute() -> None:
    if not is_rhino_compute_available():
        pytest.skip("RhinoCompute is not available at http://localhost:5000/")

    compute_result = evaluate_document(
        CSHARP_ADDITION_RAW_FIXTURE_PATH,
        input_values=[
            ComputeInputValue(nickname="Get Number", value=2),
        ],
        compute_url=DEFAULT_RHINO_COMPUTE_URL,
    )
    assert compute_result.success is True
    raw_response = compute_result.raw_response or {}
    error_messages = " ".join(raw_response.get("errors", []))
    assert "Parameter names must be unique" in error_messages


@pytest.mark.integration
def test_csharp_addition_fixture_executes_on_rhino_compute() -> None:
    if not is_rhino_compute_available():
        pytest.skip("RhinoCompute is not available at http://localhost:5000/")

    compute_result = evaluate_document(
        CSHARP_ADDITION_FIXTURE_PATH,
        input_values=[
            ComputeInputValue(nickname="X", value=2),
            ComputeInputValue(nickname="Y", value=3),
        ],
        compute_url=DEFAULT_RHINO_COMPUTE_URL,
    )
    assert compute_result.success is True, (
        "RhinoCompute failed for csharp_addition fixture: "
        + "; ".join(diagnostic["message"] for diagnostic in compute_result.diagnostics)
    )
    assert extract_numeric_result(compute_result.outputs) == 5.0


@pytest.mark.integration
def test_e2e_generate_csharp_addition_then_compute(tmp_path: Path) -> None:
    if not is_rhino_compute_available():
        pytest.skip("RhinoCompute is not available at http://localhost:5000/")

    generated_path = tmp_path / "generated_csharp_addition.ghx"
    generate_csharp_addition_document(generated_path)

    inspect_summary = inspect_document(generated_path)
    assert len(inspect_summary["script_components"]) == 1
    validation_result = validate_document(generated_path)
    assert validation_result.valid is True

    compute_result = evaluate_document(
        generated_path,
        input_values=[
            ComputeInputValue(nickname="X", value=2),
            ComputeInputValue(nickname="Y", value=3),
        ],
        compute_url=DEFAULT_RHINO_COMPUTE_URL,
    )
    assert compute_result.success is True
    assert extract_numeric_result(compute_result.outputs) == 5.0


@pytest.mark.integration
def test_e2e_edit_script_source_changes_compute_result(tmp_path: Path) -> None:
    if not is_rhino_compute_available():
        pytest.skip("RhinoCompute is not available at http://localhost:5000/")

    edited_path = tmp_path / "edited_csharp_addition.ghx"
    shutil.copy(CSHARP_ADDITION_FIXTURE_PATH, edited_path)
    replacement_source_text = read_script_source_text(edited_path).replace(
        "firstNumber + secondNumber",
        "firstNumber * secondNumber",
    )
    set_script_source_text(edited_path, replacement_source_text)
    assert validate_document(edited_path).valid is True

    compute_result = evaluate_document(
        edited_path,
        input_values=[
            ComputeInputValue(nickname="X", value=2),
            ComputeInputValue(nickname="Y", value=3),
        ],
        compute_url=DEFAULT_RHINO_COMPUTE_URL,
    )
    assert compute_result.success is True
    assert extract_numeric_result(compute_result.outputs) == 6.0


@pytest.mark.integration
def test_e2e_repair_raw_fixture_then_compute(tmp_path: Path) -> None:
    if not is_rhino_compute_available():
        pytest.skip("RhinoCompute is not available at http://localhost:5000/")

    repaired_path = tmp_path / "repaired_csharp_addition.ghx"
    shutil.copy(CSHARP_ADDITION_RAW_FIXTURE_PATH, repaired_path)

    raw_validation = validate_document(repaired_path)
    assert raw_validation.valid is False
    assert any(
        diagnostic["code"] == "duplicate_compute_input_param_name"
        for diagnostic in raw_validation.diagnostics
    )

    repair_duplicate_contextual_input_nicknames(
        repaired_path,
        nickname_assignments=[
            (RAW_GET_NUMBER_X_INSTANCE_GUID, "X"),
            (RAW_GET_NUMBER_Y_INSTANCE_GUID, "Y"),
        ],
    )
    remove_context_bake_by_instance_guid(repaired_path, RAW_CONTEXT_BAKE_OUT_INSTANCE_GUID)
    set_script_source_text(repaired_path, read_script_source_text(CSHARP_ADDITION_FIXTURE_PATH))
    assert validate_document(repaired_path).valid is True

    compute_result = evaluate_document(
        repaired_path,
        input_values=[
            ComputeInputValue(nickname="X", value=2),
            ComputeInputValue(nickname="Y", value=3),
        ],
        compute_url=DEFAULT_RHINO_COMPUTE_URL,
    )
    assert compute_result.success is True
    assert extract_numeric_result(compute_result.outputs) == 5.0


@pytest.mark.integration
def test_e2e_generate_csharp_addition_via_cli(tmp_path: Path) -> None:
    if not is_rhino_compute_available():
        pytest.skip("RhinoCompute is not available at http://localhost:5000/")

    generated_path = tmp_path / "cli_generated_csharp_addition.ghx"
    completed_process = run_pyghx_cli(
        [
            "generate-csharp-addition",
            "--output",
            str(generated_path),
        ]
    )
    assert completed_process.returncode == 0
    assert generated_path.is_file()

    compute_process = run_pyghx_cli(
        [
            "compute",
            str(generated_path),
            "--number",
            "X=2",
            "--number",
            "Y=3",
            "--url",
            DEFAULT_RHINO_COMPUTE_URL,
            "--json",
        ]
    )
    assert compute_process.returncode == 0
    payload = parse_cli_json(compute_process.stdout)
    assert payload["success"] is True
    assert payload["numeric_summary"] == 5.0
