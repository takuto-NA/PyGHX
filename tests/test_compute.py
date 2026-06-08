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
    DEFAULT_RHINO_COMPUTE_URL,
    VARIATION_FIXTURE_PATH,
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
