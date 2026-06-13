"""Unit tests for projected gradient descent against gradient GHX outputs."""

from __future__ import annotations

import math
from typing import Callable

import pytest

from pathlib import Path

from pyghx.gradient_descent import (
    CONTEXTUAL_INPUT_NICKNAMES,
    GRADIENT_COMPONENT_COUNT,
    DEFAULT_FIXED_VARIABLE_VALUES,
    DEFAULT_INITIAL_INPUT_VALUES,
    GradientDescentConfig,
    GradientDescentError,
    LbfgsConfig,
    PenaltyGradientEvaluator,
    YPathTraceConfig,
    build_station_initial_input_values,
    build_y_station_values,
    cap_free_variable_input_delta,
    measure_normalized_free_variable_jump,
    run_y_path_trace,
    extract_penalty_scalar,
    extract_penalty_and_gradient,
    run_projected_lbfgs,
    run_projected_gradient_descent,
    write_descent_run_record,
)

EvaluatorFunction = Callable[[dict[str, float]], tuple[float, list[float]]]


def _build_quadratic_evaluator(
    target_values: dict[str, float],
) -> EvaluatorFunction:
    """Return penalty = sum((input - target)^2) and its analytic gradient."""

    def evaluate(inputs: dict[str, float]) -> tuple[float, list[float]]:
        penalty = 0.0
        gradient_values: list[float] = []
        for nickname in CONTEXTUAL_INPUT_NICKNAMES:
            delta = inputs[nickname] - target_values[nickname]
            penalty += delta * delta
            gradient_values.append(2.0 * delta)
        return penalty, gradient_values

    return evaluate


