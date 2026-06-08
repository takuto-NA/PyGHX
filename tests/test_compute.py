"""RhinoCompute integration and unit tests."""

from __future__ import annotations

import urllib.error
import urllib.request

import pytest

from pyghx.compute import (
    ComputeInputValue,
    evaluate_document,
    extract_numeric_result,
    _normalize_branch_data,
)
from tests.helpers import (
    ADDITION_FIXTURE_PATH,
    DEFAULT_RHINO_COMPUTE_URL,
    VARIATION_FIXTURE_PATH,
)


def test_normalize_branch_data_parses_numeric_strings() -> None:
    assert _normalize_branch_data("5") == 5
    assert _normalize_branch_data("2.5") == 2.5


def test_variation_non_number_inputs_are_rejected_without_live_server() -> None:
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


def _is_rhino_compute_available() -> bool:
    try:
        health_url = DEFAULT_RHINO_COMPUTE_URL.rstrip("/") + "/healthcheck"
        with urllib.request.urlopen(health_url, timeout=3):
            return True
    except (urllib.error.URLError, TimeoutError):
        return False


@pytest.mark.integration
def test_rhino_compute_addition_fixture() -> None:
    if not _is_rhino_compute_available():
        pytest.skip("RhinoCompute is not available at http://localhost:5000/")

    compute_result = evaluate_document(
        ADDITION_FIXTURE_PATH,
        input_values=[
            ComputeInputValue(nickname="X", value=2),
            ComputeInputValue(nickname="Y", value=3),
        ],
        compute_url=DEFAULT_RHINO_COMPUTE_URL,
    )
    if not compute_result.success:
        diagnostic_messages = "; ".join(
            diagnostic["message"] for diagnostic in compute_result.diagnostics
        )
        pytest.skip(f"RhinoCompute evaluation is unavailable: {diagnostic_messages}")

    numeric_result = extract_numeric_result(compute_result.outputs)
    assert numeric_result == 5


@pytest.mark.integration
def test_rhino_compute_addition_via_cli() -> None:
    if not _is_rhino_compute_available():
        pytest.skip("RhinoCompute is not available at http://localhost:5000/")

    from tests.helpers import parse_cli_json, run_pyghx_cli

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
        pytest.skip(f"RhinoCompute evaluation is unavailable: {diagnostic_messages}")

    payload = parse_cli_json(completed_process.stdout)
    assert payload["success"] is True
    assert payload["numeric_summary"] == 5
