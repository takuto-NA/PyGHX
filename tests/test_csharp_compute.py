"""RhinoCompute and end-to-end tests for C# Script GHX files."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from pyghx.compute import ComputeInputValue, evaluate_document, extract_numeric_result
from pyghx.generate import (
    generate_csharp_addition_document,
    write_default_csharp_script_source,
)
from pyghx.inspect import inspect_document
from pyghx.script_edit import (
    read_script_source_text,
    remove_context_bake_by_instance_guid,
    repair_duplicate_contextual_input_nicknames,
    set_script_source_text,
)
from pyghx.script_graph_edit import add_csharp_number_input, remove_csharp_input, rename_csharp_input
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


@pytest.mark.integration
def test_e2e_add_csharp_number_input_then_compute(tmp_path: Path) -> None:
    if not is_rhino_compute_available():
        pytest.skip("RhinoCompute is not available at http://localhost:5000/")

    edited_path = tmp_path / "three_input_csharp_addition.ghx"
    generate_csharp_addition_document(edited_path)
    add_csharp_number_input(edited_path, contextual_nickname="Z", variable_name="z")

    updated_source_text = read_script_source_text(edited_path).replace(
        "firstNumber + secondNumber",
        "firstNumber + secondNumber + Convert.ToDouble(z)",
    )
    set_script_source_text(edited_path, updated_source_text)
    assert validate_document(edited_path).valid is True

    compute_result = evaluate_document(
        edited_path,
        input_values=[
            ComputeInputValue(nickname="X", value=2),
            ComputeInputValue(nickname="Y", value=3),
            ComputeInputValue(nickname="Z", value=4),
        ],
        compute_url=DEFAULT_RHINO_COMPUTE_URL,
    )
    assert compute_result.success is True
    assert extract_numeric_result(compute_result.outputs) == 9.0


@pytest.mark.integration
def test_e2e_rename_csharp_input_then_compute(tmp_path: Path) -> None:
    if not is_rhino_compute_available():
        pytest.skip("RhinoCompute is not available at http://localhost:5000/")

    edited_path = tmp_path / "renamed_input_csharp_addition.ghx"
    shutil.copy(CSHARP_ADDITION_FIXTURE_PATH, edited_path)
    rename_csharp_input(
        edited_path,
        contextual_nickname="X",
        new_contextual_nickname="Length",
        new_variable_name="length",
    )
    renamed_source_text = read_script_source_text(edited_path).replace(
        "Convert.ToDouble(x)",
        "Convert.ToDouble(length)",
    )
    set_script_source_text(edited_path, renamed_source_text)
    assert validate_document(edited_path).valid is True

    compute_result = evaluate_document(
        edited_path,
        input_values=[
            ComputeInputValue(nickname="Length", value=2),
            ComputeInputValue(nickname="Y", value=3),
        ],
        compute_url=DEFAULT_RHINO_COMPUTE_URL,
    )
    assert compute_result.success is True
    assert extract_numeric_result(compute_result.outputs) == 5.0


@pytest.mark.integration
def test_e2e_remove_csharp_input_then_compute(tmp_path: Path) -> None:
    if not is_rhino_compute_available():
        pytest.skip("RhinoCompute is not available at http://localhost:5000/")

    edited_path = tmp_path / "removed_input_csharp_addition.ghx"
    shutil.copy(CSHARP_ADDITION_FIXTURE_PATH, edited_path)
    add_csharp_number_input(edited_path, contextual_nickname="Z", variable_name="z")
    remove_csharp_input(edited_path, variable_name="z")
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
    assert extract_numeric_result(compute_result.outputs) == 5.0


@pytest.mark.integration
def test_e2e_add_csharp_number_input_via_cli_then_compute(tmp_path: Path) -> None:
    if not is_rhino_compute_available():
        pytest.skip("RhinoCompute is not available at http://localhost:5000/")

    generated_path = tmp_path / "cli_three_input_csharp_addition.ghx"
    generate_process = run_pyghx_cli(
        ["generate-csharp-addition", "--output", str(generated_path)]
    )
    assert generate_process.returncode == 0

    add_process = run_pyghx_cli(
        [
            "add-csharp-number-input",
            str(generated_path),
            "--name",
            "Z",
            "--variable-name",
            "z",
        ]
    )
    assert add_process.returncode == 0

    updated_source_text = read_script_source_text(generated_path).replace(
        "firstNumber + secondNumber",
        "firstNumber + secondNumber + Convert.ToDouble(z)",
    )
    set_script_source_text(generated_path, updated_source_text)

    compute_process = run_pyghx_cli(
        [
            "compute",
            str(generated_path),
            "--number",
            "X=2",
            "--number",
            "Y=3",
            "--number",
            "Z=4",
            "--url",
            DEFAULT_RHINO_COMPUTE_URL,
            "--json",
        ]
    )
    assert compute_process.returncode == 0
    payload = parse_cli_json(compute_process.stdout)
    assert payload["success"] is True
    assert payload["numeric_summary"] == 9.0


@pytest.mark.integration
def test_e2e_default_csharp_script_template_then_compute(tmp_path: Path) -> None:
    if not is_rhino_compute_available():
        pytest.skip("RhinoCompute is not available at http://localhost:5000/")

    script_path = tmp_path / "template_script.cs"
    graph_path = tmp_path / "graph_from_default_template.ghx"

    write_default_csharp_script_source(script_path)
    edited_source_text = script_path.read_text(encoding="utf-8").replace(
        "a = null;",
        "a = Convert.ToDouble(x) + Convert.ToDouble(y);",
    )
    script_path.write_text(edited_source_text, encoding="utf-8")

    generate_csharp_addition_document(graph_path)
    set_script_source_text(graph_path, edited_source_text)
    assert validate_document(graph_path).valid is True

    compute_result = evaluate_document(
        graph_path,
        input_values=[
            ComputeInputValue(nickname="X", value=2),
            ComputeInputValue(nickname="Y", value=3),
        ],
        compute_url=DEFAULT_RHINO_COMPUTE_URL,
    )
    assert compute_result.success is True
    assert extract_numeric_result(compute_result.outputs) == 5.0


@pytest.mark.integration
def test_e2e_default_csharp_script_template_via_cli_then_compute(tmp_path: Path) -> None:
    if not is_rhino_compute_available():
        pytest.skip("RhinoCompute is not available at http://localhost:5000/")

    script_path = tmp_path / "cli_template_script.cs"
    graph_path = tmp_path / "cli_graph_from_default_template.ghx"

    write_process = run_pyghx_cli(
        ["write-csharp-script-template", "--output", str(script_path)]
    )
    assert write_process.returncode == 0

    edited_source_text = script_path.read_text(encoding="utf-8").replace(
        "a = null;",
        "a = Convert.ToDouble(x) + Convert.ToDouble(y);",
    )
    script_path.write_text(edited_source_text, encoding="utf-8")

    generate_process = run_pyghx_cli(
        ["generate-csharp-addition", "--output", str(graph_path)]
    )
    assert generate_process.returncode == 0

    set_script_process = run_pyghx_cli(
        [
            "set-script-source",
            str(graph_path),
            "--source-file",
            str(script_path),
        ]
    )
    assert set_script_process.returncode == 0

    compute_process = run_pyghx_cli(
        [
            "compute",
            str(graph_path),
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
