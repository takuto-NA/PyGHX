"""RhinoCompute integration and unit tests."""

from __future__ import annotations

import pytest

from pyghx.compute import (
    ComputeInputValue,
    evaluate_document,
    extract_numeric_result,
    _build_request_body,
    _normalize_branch_data,
)
from pyghx.inspect import inspect_document
from tests.helpers import (
    ADDITION_FIXTURE_PATH,
    CSHARP_STEP_IMPORT_FIXTURE_PATH,
    DEFAULT_RHINO_COMPUTE_URL,
    IMPORT_MODEL_FIXTURE_PATH,
    IMPORT_TWO_MODELS_FIXTURE_PATH,
    VARIATION_FIXTURE_PATH,
    import_model_step_path,
    import_two_model_step_paths,
    is_rhino_compute_available,
    parse_cli_json,
    run_pyghx_cli,
)


def test_normalize_branch_data_parses_numeric_strings() -> None:
    assert _normalize_branch_data("5") == 5
    assert _normalize_branch_data("2.5") == 2.5


def test_variation_line_input_is_still_unsupported() -> None:
    compute_result = evaluate_document(
        VARIATION_FIXTURE_PATH,
        input_values=[
            ComputeInputValue(nickname="Get Line", value="unused", kind="line"),
        ],
        compute_url=DEFAULT_RHINO_COMPUTE_URL,
    )
    assert compute_result.success is False
    assert any(
        diagnostic["code"] == "unsupported_input_kind"
        for diagnostic in compute_result.diagnostics
    )


def test_import_model_file_path_input_builds_grasshopper_request_body() -> None:
    request_body = _build_request_body(
        IMPORT_MODEL_FIXTURE_PATH,
        [
            ComputeInputValue(
                nickname="Get File Path",
                value=r"C:\models\example.stp",
                kind="file_path",
            )
        ],
        inspect_document(IMPORT_MODEL_FIXTURE_PATH),
    )
    file_path_value = request_body["values"][0]
    assert file_path_value["ParamName"] == "Get File Path"
    assert file_path_value["InnerTree"]["0"][0]["data"] == '"C:\\\\models\\\\example.stp"'


def test_variation_point_input_builds_grasshopper_request_body() -> None:
    request_body = _build_request_body(
        VARIATION_FIXTURE_PATH,
        [
            ComputeInputValue(
                nickname="Get Point",
                value=(1.0, 2.0, 0.0),
                kind="point",
            )
        ],
        inspect_document(VARIATION_FIXTURE_PATH),
    )
    point_value = request_body["values"][0]
    assert point_value["ParamName"] == "Get Point"
    assert point_value["InnerTree"]["0"][0]["data"] == '{"X": 1.0, "Y": 2.0, "Z": 0.0}'


@pytest.mark.integration
def test_rhino_compute_addition_fixture() -> None:
    if not is_rhino_compute_available():
        pytest.skip("RhinoCompute is not available at http://localhost:5000/")

    compute_result = evaluate_document(
        ADDITION_FIXTURE_PATH,
        input_values=[
            ComputeInputValue(nickname="X", value=2),
            ComputeInputValue(nickname="Y", value=3),
        ],
        compute_url=DEFAULT_RHINO_COMPUTE_URL,
    )
    assert compute_result.success is True, (
        "RhinoCompute failed for addition fixture: "
        + "; ".join(diagnostic["message"] for diagnostic in compute_result.diagnostics)
    )

    numeric_result = extract_numeric_result(compute_result.outputs)
    assert numeric_result == 5


@pytest.mark.integration
def test_rhino_compute_addition_via_cli() -> None:
    if not is_rhino_compute_available():
        pytest.skip("RhinoCompute is not available at http://localhost:5000/")

    completed_process = run_pyghx_cli(
        [
            "compute",
            str(ADDITION_FIXTURE_PATH),
            "--number",
            "X=2",
            "--number",
            "Y=3",
            "--url",
            DEFAULT_RHINO_COMPUTE_URL,
            "--json",
        ]
    )
    if completed_process.returncode != 0:
        payload = parse_cli_json(completed_process.stdout)
        diagnostic_messages = "; ".join(
            diagnostic["message"] for diagnostic in payload.get("diagnostics", [])
        )
        raise AssertionError(
            f"RhinoCompute CLI evaluation failed: {diagnostic_messages}"
        )

    payload = parse_cli_json(completed_process.stdout)
    assert payload["success"] is True
    assert payload["numeric_summary"] == 5


