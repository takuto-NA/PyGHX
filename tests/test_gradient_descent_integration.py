"""Integration tests for projected gradient descent against real gradient GHX files."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from pyghx.gradient_transform import transform_penalty_graph_for_gradient
from tests.helpers import (
    DEFAULT_RHINO_COMPUTE_URL,
    is_rhino_compute_available,
    parse_cli_json,
    run_pyghx_cli,
)

DEFAULT_FIXED_Y_VALUE = -0.04


def descent_gradient_ghx_path() -> Path | None:
    """Return an optional gradient GHX path for descent integration tests."""
    raw_path = os.environ.get("PYGHX_DESCENT_GRADIENT_GHX")
    if raw_path:
        path = Path(raw_path)
        if path.is_file():
            return path

    source_raw_path = os.environ.get("PYGHX_GRADIENT_SOURCE_GHX")
    if not source_raw_path:
        return None

    source_path = Path(source_raw_path)
    if not source_path.is_file():
        return None

    generated_path = Path(".pyghx") / "definition_gradient_for_descent.ghx"
    generated_path.parent.mkdir(parents=True, exist_ok=True)
    transform_penalty_graph_for_gradient(source_path, generated_path)
    return generated_path


def descent_source_ghx_path() -> Path | None:
    """Return an optional original scalar penalty GHX path for exact descent tests."""
    raw_path = os.environ.get("PYGHX_GRADIENT_SOURCE_GHX")
    if not raw_path:
        return None
    path = Path(raw_path)
    if not path.is_file():
        return None
    return path


@pytest.mark.skipif(
    descent_gradient_ghx_path() is None,
    reason=(
        "Set PYGHX_DESCENT_GRADIENT_GHX or PYGHX_GRADIENT_SOURCE_GHX to a local gradient GHX."
    ),
)
@pytest.mark.skipif(
    not is_rhino_compute_available(),
    reason="RhinoCompute is not available on localhost:5000.",
)
def test_descend_gradient_cli_keeps_y_fixed_and_never_increases_objective() -> None:
    gradient_ghx_path = descent_gradient_ghx_path()
    assert gradient_ghx_path is not None

    completed_process = run_pyghx_cli(
        [
            "descend-gradient",
            str(gradient_ghx_path),
            "--url",
            DEFAULT_RHINO_COMPUTE_URL,
            "--max-iterations",
            "10",
            "--json",
        ]
    )
    assert completed_process.returncode == 0, completed_process.stderr

    payload = parse_cli_json(completed_process.stdout)
    assert "final_input_values" in payload
    assert "final_penalty" in payload
    assert "final_gradient_values" in payload
    assert "stop_reason" in payload
    assert "accepted_iteration_count" in payload
    assert "rejected_line_search_trial_count" in payload
    assert "run_metrics" in payload
    assert payload["run_metrics"]["evaluation_count"] >= 1
    assert payload["run_metrics"]["rhino_compute_call_count"] >= 1
    assert payload["run_metrics"]["total_wall_clock_milliseconds"] >= 0.0
    assert payload["final_input_values"]["Y"] == DEFAULT_FIXED_Y_VALUE

    previous_objective: float | None = None
    for accepted_iteration in payload["accepted_iterations"]:
        assert accepted_iteration["input_values"]["Y"] == DEFAULT_FIXED_Y_VALUE
        if previous_objective is not None:
            assert accepted_iteration["residual_objective"] <= previous_objective
        previous_objective = accepted_iteration["residual_objective"]


@pytest.mark.skipif(
    descent_gradient_ghx_path() is None,
    reason=(
        "Set PYGHX_DESCENT_GRADIENT_GHX or PYGHX_GRADIENT_SOURCE_GHX to a local gradient GHX."
    ),
)
@pytest.mark.skipif(
    not is_rhino_compute_available(),
    reason="RhinoCompute is not available on localhost:5000.",
)
def test_descend_gradient_cli_returns_structured_json_from_default_start() -> None:
    gradient_ghx_path = descent_gradient_ghx_path()
    assert gradient_ghx_path is not None

    completed_process = run_pyghx_cli(
        [
            "descend-gradient",
            str(gradient_ghx_path),
            "--url",
            DEFAULT_RHINO_COMPUTE_URL,
            "--json",
        ]
    )
    assert completed_process.returncode == 0, completed_process.stderr

    payload = json.loads(completed_process.stdout)
    assert isinstance(payload["final_gradient_values"], list)
    assert len(payload["final_gradient_values"]) == 7
    assert payload["stop_reason"] in {
        "converged",
        "max_iterations_reached",
        "step_size_too_small",
        "zero_projected_gradient",
    }


@pytest.mark.skipif(
    descent_gradient_ghx_path() is None or descent_source_ghx_path() is None,
    reason="Set PYGHX_GRADIENT_SOURCE_GHX to a local scalar penalty GHX.",
)
@pytest.mark.skipif(
    not is_rhino_compute_available(),
    reason="RhinoCompute is not available on localhost:5000.",
)
def test_descend_gradient_with_source_ghx_uses_original_scalar_penalty() -> None:
    gradient_ghx_path = descent_gradient_ghx_path()
    source_ghx_path = descent_source_ghx_path()
    assert gradient_ghx_path is not None
    assert source_ghx_path is not None

    source_process = run_pyghx_cli(
        [
            "compute",
            str(source_ghx_path),
            "--number",
            "X=0",
            "--number",
            "Y=-0.04",
            "--number",
            "Z=0",
            "--number",
            "RX=0",
            "--number",
            "RY=0",
            "--number",
            "RZ=0",
            "--number",
            "RS=0",
            "--url",
            DEFAULT_RHINO_COMPUTE_URL,
            "--json",
        ]
    )
    assert source_process.returncode == 0, source_process.stderr
    source_payload = parse_cli_json(source_process.stdout)

    descent_process = run_pyghx_cli(
        [
            "descend-gradient",
            str(gradient_ghx_path),
            "--source-ghx",
            str(source_ghx_path),
            "--max-iterations",
            "0",
            "--url",
            DEFAULT_RHINO_COMPUTE_URL,
            "--no-record",
            "--json",
        ]
    )
    assert descent_process.returncode == 0, descent_process.stderr
    descent_payload = parse_cli_json(descent_process.stdout)

    assert descent_payload["final_penalty"] == source_payload["outputs"]["penalty"][0]
    assert descent_payload["run_metrics"]["initial_penalty"] == source_payload["outputs"]["penalty"][0]


@pytest.mark.skipif(
    descent_gradient_ghx_path() is None or descent_source_ghx_path() is None,
    reason="Set PYGHX_GRADIENT_SOURCE_GHX to a local scalar penalty GHX.",
)
@pytest.mark.skipif(
    not is_rhino_compute_available(),
    reason="RhinoCompute is not available on localhost:5000.",
)
def test_trace_y_path_cli_smoke_trace_from_zero_to_minus_two(tmp_path: Path) -> None:
    gradient_ghx_path = descent_gradient_ghx_path()
    source_ghx_path = descent_source_ghx_path()
    assert gradient_ghx_path is not None
    assert source_ghx_path is not None
    record_jsonl_path = tmp_path / "y_path_trace_smoke.jsonl"
    record_csv_path = tmp_path / "y_path_trace_smoke.csv"

    completed_process = run_pyghx_cli(
        [
            "trace-y-path",
            str(gradient_ghx_path),
            "--source-ghx",
            str(source_ghx_path),
            "--start-y",
            "0",
            "--end-y",
            "-2",
            "--y-step",
            "-1",
            "--finite-difference-step",
            "0.001",
            "--maximum-movement-norm",
            "0.25",
            "--max-iterations-per-y",
            "40",
            "--record-jsonl",
            str(record_jsonl_path),
            "--record-csv",
            str(record_csv_path),
            "--url",
            DEFAULT_RHINO_COMPUTE_URL,
            "--json",
        ]
    )
    assert completed_process.returncode == 0, completed_process.stderr

    payload = parse_cli_json(completed_process.stdout)
    assert payload["stop_reason"] in {"completed_all_stations", "station_failed"}
    assert payload["completed_station_count"] >= 1
    station_results = payload["station_results"]
    y_values = [station_result["y_value"] for station_result in station_results]
    assert y_values[0] == 0.0
    for station_index, station_result in enumerate(station_results):
        assert station_result["final_input_values"]["Y"] == station_result["y_value"]
        if station_index == 0:
            continue
        assert station_result["normalized_adjacent_jump"] is not None
        assert station_result["normalized_adjacent_jump"] <= 0.25
    assert record_jsonl_path.exists()
    assert record_csv_path.exists()
