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
    PenaltyGradientEvaluator,
    extract_penalty_and_gradient,
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