@pytest.mark.integration
def test_rhino_compute_import_model_fixture() -> None:
    step_file_path = import_model_step_path()
    if step_file_path is None:
        pytest.skip("PYGHX_IMPORT_STEP_PATH is not set to an existing STEP/3DM file.")

    if not is_rhino_compute_available():
        pytest.skip("RhinoCompute is not available at http://localhost:5000/")

    compute_result = evaluate_document(
        IMPORT_MODEL_FIXTURE_PATH,
        input_values=[
            ComputeInputValue(
                nickname="Get File Path",
                value=str(step_file_path),
                kind="file_path",
            )
        ],
        compute_url=DEFAULT_RHINO_COMPUTE_URL,
    )
    assert compute_result.success is True, (
        "RhinoCompute failed for import_model fixture: "
        + "; ".join(diagnostic["message"] for diagnostic in compute_result.diagnostics)
    )
    import_geometry_output = compute_result.outputs.get("import_3dm")
    assert import_geometry_output
    assert len(import_geometry_output) >= 1


@pytest.mark.integration
def test_rhino_compute_csharp_step_import_fixture() -> None:
    step_file_path = import_model_step_path()
    if step_file_path is None:
        pytest.skip("PYGHX_IMPORT_STEP_PATH is not set to an existing STEP/3DM file.")

    if not is_rhino_compute_available():
        pytest.skip("RhinoCompute is not available at http://localhost:5000/")

    compute_result = evaluate_document(
        CSHARP_STEP_IMPORT_FIXTURE_PATH,
        input_values=[
            ComputeInputValue(
                nickname="Get File Path",
                value=str(step_file_path),
                kind="file_path",
            )
        ],
        compute_url=DEFAULT_RHINO_COMPUTE_URL,
    )
    assert compute_result.success is True, (
        "RhinoCompute failed for csharp_step_import fixture: "
        + "; ".join(diagnostic["message"] for diagnostic in compute_result.diagnostics)
    )
    geometry_piece_count_output = compute_result.outputs.get("c_script")
    assert geometry_piece_count_output
    assert geometry_piece_count_output[0] >= 1


@pytest.mark.integration
def test_rhino_compute_import_two_models_fixture() -> None:
    step_file_paths = import_two_model_step_paths()
    if step_file_paths is None:
        pytest.skip(
            "PYGHX_IMPORT_TARGET_STEP_PATH and PYGHX_IMPORT_OBSTACLE_STEP_PATH "
            "must point to existing STEP/3DM files."
        )

    if not is_rhino_compute_available():
        pytest.skip("RhinoCompute is not available at http://localhost:5000/")

    target_step_path, obstacle_step_path = step_file_paths
    compute_result = evaluate_document(
        IMPORT_TWO_MODELS_FIXTURE_PATH,
        input_values=[
            ComputeInputValue(
                nickname="Target",
                value=str(target_step_path),
                kind="file_path",
            ),
            ComputeInputValue(
                nickname="Obstacle",
                value=str(obstacle_step_path),
                kind="file_path",
            ),
        ],
        compute_url=DEFAULT_RHINO_COMPUTE_URL,
    )
    assert compute_result.success is True, (
        "RhinoCompute failed for import_two_models fixture: "
        + "; ".join(diagnostic["message"] for diagnostic in compute_result.diagnostics)
    )
    assert len(compute_result.outputs.get("import_target", [])) >= 1
    assert len(compute_result.outputs.get("import_obstacle", [])) >= 1


@pytest.mark.integration
def test_rhino_compute_variation_get_point_pattern(tmp_path: Path) -> None:
    if not is_rhino_compute_available():
        pytest.skip("RhinoCompute is not available at http://localhost:5000/")

    from pyghx.reference import extract_patterns, generate_from_pattern

    catalog_path = extract_patterns(VARIATION_FIXTURE_PATH, output_dir=tmp_path / "patterns")
    output_path = generate_from_pattern(
        "contextual_input_bake_point",
        catalog_directory=catalog_path.parent,
        output_path=tmp_path / "generated_point.ghx",
    )
    compute_result = evaluate_document(
        output_path,
        input_values=[
            ComputeInputValue(
                nickname="Get Point",
                value=(1.0, 2.0, 0.0),
                kind="point",
            )
        ],
        compute_url=DEFAULT_RHINO_COMPUTE_URL,
    )
    assert compute_result.success is True, (
        "RhinoCompute failed for extracted Get Point pattern: "
        + "; ".join(diagnostic["message"] for diagnostic in compute_result.diagnostics)
    )