def _build_oversized_step_evaluator() -> EvaluatorFunction:
    """Return a surface where the first large step worsens the objective."""

    def evaluate(inputs: dict[str, float]) -> tuple[float, list[float]]:
        x_value = inputs["X"]
        if abs(x_value) > 2.0:
            return 100.0, [20.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        return x_value * x_value, [2.0 * x_value, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

    return evaluate


class CountingFiniteDifferenceLikeEvaluator:
    """Test evaluator where gradient evaluations cost eight calls and penalty-only costs one."""

    compute_call_count_per_evaluation = GRADIENT_COMPONENT_COUNT + 1
    penalty_only_compute_call_count_per_evaluation = 1

    def evaluate(self, inputs: dict[str, float]) -> tuple[float, list[float]]:
        x_value = inputs["X"]
        if abs(x_value) > 2.0:
            return 100.0, [20.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        return x_value * x_value, [2.0 * x_value, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

    def evaluate_penalty(self, inputs: dict[str, float]) -> float:
        x_value = inputs["X"]
        if abs(x_value) > 2.0:
            return 100.0
        return x_value * x_value


def test_cli_help_lists_descend_gradient_command() -> None:
    from tests.helpers import run_pyghx_cli

    completed_process = run_pyghx_cli(["--help"])
    assert completed_process.returncode == 0
    assert "descend-gradient" in completed_process.stdout


def test_extract_penalty_and_gradient_reads_scalar_and_list() -> None:
    penalty_value, gradient_values = extract_penalty_and_gradient(
        {
            "penalty": [3.5],
            "Gradient": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0],
        }
    )
    assert penalty_value == 3.5
    assert gradient_values == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0]


def test_extract_penalty_scalar_reads_single_non_penalty_output() -> None:
    assert extract_penalty_scalar({"number": [2.25]}) == 2.25


def test_extract_penalty_and_gradient_rejects_missing_gradient() -> None:
    with pytest.raises(GradientDescentError, match="seven gradient values"):
        extract_penalty_and_gradient({"penalty": [1.0]})


def test_run_projected_gradient_descent_keeps_fixed_y_value() -> None:
    target_values = {
        "X": 2.0,
        "Y": -0.04,
        "Z": 1.0,
        "RX": 0.0,
        "RY": 0.0,
        "RZ": 0.0,
        "RS": 0.0,
    }
    evaluator = PenaltyGradientEvaluator(_build_quadratic_evaluator(target_values))
    config = GradientDescentConfig(
        initial_input_values=dict(DEFAULT_INITIAL_INPUT_VALUES),
        fixed_variable_values=dict(DEFAULT_FIXED_VARIABLE_VALUES),
        maximum_iteration_count=20,
    )

    result = run_projected_gradient_descent(evaluator, config)

    assert result.final_input_values["Y"] == -0.04
    assert result.final_penalty < 5.0
    for accepted_iteration in result.accepted_iterations:
        assert accepted_iteration.input_values["Y"] == -0.04


def test_run_projected_gradient_descent_converges_on_one_degree_of_freedom() -> None:
    target_x_value = 2.0

    def evaluate_one_dimension(inputs: dict[str, float]) -> tuple[float, list[float]]:
        delta_x = inputs["X"] - target_x_value
        penalty_value = delta_x * delta_x
        gradient_values = [2.0 * delta_x, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        return penalty_value, gradient_values

    evaluator = PenaltyGradientEvaluator(evaluate_one_dimension)
    config = GradientDescentConfig(
        initial_input_values=dict(DEFAULT_INITIAL_INPUT_VALUES),
        fixed_variable_values=dict(DEFAULT_FIXED_VARIABLE_VALUES),
        maximum_step_size=1.0,
        minimum_step_size=1e-12,
        penalty_tolerance=1e-6,
        gradient_tolerance=1e-6,
        maximum_iteration_count=50,
    )

    result = run_projected_gradient_descent(evaluator, config)

    assert result.stop_reason == "converged"
    assert math.isclose(result.final_penalty, 0.0, abs_tol=1e-6)
    assert math.isclose(result.final_input_values["X"], target_x_value, abs_tol=1e-4)
    assert result.final_input_values["Y"] == -0.04


def test_run_projected_lbfgs_converges_on_quadratic_surface() -> None:
    target_values = {
        "X": 2.0,
        "Y": -0.04,
        "Z": 1.0,
        "RX": -0.5,
        "RY": 0.25,
        "RZ": 0.75,
        "RS": -0.25,
    }
    evaluator = PenaltyGradientEvaluator(_build_quadratic_evaluator(target_values))
    config = LbfgsConfig(
        initial_input_values=dict(DEFAULT_INITIAL_INPUT_VALUES),
        fixed_variable_values=dict(DEFAULT_FIXED_VARIABLE_VALUES),
        penalty_tolerance=1e-12,
        gradient_tolerance=1e-8,
        maximum_iteration_count=20,
    )

    result = run_projected_lbfgs(evaluator, config)

    assert result.stop_reason == "converged"
    assert result.final_penalty < 1e-12
    assert result.final_input_values["Y"] == -0.04
    assert result.run_metrics.evaluation_count <= 5


def test_build_y_station_values_includes_start_and_end() -> None:
    station_values = build_y_station_values(start_y=0.0, end_y=-50.0, y_step=-1.0)

    assert station_values[0] == 0.0
    assert station_values[-1] == -50.0
    assert len(station_values) == 51


def test_build_y_station_values_rejects_invalid_step_direction() -> None:
    with pytest.raises(GradientDescentError, match="must be negative"):
        build_y_station_values(start_y=0.0, end_y=-50.0, y_step=1.0)


def test_build_station_initial_input_values_uses_previous_solution() -> None:
    path_config = YPathTraceConfig(maximum_movement_norm=0.25)
    previous_station_final_values = {
        "X": 1.0,
        "Y": -1.0,
        "Z": 2.0,
        "RX": 3.0,
        "RY": 4.0,
        "RZ": 5.0,
        "RS": 6.0,
    }

    initial_input_values = build_station_initial_input_values(
        y_value=-2.0,
        previous_station_final_values=previous_station_final_values,
        second_previous_station_final_values=None,
        path_config=path_config,
    )

    assert initial_input_values["Y"] == -2.0
    assert initial_input_values["X"] == 1.0
    assert initial_input_values["RS"] == 6.0


def test_cap_free_variable_input_delta_limits_normalized_jump() -> None:
    base_input_values = {
        "X": 0.0,
        "Y": -1.0,
        "Z": 0.0,
        "RX": 0.0,
        "RY": 0.0,
        "RZ": 0.0,
        "RS": 0.0,
    }
    target_input_values = {
        "X": 10.0,
        "Y": -2.0,
        "Z": 0.0,
        "RX": 0.0,
        "RY": 0.0,
        "RZ": 0.0,
        "RS": 0.0,
    }

    capped_input_values = cap_free_variable_input_delta(
        base_input_values=base_input_values,
        target_input_values=target_input_values,
        fixed_variable_values={"Y": -2.0},
        movement_scale_values={
            "X": 1.0,
            "Y": 1.0,
            "Z": 1.0,
            "RX": 10.0,
            "RY": 10.0,
            "RZ": 10.0,
            "RS": 1.0,
        },
        maximum_movement_norm=0.25,
    )

    normalized_jump = measure_normalized_free_variable_jump(
        from_input_values=base_input_values,
        to_input_values=capped_input_values,
        fixed_variable_values={"Y": -2.0},
        movement_scale_values={
            "X": 1.0,
            "Y": 1.0,
            "Z": 1.0,
            "RX": 10.0,
            "RY": 10.0,
            "RZ": 10.0,
            "RS": 1.0,
        },
    )
    assert normalized_jump <= 0.25


def test_run_y_path_trace_continues_across_y_stations(tmp_path: Path) -> None:
    target_values = {
        "X": 1.0,
        "Y": 0.0,
        "Z": 0.5,
        "RX": -0.25,
        "RY": 0.25,
        "RZ": 0.75,
        "RS": -0.5,
    }
    evaluator = PenaltyGradientEvaluator(_build_quadratic_evaluator(target_values))
    path_config = YPathTraceConfig(
        start_y=0.0,
        end_y=-2.0,
        y_step=-1.0,
        maximum_iterations_per_y=20,
        maximum_movement_norm=0.25,
        use_secant_prediction=False,
    )
    record_jsonl_path = tmp_path / "y_path_trace.jsonl"
    record_csv_path = tmp_path / "y_path_trace.csv"

    path_result = run_y_path_trace(
        evaluator=evaluator,
        path_config=path_config,
        record_jsonl_path=record_jsonl_path,
        record_csv_path=record_csv_path,
    )

    assert path_result.stop_reason == "completed_all_stations"
    assert len(path_result.station_results) == 3
    assert [station_result.y_value for station_result in path_result.station_results] == [
        0.0,
        -1.0,
        -2.0,
    ]
    assert record_jsonl_path.exists()
    assert record_csv_path.exists()
    for station_index, station_result in enumerate(path_result.station_results):
        assert station_result.final_input_values["Y"] == station_result.y_value
        if station_index == 0:
            continue
        previous_station_result = path_result.station_results[station_index - 1]
        assert station_result.normalized_adjacent_jump is not None
        assert station_result.normalized_adjacent_jump <= 0.25


def test_run_y_path_trace_resume_continues_from_last_station(tmp_path: Path) -> None:
    target_values = {
        "X": 1.0,
        "Y": 0.0,
        "Z": 0.5,
        "RX": -0.25,
        "RY": 0.25,
        "RZ": 0.75,
        "RS": -0.5,
    }
    evaluator = PenaltyGradientEvaluator(_build_quadratic_evaluator(target_values))
    path_config = YPathTraceConfig(
        start_y=0.0,
        end_y=-2.0,
        y_step=-1.0,
        maximum_iterations_per_y=20,
        maximum_movement_norm=0.25,
        use_secant_prediction=False,
    )
    record_jsonl_path = tmp_path / "y_path_trace.jsonl"
    record_csv_path = tmp_path / "y_path_trace.csv"
    run_y_path_trace(
        evaluator=evaluator,
        path_config=path_config,
        record_jsonl_path=record_jsonl_path,
        record_csv_path=record_csv_path,
    )
    completed_jsonl_lines = record_jsonl_path.read_text(encoding="utf-8").splitlines()
    record_jsonl_path.write_text(
        "\n".join(completed_jsonl_lines[:2]) + "\n",
        encoding="utf-8",
    )

    resumed_path_result = run_y_path_trace(
        evaluator=evaluator,
        path_config=path_config,
        record_jsonl_path=record_jsonl_path,
        record_csv_path=record_csv_path,
        resume=True,
    )

    assert resumed_path_result.stop_reason == "completed_all_stations"
    assert len(resumed_path_result.station_results) == 3
    assert resumed_path_result.station_results[-1].y_value == -2.0


def test_run_projected_lbfgs_caps_normalized_movement_norm() -> None:
    target_values = {
        "X": 10.0,
        "Y": -0.04,
        "Z": 0.0,
        "RX": 0.0,
        "RY": 0.0,
        "RZ": 0.0,
        "RS": 0.0,
    }
    evaluator = PenaltyGradientEvaluator(_build_quadratic_evaluator(target_values))
    initial_input_values = dict(DEFAULT_INITIAL_INPUT_VALUES)
    config = LbfgsConfig(
        initial_input_values=initial_input_values,
        fixed_variable_values=dict(DEFAULT_FIXED_VARIABLE_VALUES),
        maximum_iteration_count=1,
        maximum_movement_norm=0.25,
        movement_scale_values={
            "X": 1.0,
            "Y": 1.0,
            "Z": 1.0,
            "RX": 10.0,
            "RY": 10.0,
            "RZ": 10.0,
            "RS": 1.0,
        },
    )

    result = run_projected_lbfgs(evaluator, config)

    movement_norm = abs(result.final_input_values["X"] - initial_input_values["X"])
    assert movement_norm <= 0.25
    assert result.run_metrics.penalty_only_evaluation_count >= 1
    assert result.optimizer_iteration_count == 1


def test_run_projected_gradient_descent_rejects_objective_increasing_steps() -> None:
    evaluator = PenaltyGradientEvaluator(_build_oversized_step_evaluator())
    initial_input_values = dict(DEFAULT_INITIAL_INPUT_VALUES)
    initial_input_values["X"] = 1.5
    config = GradientDescentConfig(
        initial_input_values=initial_input_values,
        fixed_variable_values=dict(DEFAULT_FIXED_VARIABLE_VALUES),
        initial_step_size=10.0,
        maximum_step_size=10.0,
        minimum_step_size=1e-12,
        penalty_tolerance=1e-6,
        gradient_tolerance=1e-6,
        maximum_iteration_count=20,
    )

    result = run_projected_gradient_descent(evaluator, config)

    assert result.rejected_line_search_trial_count > 0
    previous_objective = result.accepted_iterations[0].residual_objective
    for accepted_iteration in result.accepted_iterations[1:]:
        assert accepted_iteration.residual_objective <= previous_objective
        previous_objective = accepted_iteration.residual_objective


def test_run_projected_gradient_descent_grows_successful_step_size() -> None:
    evaluator = PenaltyGradientEvaluator(_build_oversized_step_evaluator())
    initial_input_values = dict(DEFAULT_INITIAL_INPUT_VALUES)
    initial_input_values["X"] = 1.5
    config = GradientDescentConfig(
        initial_input_values=initial_input_values,
        fixed_variable_values=dict(DEFAULT_FIXED_VARIABLE_VALUES),
        initial_step_size=0.03125,
        maximum_step_size=0.125,
        step_growth_factor=2.0,
        penalty_tolerance=1e-12,
        gradient_tolerance=1e-12,
        maximum_iteration_count=3,
    )

    result = run_projected_gradient_descent(evaluator, config)

    accepted_step_sizes = [
        accepted_iteration.accepted_step_size
        for accepted_iteration in result.accepted_iterations
    ]
    assert accepted_step_sizes[:3] == [0.03125, 0.0625, 0.125]


def test_run_projected_gradient_descent_stops_before_tiny_steps() -> None:
    evaluator = PenaltyGradientEvaluator(_build_oversized_step_evaluator())
    initial_input_values = dict(DEFAULT_INITIAL_INPUT_VALUES)
    initial_input_values["X"] = 1.5
    config = GradientDescentConfig(
        initial_input_values=initial_input_values,
        fixed_variable_values=dict(DEFAULT_FIXED_VARIABLE_VALUES),
        initial_step_size=10.0,
        maximum_step_size=10.0,
        minimum_step_size=0.001,
        penalty_tolerance=1e-12,
        gradient_tolerance=1e-12,
        maximum_iteration_count=20,
    )

    result = run_projected_gradient_descent(evaluator, config)

    assert result.accepted_iterations
    assert all(
        accepted_iteration.accepted_step_size >= 0.001
        for accepted_iteration in result.accepted_iterations
    )


def test_run_projected_gradient_descent_uses_penalty_only_line_search_trials() -> None:
    evaluator = CountingFiniteDifferenceLikeEvaluator()
    initial_input_values = dict(DEFAULT_INITIAL_INPUT_VALUES)
    initial_input_values["X"] = 1.5
    config = GradientDescentConfig(
        initial_input_values=initial_input_values,
        fixed_variable_values=dict(DEFAULT_FIXED_VARIABLE_VALUES),
        initial_step_size=10.0,
        maximum_step_size=10.0,
        minimum_step_size=1e-12,
        penalty_tolerance=1e-12,
        gradient_tolerance=1e-12,
        maximum_iteration_count=1,
    )

    result = run_projected_gradient_descent(evaluator, config)

    assert result.rejected_line_search_trial_count > 0
    assert result.run_metrics.evaluation_count == 2
    assert result.run_metrics.penalty_only_evaluation_count > 0
    assert result.run_metrics.rhino_compute_call_count == 16
    assert result.run_metrics.penalty_only_rhino_compute_call_count == (
        result.run_metrics.penalty_only_evaluation_count
    )


def test_run_projected_gradient_descent_records_evaluation_and_timing_metrics() -> None:
    target_x_value = 1.0

    def evaluate_one_dimension(inputs: dict[str, float]) -> tuple[float, list[float]]:
        delta_x = inputs["X"] - target_x_value
        penalty_value = delta_x * delta_x
        gradient_values = [2.0 * delta_x, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        return penalty_value, gradient_values

    evaluator = PenaltyGradientEvaluator(evaluate_one_dimension)
    config = GradientDescentConfig(
        initial_input_values=dict(DEFAULT_INITIAL_INPUT_VALUES),
        fixed_variable_values=dict(DEFAULT_FIXED_VARIABLE_VALUES),
        penalty_tolerance=1e-6,
    )

    result = run_projected_gradient_descent(evaluator, config)

    assert result.run_metrics.evaluation_count >= 2
    assert result.run_metrics.rhino_compute_call_count == 0
    assert result.run_metrics.accepted_iteration_count == len(result.accepted_iterations)
    assert result.run_metrics.initial_penalty > 0.0
    assert result.run_metrics.total_wall_clock_milliseconds >= 0.0
    assert result.run_metrics.total_evaluate_milliseconds >= 0.0
    assert "run_metrics" in result.to_dict()


def test_write_descent_run_record_persists_metrics_and_result(tmp_path: Path) -> None:
    target_x_value = 1.0

    def evaluate_one_dimension(inputs: dict[str, float]) -> tuple[float, list[float]]:
        delta_x = inputs["X"] - target_x_value
        penalty_value = delta_x * delta_x
        gradient_values = [2.0 * delta_x, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        return penalty_value, gradient_values

    evaluator = PenaltyGradientEvaluator(evaluate_one_dimension)
    config = GradientDescentConfig(
        initial_input_values=dict(DEFAULT_INITIAL_INPUT_VALUES),
        fixed_variable_values=dict(DEFAULT_FIXED_VARIABLE_VALUES),
        penalty_tolerance=1e-6,
    )
    result = run_projected_gradient_descent(evaluator, config)
    record_path = tmp_path / "descent_record.json"

    write_descent_run_record(
        record_path=record_path,
        gradient_ghx_path=tmp_path / "definition_gradient.ghx",
        descent_config=config,
        descent_result=result,
        compute_url="http://localhost:5000/",
    )

    import json

    record_payload = json.loads(record_path.read_text(encoding="utf-8"))
    assert record_payload["result"]["run_metrics"]["evaluation_count"] >= 1
    assert record_payload["descent_config"]["fixed_variable_values"]["Y"] == -0.04


def test_run_projected_gradient_descent_records_stop_reason_on_zero_gradient() -> None:
    zero_evaluator = PenaltyGradientEvaluator(
        lambda _inputs: (0.0, [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
    )
    config = GradientDescentConfig(
        initial_input_values=dict(DEFAULT_INITIAL_INPUT_VALUES),
        fixed_variable_values=dict(DEFAULT_FIXED_VARIABLE_VALUES),
        penalty_tolerance=1e-9,
    )

    result = run_projected_gradient_descent(zero_evaluator, config)

    assert result.stop_reason == "converged"
    assert result.final_penalty == 0.0
