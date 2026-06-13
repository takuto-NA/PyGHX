"""Projected gradient descent for gradient-enabled penalty GHX definitions."""

from __future__ import annotations

import csv
import json
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

from pyghx.compute import ComputeInputValue, evaluate_document

CONTEXTUAL_INPUT_NICKNAMES: tuple[str, ...] = ("X", "Y", "Z", "RX", "RY", "RZ", "RS")
DEFAULT_FIXED_Y_VALUE = -0.04
DEFAULT_INITIAL_INPUT_VALUES: dict[str, float] = {
    "X": 0.0,
    "Y": DEFAULT_FIXED_Y_VALUE,
    "Z": 0.0,
    "RX": 0.0,
    "RY": 0.0,
    "RZ": 0.0,
    "RS": 0.0,
}
DEFAULT_FIXED_VARIABLE_VALUES: dict[str, float] = {
    "Y": DEFAULT_FIXED_Y_VALUE,
}
DEFAULT_PENALTY_TOLERANCE = 0.001
DEFAULT_GRADIENT_TOLERANCE = 0.001
DEFAULT_MAXIMUM_ITERATION_COUNT = 100
DEFAULT_INITIAL_STEP_SIZE = 0.25
DEFAULT_MAXIMUM_STEP_SIZE = 0.25
DEFAULT_STEP_GROWTH_FACTOR = 2.0
DEFAULT_BACKTRACKING_REDUCTION_FACTOR = 0.5
DEFAULT_ARMIJO_FACTOR = 1e-4
DEFAULT_MINIMUM_STEP_SIZE = 0.001
DEFAULT_MAXIMUM_LINE_SEARCH_ATTEMPTS = 50
DEFAULT_FINITE_DIFFERENCE_STEP = 0.01
GRADIENT_COMPONENT_COUNT = 7
ZERO_NORM_TOLERANCE = 1e-18
DEFAULT_DESCENT_RECORD_PATH = Path(".pyghx") / "descent_latest.json"
DEFAULT_LBFGS_HISTORY_SIZE = 10
DEFAULT_LBFGS_MAXIMUM_LINE_SEARCH_STEPS = 20
DEFAULT_LBFGS_RECORD_PATH = Path(".pyghx") / "lbfgs_latest.json"
DEFAULT_MOVEMENT_SCALE_VALUES: dict[str, float] = {
    "X": 1.0,
    "Y": 1.0,
    "Z": 1.0,
    "RX": 10.0,
    "RY": 10.0,
    "RZ": 10.0,
    "RS": 1.0,
}
DEFAULT_Y_PATH_START_Y = 0.0
DEFAULT_Y_PATH_END_Y = -50.0
DEFAULT_Y_PATH_STEP = -1.0
DEFAULT_Y_PATH_FINITE_DIFFERENCE_STEP = 0.001
DEFAULT_Y_PATH_MAXIMUM_MOVEMENT_NORM = 0.25
DEFAULT_Y_PATH_MAX_ITERATIONS_PER_Y = 80
DEFAULT_Y_PATH_TRACE_JSONL_PATH = Path(".pyghx") / "y_path_trace.jsonl"
DEFAULT_Y_PATH_TRACE_CSV_PATH = Path(".pyghx") / "y_path_trace.csv"
Y_PATH_RECORD_KIND_HEADER = "header"
Y_PATH_RECORD_KIND_STATION = "station"
Y_PATH_FIXED_VARIABLE_NICKNAME = "Y"


class GradientDescentError(Exception):
    """Raised when gradient descent input or output contracts are invalid."""


@dataclass(frozen=True)
class GradientDescentConfig:
    """Configuration for one projected gradient descent run."""

    initial_input_values: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_INITIAL_INPUT_VALUES)
    )
    fixed_variable_values: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_FIXED_VARIABLE_VALUES)
    )
    penalty_tolerance: float = DEFAULT_PENALTY_TOLERANCE
    gradient_tolerance: float = DEFAULT_GRADIENT_TOLERANCE
    maximum_iteration_count: int = DEFAULT_MAXIMUM_ITERATION_COUNT
    initial_step_size: float = DEFAULT_INITIAL_STEP_SIZE
    maximum_step_size: float = DEFAULT_MAXIMUM_STEP_SIZE
    step_growth_factor: float = DEFAULT_STEP_GROWTH_FACTOR
    backtracking_reduction_factor: float = DEFAULT_BACKTRACKING_REDUCTION_FACTOR
    armijo_factor: float = DEFAULT_ARMIJO_FACTOR
    minimum_step_size: float = DEFAULT_MINIMUM_STEP_SIZE
    maximum_line_search_attempts: int = DEFAULT_MAXIMUM_LINE_SEARCH_ATTEMPTS


@dataclass(frozen=True)
class GradientDescentRunMetrics:
    """Timing and evaluation counters for one gradient descent run."""

    evaluation_count: int
    rhino_compute_call_count: int
    penalty_only_evaluation_count: int
    penalty_only_rhino_compute_call_count: int
    accepted_iteration_count: int
    rejected_line_search_trial_count: int
    total_wall_clock_milliseconds: float
    total_evaluate_milliseconds: float
    initial_penalty: float
    initial_input_values: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "evaluation_count": self.evaluation_count,
            "rhino_compute_call_count": self.rhino_compute_call_count,
            "penalty_only_evaluation_count": self.penalty_only_evaluation_count,
            "penalty_only_rhino_compute_call_count": self.penalty_only_rhino_compute_call_count,
            "accepted_iteration_count": self.accepted_iteration_count,
            "rejected_line_search_trial_count": self.rejected_line_search_trial_count,
            "total_wall_clock_milliseconds": self.total_wall_clock_milliseconds,
            "total_evaluate_milliseconds": self.total_evaluate_milliseconds,
            "initial_penalty": self.initial_penalty,
            "initial_input_values": dict(self.initial_input_values),
        }


@dataclass(frozen=True)
class AcceptedGradientDescentIteration:
    """One accepted projected gradient descent iteration."""

    iteration_index: int
    input_values: dict[str, float]
    penalty: float
    gradient_values: list[float]
    residual_objective: float
    projected_gradient_norm: float
    accepted_step_size: float
    rejected_line_search_trial_count: int


@dataclass(frozen=True)
class GradientDescentResult:
    """Final result from one projected gradient descent run."""

    final_input_values: dict[str, float]
    final_penalty: float
    final_gradient_values: list[float]
    final_projected_gradient_norm: float
    stop_reason: str
    accepted_iterations: tuple[AcceptedGradientDescentIteration, ...]
    rejected_line_search_trial_count: int
    run_metrics: GradientDescentRunMetrics

    def to_dict(self) -> dict[str, Any]:
        return {
            "final_input_values": dict(self.final_input_values),
            "final_penalty": self.final_penalty,
            "final_gradient_values": list(self.final_gradient_values),
            "final_projected_gradient_norm": self.final_projected_gradient_norm,
            "stop_reason": self.stop_reason,
            "accepted_iteration_count": len(self.accepted_iterations),
            "rejected_line_search_trial_count": self.rejected_line_search_trial_count,
            "run_metrics": self.run_metrics.to_dict(),
            "accepted_iterations": [
                {
                    "iteration_index": accepted_iteration.iteration_index,
                    "input_values": dict(accepted_iteration.input_values),
                    "penalty": accepted_iteration.penalty,
                    "gradient_values": list(accepted_iteration.gradient_values),
                    "residual_objective": accepted_iteration.residual_objective,
                    "objective_value": accepted_iteration.residual_objective,
                    "projected_gradient_norm": accepted_iteration.projected_gradient_norm,
                    "accepted_step_size": accepted_iteration.accepted_step_size,
                    "rejected_line_search_trial_count": (
                        accepted_iteration.rejected_line_search_trial_count
                    ),
                }
                for accepted_iteration in self.accepted_iterations
            ],
        }


@dataclass(frozen=True)
class LbfgsConfig:
    """Configuration for one projected L-BFGS-B run."""

    initial_input_values: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_INITIAL_INPUT_VALUES)
    )
    fixed_variable_values: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_FIXED_VARIABLE_VALUES)
    )
    penalty_tolerance: float = DEFAULT_PENALTY_TOLERANCE
    gradient_tolerance: float = DEFAULT_GRADIENT_TOLERANCE
    maximum_iteration_count: int = DEFAULT_MAXIMUM_ITERATION_COUNT
    history_size: int = DEFAULT_LBFGS_HISTORY_SIZE
    maximum_line_search_steps: int = DEFAULT_LBFGS_MAXIMUM_LINE_SEARCH_STEPS
    maximum_movement_norm: float | None = None
    movement_scale_values: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_MOVEMENT_SCALE_VALUES)
    )


@dataclass(frozen=True)
class LbfgsResult:
    """Final result from one projected L-BFGS-B run."""

    final_input_values: dict[str, float]
    final_penalty: float
    final_gradient_values: list[float]
    final_projected_gradient_norm: float
    stop_reason: str
    optimizer_message: str
    optimizer_iteration_count: int
    optimizer_function_evaluation_count: int
    run_metrics: GradientDescentRunMetrics

    def to_dict(self) -> dict[str, Any]:
        return {
            "final_input_values": dict(self.final_input_values),
            "final_penalty": self.final_penalty,
            "final_gradient_values": list(self.final_gradient_values),
            "final_projected_gradient_norm": self.final_projected_gradient_norm,
            "stop_reason": self.stop_reason,
            "optimizer_message": self.optimizer_message,
            "optimizer_iteration_count": self.optimizer_iteration_count,
            "optimizer_function_evaluation_count": self.optimizer_function_evaluation_count,
            "run_metrics": self.run_metrics.to_dict(),
        }


@dataclass(frozen=True)
class CappedLbfgsLineSearchResult:
    """Accepted capped L-BFGS trial point and rejected trial count."""

    rejected_trial_count: int
    next_input_values: dict[str, float] | None


class PenaltyGradientEvaluatorProtocol(Protocol):
    """Callable contract for one penalty and gradient evaluation."""

    def evaluate(
        self,
        input_values: dict[str, float],
    ) -> tuple[float, list[float]]:
        """Return scalar penalty and seven gradient components."""


class PenaltyOnlyEvaluatorProtocol(PenaltyGradientEvaluatorProtocol, Protocol):
    """Callable contract for evaluators that can evaluate penalty alone."""

    def evaluate_penalty(
        self,
        input_values: dict[str, float],
    ) -> float:
        """Return scalar penalty without computing a gradient."""


@dataclass
class CountingPenaltyGradientEvaluator:
    """Wrap one evaluator and count penalty-gradient evaluations with timing."""

    inner_evaluator: PenaltyGradientEvaluatorProtocol
    evaluation_count: int = 0
    rhino_compute_call_count: int = 0
    evaluate_milliseconds_total: float = 0.0
    penalty_only_evaluation_count: int = 0
    penalty_only_rhino_compute_call_count: int = 0
    penalty_only_evaluate_milliseconds_total: float = 0.0

    def evaluate(
        self,
        input_values: dict[str, float],
    ) -> tuple[float, list[float]]:
        evaluate_started_at = time.perf_counter()
        penalty_value, gradient_values = self.inner_evaluator.evaluate(input_values)
        self.evaluation_count += 1
        self.rhino_compute_call_count += _read_compute_call_count_per_evaluation(
            self.inner_evaluator
        )
        self.evaluate_milliseconds_total += _elapsed_milliseconds_since(evaluate_started_at)
        return penalty_value, gradient_values

    def evaluate_penalty(
        self,
        input_values: dict[str, float],
    ) -> float:
        if not _supports_penalty_only_evaluation(self.inner_evaluator):
            penalty_value, _gradient_values = self.evaluate(input_values)
            return penalty_value
        evaluate_started_at = time.perf_counter()
        penalty_value = self.inner_evaluator.evaluate_penalty(input_values)
        self.penalty_only_evaluation_count += 1
        self.penalty_only_rhino_compute_call_count += _read_penalty_only_compute_call_count(
            self.inner_evaluator
        )
        self.penalty_only_evaluate_milliseconds_total += _elapsed_milliseconds_since(
            evaluate_started_at
        )
        return penalty_value


@dataclass(frozen=True)
class PenaltyGradientEvaluator:
    """Adapter around a plain callable penalty and gradient evaluator."""

    evaluate_function: Callable[[dict[str, float]], tuple[float, list[float]]]
    compute_call_count_per_evaluation: int = 0
    penalty_only_compute_call_count_per_evaluation: int = 0

    def evaluate(
        self,
        input_values: dict[str, float],
    ) -> tuple[float, list[float]]:
        penalty_value, gradient_values = self.evaluate_function(input_values)
        _validate_finite_penalty_and_gradient(penalty_value, gradient_values)
        return penalty_value, gradient_values

    def evaluate_penalty(
        self,
        input_values: dict[str, float],
    ) -> float:
        penalty_value, _gradient_values = self.evaluate(input_values)
        return penalty_value


@dataclass(frozen=True)
class RhinoComputePenaltyGradientEvaluator:
    """Evaluate penalty and Gradient through one RhinoCompute call."""

    gradient_ghx_path: Path
    compute_url: str
    compute_call_count_per_evaluation: int = 1
    penalty_only_compute_call_count_per_evaluation: int = 1

    def evaluate(
        self,
        input_values: dict[str, float],
    ) -> tuple[float, list[float]]:
        compute_input_values = [
            ComputeInputValue(nickname=nickname, value=input_values[nickname])
            for nickname in CONTEXTUAL_INPUT_NICKNAMES
        ]
        compute_result = evaluate_document(
            self.gradient_ghx_path,
            input_values=compute_input_values,
            compute_url=self.compute_url,
        )
        if not compute_result.success:
            diagnostic_messages = ", ".join(
                diagnostic["message"] for diagnostic in compute_result.diagnostics
            )
            raise GradientDescentError(
                "RhinoCompute evaluation failed during gradient descent: "
                f"{diagnostic_messages or 'unknown error'}."
            )
        return extract_penalty_and_gradient(compute_result.outputs)

    def evaluate_penalty(
        self,
        input_values: dict[str, float],
    ) -> float:
        penalty_value, _gradient_values = self.evaluate(input_values)
        return penalty_value


@dataclass(frozen=True)
class OriginalFiniteDifferenceEvaluator:
    """Evaluate the original scalar GHX and build a matching forward-difference gradient."""

    source_ghx_path: Path
    compute_url: str
    finite_difference_step: float = DEFAULT_FINITE_DIFFERENCE_STEP
    compute_call_count_per_evaluation: int = GRADIENT_COMPONENT_COUNT + 1
    penalty_only_compute_call_count_per_evaluation: int = 1

    def evaluate(
        self,
        input_values: dict[str, float],
    ) -> tuple[float, list[float]]:
        base_penalty = self._evaluate_original_penalty(input_values)
        gradient_values: list[float] = []
        for nickname in CONTEXTUAL_INPUT_NICKNAMES:
            perturbed_input_values = dict(input_values)
            perturbed_input_values[nickname] = (
                perturbed_input_values[nickname] + self.finite_difference_step
            )
            perturbed_penalty = self._evaluate_original_penalty(perturbed_input_values)
            gradient_values.append(
                (perturbed_penalty - base_penalty) / self.finite_difference_step
            )
        return base_penalty, gradient_values

    def evaluate_penalty(
        self,
        input_values: dict[str, float],
    ) -> float:
        return self._evaluate_original_penalty(input_values)

    def _evaluate_original_penalty(
        self,
        input_values: dict[str, float],
    ) -> float:
        compute_input_values = [
            ComputeInputValue(nickname=nickname, value=input_values[nickname])
            for nickname in CONTEXTUAL_INPUT_NICKNAMES
        ]
        compute_result = evaluate_document(
            self.source_ghx_path,
            input_values=compute_input_values,
            compute_url=self.compute_url,
        )
        if not compute_result.success:
            diagnostic_messages = ", ".join(
                diagnostic["message"] for diagnostic in compute_result.diagnostics
            )
            raise GradientDescentError(
                "Original GHX evaluation failed during finite-difference descent: "
                f"{diagnostic_messages or 'unknown error'}."
            )
        return extract_penalty_scalar(compute_result.outputs)


def extract_penalty_scalar(outputs: dict[str, Any]) -> float:
    """Read one scalar penalty value from RhinoCompute outputs."""
    penalty_output_values = outputs.get("penalty")
    if penalty_output_values is None and len(outputs) == 1:
        penalty_output_values = next(iter(outputs.values()))
    if not isinstance(penalty_output_values, list) or not penalty_output_values:
        raise GradientDescentError(
            f"Expected one scalar penalty output, got {penalty_output_values!r}."
        )
    penalty_value = float(penalty_output_values[0])
    if not math.isfinite(penalty_value):
        raise GradientDescentError(f"Penalty value is not finite: {penalty_value!r}.")
    return penalty_value


def extract_penalty_and_gradient(outputs: dict[str, Any]) -> tuple[float, list[float]]:
    """Read scalar penalty and seven-element Gradient from RhinoCompute outputs."""
    penalty_value = extract_penalty_scalar(outputs)
    gradient_output_values = outputs.get("gradient", outputs.get("Gradient"))
    if not isinstance(gradient_output_values, list):
        raise GradientDescentError(
            f"Expected seven gradient values, got {gradient_output_values!r}."
        )
    if len(gradient_output_values) != GRADIENT_COMPONENT_COUNT:
        raise GradientDescentError(
            "Expected seven gradient values, "
            f"got {len(gradient_output_values)} values: {gradient_output_values!r}."
        )

    gradient_values = [float(value) for value in gradient_output_values]
    _validate_finite_penalty_and_gradient(penalty_value, gradient_values)
    return penalty_value, gradient_values


def run_projected_gradient_descent(
    evaluator: PenaltyGradientEvaluatorProtocol,
    config: GradientDescentConfig,
) -> GradientDescentResult:
    """Run projected steepest descent with Armijo backtracking line search."""
    run_started_at = time.perf_counter()
    counting_evaluator = _wrap_counting_evaluator(evaluator)
    current_input_values = _apply_fixed_variable_values(
        config.initial_input_values,
        config.fixed_variable_values,
    )
    penalty_value, gradient_values = counting_evaluator.evaluate(current_input_values)
    initial_penalty = penalty_value
    initial_input_values = dict(current_input_values)
    accepted_iterations: list[AcceptedGradientDescentIteration] = []
    total_rejected_line_search_trial_count = 0
    projected_search_gradient = _build_projected_search_gradient(
        gradient_values=gradient_values,
        fixed_variable_values=config.fixed_variable_values,
    )
    projected_gradient_norm = math.sqrt(_squared_euclidean_norm(projected_search_gradient))

    if _is_converged(projected_gradient_norm, config.gradient_tolerance):
        return _build_gradient_descent_result(
            final_input_values=current_input_values,
            final_penalty=penalty_value,
            final_gradient_values=gradient_values,
            final_projected_gradient_norm=projected_gradient_norm,
            stop_reason="converged",
            accepted_iterations=accepted_iterations,
            rejected_line_search_trial_count=total_rejected_line_search_trial_count,
            counting_evaluator=counting_evaluator,
            initial_penalty=initial_penalty,
            initial_input_values=initial_input_values,
            run_started_at=run_started_at,
        )

    suggested_step_size = config.initial_step_size
    for iteration_index in range(config.maximum_iteration_count):
        current_objective = _objective_value(penalty_value)
        projected_search_gradient = _build_projected_search_gradient(
            gradient_values=gradient_values,
            fixed_variable_values=config.fixed_variable_values,
        )
        projected_gradient_norm_squared = _squared_euclidean_norm(projected_search_gradient)
        projected_gradient_norm = math.sqrt(projected_gradient_norm_squared)
        if _is_converged(projected_gradient_norm, config.gradient_tolerance):
            return _build_gradient_descent_result(
                final_input_values=current_input_values,
                final_penalty=penalty_value,
                final_gradient_values=gradient_values,
                final_projected_gradient_norm=projected_gradient_norm,
                stop_reason="converged",
                accepted_iterations=accepted_iterations,
                rejected_line_search_trial_count=total_rejected_line_search_trial_count,
                counting_evaluator=counting_evaluator,
                initial_penalty=initial_penalty,
                initial_input_values=initial_input_values,
                run_started_at=run_started_at,
            )
        if projected_gradient_norm_squared <= ZERO_NORM_TOLERANCE:
            return _build_gradient_descent_result(
                final_input_values=current_input_values,
                final_penalty=penalty_value,
                final_gradient_values=gradient_values,
                final_projected_gradient_norm=projected_gradient_norm,
                stop_reason="zero_projected_gradient",
                accepted_iterations=accepted_iterations,
                rejected_line_search_trial_count=total_rejected_line_search_trial_count,
                counting_evaluator=counting_evaluator,
                initial_penalty=initial_penalty,
                initial_input_values=initial_input_values,
                run_started_at=run_started_at,
            )

        accepted_step_size, rejected_trial_count, next_input_values = _find_acceptable_step(
            current_input_values=current_input_values,
            projected_search_gradient=projected_search_gradient,
            current_objective=current_objective,
            projected_gradient_norm_squared=projected_gradient_norm_squared,
            evaluator=counting_evaluator,
            config=config,
            suggested_step_size=suggested_step_size,
        )
        total_rejected_line_search_trial_count += rejected_trial_count
        if accepted_step_size is None or next_input_values is None:
            return _build_gradient_descent_result(
                final_input_values=current_input_values,
                final_penalty=penalty_value,
                final_gradient_values=gradient_values,
                final_projected_gradient_norm=projected_gradient_norm,
                stop_reason="step_size_too_small",
                accepted_iterations=accepted_iterations,
                rejected_line_search_trial_count=total_rejected_line_search_trial_count,
                counting_evaluator=counting_evaluator,
                initial_penalty=initial_penalty,
                initial_input_values=initial_input_values,
                run_started_at=run_started_at,
            )

        suggested_step_size = min(
            accepted_step_size * config.step_growth_factor,
            config.maximum_step_size,
        )
        current_input_values = next_input_values
        penalty_value, gradient_values = counting_evaluator.evaluate(current_input_values)
        next_projected_search_gradient = _build_projected_search_gradient(
            gradient_values=gradient_values,
            fixed_variable_values=config.fixed_variable_values,
        )
        next_projected_gradient_norm = math.sqrt(
            _squared_euclidean_norm(next_projected_search_gradient)
        )
        accepted_iterations.append(
            AcceptedGradientDescentIteration(
                iteration_index=iteration_index,
                input_values=dict(current_input_values),
                penalty=penalty_value,
                gradient_values=list(gradient_values),
                residual_objective=_objective_value(penalty_value),
                projected_gradient_norm=next_projected_gradient_norm,
                accepted_step_size=accepted_step_size,
                rejected_line_search_trial_count=rejected_trial_count,
            )
        )

        if _is_converged(next_projected_gradient_norm, config.gradient_tolerance):
            return _build_gradient_descent_result(
                final_input_values=current_input_values,
                final_penalty=penalty_value,
                final_gradient_values=gradient_values,
                final_projected_gradient_norm=next_projected_gradient_norm,
                stop_reason="converged",
                accepted_iterations=accepted_iterations,
                rejected_line_search_trial_count=total_rejected_line_search_trial_count,
                counting_evaluator=counting_evaluator,
                initial_penalty=initial_penalty,
                initial_input_values=initial_input_values,
                run_started_at=run_started_at,
            )

    return _build_gradient_descent_result(
        final_input_values=current_input_values,
        final_penalty=penalty_value,
        final_gradient_values=gradient_values,
        final_projected_gradient_norm=math.sqrt(
            _squared_euclidean_norm(
                _build_projected_search_gradient(
                    gradient_values=gradient_values,
                    fixed_variable_values=config.fixed_variable_values,
                )
            )
        ),
        stop_reason="max_iterations_reached",
        accepted_iterations=accepted_iterations,
        rejected_line_search_trial_count=total_rejected_line_search_trial_count,
        counting_evaluator=counting_evaluator,
        initial_penalty=initial_penalty,
        initial_input_values=initial_input_values,
        run_started_at=run_started_at,
    )


def run_projected_lbfgs(
    evaluator: PenaltyGradientEvaluatorProtocol,
    config: LbfgsConfig,
) -> LbfgsResult:
    """Run projected L-BFGS-B with fixed variables removed from the optimizer vector."""
    if config.maximum_movement_norm is not None:
        return _run_projected_lbfgs_with_movement_cap(evaluator, config)

    from scipy.optimize import minimize

    run_started_at = time.perf_counter()
    counting_evaluator = _wrap_counting_evaluator(evaluator)
    initial_input_values = _apply_fixed_variable_values(
        config.initial_input_values,
        config.fixed_variable_values,
    )
    free_variable_nicknames = _build_free_variable_nicknames(config.fixed_variable_values)
    initial_free_values = _pack_free_variable_values(
        input_values=initial_input_values,
        free_variable_nicknames=free_variable_nicknames,
    )
    initial_penalty_value: float | None = None

    def objective_and_gradient(free_values: list[float]) -> tuple[float, list[float]]:
        nonlocal initial_penalty_value
        trial_input_values = _unpack_free_variable_values(
            free_values=free_values,
            template_input_values=initial_input_values,
            fixed_variable_values=config.fixed_variable_values,
            free_variable_nicknames=free_variable_nicknames,
        )
        penalty_value, gradient_values = counting_evaluator.evaluate(trial_input_values)
        if initial_penalty_value is None:
            initial_penalty_value = penalty_value
        free_gradient_values = [
            gradient_values[CONTEXTUAL_INPUT_NICKNAMES.index(nickname)]
            for nickname in free_variable_nicknames
        ]
        return penalty_value, free_gradient_values

    optimizer_result = minimize(
        objective_and_gradient,
        initial_free_values,
        method="L-BFGS-B",
        jac=True,
        options={
            "maxiter": config.maximum_iteration_count,
            "gtol": config.gradient_tolerance,
            "ftol": config.penalty_tolerance,
            "maxcor": config.history_size,
            "maxls": config.maximum_line_search_steps,
        },
    )
    final_input_values = _unpack_free_variable_values(
        free_values=list(optimizer_result.x),
        template_input_values=initial_input_values,
        fixed_variable_values=config.fixed_variable_values,
        free_variable_nicknames=free_variable_nicknames,
    )
    final_penalty, final_gradient_values = counting_evaluator.evaluate(final_input_values)
    final_projected_search_gradient = _build_projected_search_gradient(
        gradient_values=final_gradient_values,
        fixed_variable_values=config.fixed_variable_values,
    )
    final_projected_gradient_norm = math.sqrt(
        _squared_euclidean_norm(final_projected_search_gradient)
    )
    run_metrics = GradientDescentRunMetrics(
        evaluation_count=counting_evaluator.evaluation_count,
        rhino_compute_call_count=counting_evaluator.rhino_compute_call_count,
        penalty_only_evaluation_count=counting_evaluator.penalty_only_evaluation_count,
        penalty_only_rhino_compute_call_count=(
            counting_evaluator.penalty_only_rhino_compute_call_count
        ),
        accepted_iteration_count=int(optimizer_result.nit),
        rejected_line_search_trial_count=0,
        total_wall_clock_milliseconds=_elapsed_milliseconds_since(run_started_at),
        total_evaluate_milliseconds=(
            counting_evaluator.evaluate_milliseconds_total
            + counting_evaluator.penalty_only_evaluate_milliseconds_total
        ),
        initial_penalty=(
            final_penalty if initial_penalty_value is None else initial_penalty_value
        ),
        initial_input_values=initial_input_values,
    )
    return LbfgsResult(
        final_input_values=final_input_values,
        final_penalty=final_penalty,
        final_gradient_values=final_gradient_values,
        final_projected_gradient_norm=final_projected_gradient_norm,
        stop_reason=_build_lbfgs_stop_reason(
            final_penalty=final_penalty,
            final_projected_gradient_norm=final_projected_gradient_norm,
            gradient_tolerance=config.gradient_tolerance,
            penalty_tolerance=config.penalty_tolerance,
            optimizer_success=bool(optimizer_result.success),
            optimizer_iteration_count=int(optimizer_result.nit),
            maximum_iteration_count=config.maximum_iteration_count,
        ),
        optimizer_message=str(optimizer_result.message),
        optimizer_iteration_count=int(optimizer_result.nit),
        optimizer_function_evaluation_count=int(optimizer_result.nfev),
        run_metrics=run_metrics,
    )


def _run_projected_lbfgs_with_movement_cap(
    evaluator: PenaltyGradientEvaluatorProtocol,
    config: LbfgsConfig,
) -> LbfgsResult:
    run_started_at = time.perf_counter()
    counting_evaluator = _wrap_counting_evaluator(evaluator)
    current_input_values = _apply_fixed_variable_values(
        config.initial_input_values,
        config.fixed_variable_values,
    )
    free_variable_nicknames = _build_free_variable_nicknames(config.fixed_variable_values)
    movement_scale_values = _build_free_movement_scale_values(
        free_variable_nicknames=free_variable_nicknames,
        movement_scale_values=config.movement_scale_values,
    )
    current_free_values = _pack_free_variable_values(
        input_values=current_input_values,
        free_variable_nicknames=free_variable_nicknames,
    )
    penalty_value, gradient_values = counting_evaluator.evaluate(current_input_values)
    initial_penalty = penalty_value
    initial_input_values = dict(current_input_values)
    current_free_gradient = _pack_free_gradient_values(
        gradient_values=gradient_values,
        free_variable_nicknames=free_variable_nicknames,
    )
    free_value_history: list[list[float]] = []
    free_gradient_delta_history: list[list[float]] = []
    rejected_line_search_trial_count = 0
    accepted_iteration_count = 0
    optimizer_message = "maximum iterations reached"

    for _iteration_index in range(config.maximum_iteration_count):
        projected_gradient_norm = math.sqrt(_squared_euclidean_norm(current_free_gradient))
        if _is_converged(projected_gradient_norm, config.gradient_tolerance):
            optimizer_message = "projected gradient tolerance reached"
            break
        if penalty_value <= config.penalty_tolerance:
            optimizer_message = "penalty tolerance reached"
            break

        lbfgs_direction = _build_limited_memory_bfgs_direction(
            gradient_values=current_free_gradient,
            step_history=free_value_history,
            gradient_delta_history=free_gradient_delta_history,
        )
        movement_values = _cap_movement_values(
            movement_values=lbfgs_direction,
            movement_scale_values=movement_scale_values,
            maximum_movement_norm=config.maximum_movement_norm,
        )
        directional_derivative = _dot_product(current_free_gradient, movement_values)
        if directional_derivative >= -ZERO_NORM_TOLERANCE:
            movement_values = _cap_movement_values(
                movement_values=[-component for component in current_free_gradient],
                movement_scale_values=movement_scale_values,
                maximum_movement_norm=config.maximum_movement_norm,
            )
            directional_derivative = _dot_product(current_free_gradient, movement_values)
        if directional_derivative >= -ZERO_NORM_TOLERANCE:
            optimizer_message = "no descent direction remained after movement cap"
            break

        line_search_result = _find_acceptable_capped_lbfgs_step(
            current_free_values=current_free_values,
            movement_values=movement_values,
            current_input_values=current_input_values,
            fixed_variable_values=config.fixed_variable_values,
            free_variable_nicknames=free_variable_nicknames,
            current_objective=_objective_value(penalty_value),
            directional_derivative=directional_derivative,
            evaluator=counting_evaluator,
            config=config,
        )
        rejected_line_search_trial_count += line_search_result.rejected_trial_count
        if line_search_result.next_input_values is None:
            optimizer_message = "line search failed after movement cap"
            break

        next_penalty_value, next_gradient_values = counting_evaluator.evaluate(
            line_search_result.next_input_values
        )
        next_free_values = _pack_free_variable_values(
            input_values=line_search_result.next_input_values,
            free_variable_nicknames=free_variable_nicknames,
        )
        next_free_gradient = _pack_free_gradient_values(
            gradient_values=next_gradient_values,
            free_variable_nicknames=free_variable_nicknames,
        )
        accepted_step_values = [
            next_value - current_value
            for current_value, next_value in zip(
                current_free_values,
                next_free_values,
                strict=True,
            )
        ]
        accepted_gradient_delta_values = [
            next_gradient - current_gradient
            for current_gradient, next_gradient in zip(
                current_free_gradient,
                next_free_gradient,
                strict=True,
            )
        ]
        _append_lbfgs_history(
            step_history=free_value_history,
            gradient_delta_history=free_gradient_delta_history,
            step_values=accepted_step_values,
            gradient_delta_values=accepted_gradient_delta_values,
            history_size=config.history_size,
        )
        current_input_values = line_search_result.next_input_values
        current_free_values = next_free_values
        current_free_gradient = next_free_gradient
        penalty_value = next_penalty_value
        gradient_values = next_gradient_values
        accepted_iteration_count += 1
    else:
        optimizer_message = "maximum iterations reached"

    final_projected_gradient_norm = math.sqrt(_squared_euclidean_norm(current_free_gradient))
    run_metrics = GradientDescentRunMetrics(
        evaluation_count=counting_evaluator.evaluation_count,
        rhino_compute_call_count=counting_evaluator.rhino_compute_call_count,
        penalty_only_evaluation_count=counting_evaluator.penalty_only_evaluation_count,
        penalty_only_rhino_compute_call_count=(
            counting_evaluator.penalty_only_rhino_compute_call_count
        ),
        accepted_iteration_count=accepted_iteration_count,
        rejected_line_search_trial_count=rejected_line_search_trial_count,
        total_wall_clock_milliseconds=_elapsed_milliseconds_since(run_started_at),
        total_evaluate_milliseconds=(
            counting_evaluator.evaluate_milliseconds_total
            + counting_evaluator.penalty_only_evaluate_milliseconds_total
        ),
        initial_penalty=initial_penalty,
        initial_input_values=initial_input_values,
    )
    return LbfgsResult(
        final_input_values=current_input_values,
        final_penalty=penalty_value,
        final_gradient_values=gradient_values,
        final_projected_gradient_norm=final_projected_gradient_norm,
        stop_reason=_build_lbfgs_stop_reason(
            final_penalty=penalty_value,
            final_projected_gradient_norm=final_projected_gradient_norm,
            gradient_tolerance=config.gradient_tolerance,
            penalty_tolerance=config.penalty_tolerance,
            optimizer_success=(
                final_projected_gradient_norm <= config.gradient_tolerance
                or penalty_value <= config.penalty_tolerance
            ),
            optimizer_iteration_count=accepted_iteration_count,
            maximum_iteration_count=config.maximum_iteration_count,
        ),
        optimizer_message=optimizer_message,
        optimizer_iteration_count=accepted_iteration_count,
        optimizer_function_evaluation_count=counting_evaluator.evaluation_count,
        run_metrics=run_metrics,
    )


def write_descent_run_record(
    record_path: Path | str,
    gradient_ghx_path: Path | str,
    descent_config: GradientDescentConfig,
    descent_result: GradientDescentResult,
    compute_url: str,
) -> Path:
    """Write one descent run record with metrics, config, and result to JSON."""
    output_record_path = Path(record_path)
    output_record_path.parent.mkdir(parents=True, exist_ok=True)
    record_payload = {
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "gradient_ghx_path": str(Path(gradient_ghx_path)),
        "compute_url": compute_url,
        "descent_config": _descent_config_to_dict(descent_config),
        "result": descent_result.to_dict(),
    }
    output_record_path.write_text(
        json.dumps(record_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return output_record_path


def write_lbfgs_run_record(
    record_path: Path | str,
    gradient_ghx_path: Path | str,
    lbfgs_config: LbfgsConfig,
    lbfgs_result: LbfgsResult,
    compute_url: str,
) -> Path:
    """Write one L-BFGS-B run record with metrics, config, and result to JSON."""
    output_record_path = Path(record_path)
    output_record_path.parent.mkdir(parents=True, exist_ok=True)
    record_payload = {
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "gradient_ghx_path": str(Path(gradient_ghx_path)),
        "compute_url": compute_url,
        "lbfgs_config": _lbfgs_config_to_dict(lbfgs_config),
        "result": lbfgs_result.to_dict(),
    }
    output_record_path.write_text(
        json.dumps(record_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return output_record_path


@dataclass(frozen=True)
class YPathTraceConfig:
    """Configuration for one Y-axis continuation path trace."""

    start_y: float = DEFAULT_Y_PATH_START_Y
    end_y: float = DEFAULT_Y_PATH_END_Y
    y_step: float = DEFAULT_Y_PATH_STEP
    initial_input_values: dict[str, float] = field(
        default_factory=lambda: {
            nickname: 0.0 for nickname in CONTEXTUAL_INPUT_NICKNAMES
        }
    )
    finite_difference_step: float = DEFAULT_Y_PATH_FINITE_DIFFERENCE_STEP
    maximum_movement_norm: float = DEFAULT_Y_PATH_MAXIMUM_MOVEMENT_NORM
    maximum_iterations_per_y: int = DEFAULT_Y_PATH_MAX_ITERATIONS_PER_Y
    penalty_tolerance: float = DEFAULT_PENALTY_TOLERANCE
    gradient_tolerance: float = DEFAULT_GRADIENT_TOLERANCE
    history_size: int = DEFAULT_LBFGS_HISTORY_SIZE
    maximum_line_search_steps: int = DEFAULT_LBFGS_MAXIMUM_LINE_SEARCH_STEPS
    movement_scale_values: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_MOVEMENT_SCALE_VALUES)
    )
    use_secant_prediction: bool = True
    continue_on_station_failure: bool = False


@dataclass(frozen=True)
class YPathStationResult:
    """One completed Y station along a continuation path."""

    station_index: int
    y_value: float
    initial_input_values: dict[str, float]
    final_input_values: dict[str, float]
    final_penalty: float
    final_projected_gradient_norm: float
    stop_reason: str
    optimizer_message: str
    normalized_adjacent_jump: float | None
    run_metrics: GradientDescentRunMetrics

    def to_dict(self) -> dict[str, Any]:
        return {
            "station_index": self.station_index,
            "y_value": self.y_value,
            "initial_input_values": dict(self.initial_input_values),
            "final_input_values": dict(self.final_input_values),
            "final_penalty": self.final_penalty,
            "final_projected_gradient_norm": self.final_projected_gradient_norm,
            "stop_reason": self.stop_reason,
            "optimizer_message": self.optimizer_message,
            "normalized_adjacent_jump": self.normalized_adjacent_jump,
            "run_metrics": self.run_metrics.to_dict(),
        }


@dataclass(frozen=True)
class YPathTraceResult:
    """Final result from one Y-axis continuation path trace."""

    station_results: tuple[YPathStationResult, ...]
    stop_reason: str
    total_wall_clock_milliseconds: float
    total_rhino_compute_call_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "station_results": [station_result.to_dict() for station_result in self.station_results],
            "completed_station_count": len(self.station_results),
            "stop_reason": self.stop_reason,
            "total_wall_clock_milliseconds": self.total_wall_clock_milliseconds,
            "total_rhino_compute_call_count": self.total_rhino_compute_call_count,
        }


def build_y_station_values(
    start_y: float,
    end_y: float,
    y_step: float,
) -> list[float]:
    """Build the ordered Y station values from start to end."""
    _validate_y_path_step_direction(start_y=start_y, end_y=end_y, y_step=y_step)
    station_values: list[float] = []
    current_y = start_y
    while _y_station_in_range(current_y=current_y, end_y=end_y, y_step=y_step):
        station_values.append(current_y)
        if math.isclose(current_y, end_y, abs_tol=1e-12):
            break
        current_y += y_step
    if not station_values:
        raise GradientDescentError("Y path trace produced no stations.")
    if not math.isclose(station_values[-1], end_y, abs_tol=1e-12):
        raise GradientDescentError(
            f"Y path trace did not reach end_y={end_y}; last station was {station_values[-1]}."
        )
    return station_values


def build_station_initial_input_values(
    y_value: float,
    previous_station_final_values: dict[str, float] | None,
    second_previous_station_final_values: dict[str, float] | None,
    path_config: YPathTraceConfig,
) -> dict[str, float]:
    """Build one station start from warm start or secant prediction capped by movement norm."""
    if previous_station_final_values is None:
        initial_input_values = dict(path_config.initial_input_values)
        initial_input_values[Y_PATH_FIXED_VARIABLE_NICKNAME] = y_value
        return initial_input_values

    warm_start_values = dict(previous_station_final_values)
    warm_start_values[Y_PATH_FIXED_VARIABLE_NICKNAME] = y_value
    if not path_config.use_secant_prediction or second_previous_station_final_values is None:
        return warm_start_values

    secant_target_values = _build_secant_predicted_input_values(
        previous_station_final_values=previous_station_final_values,
        second_previous_station_final_values=second_previous_station_final_values,
        next_y_value=y_value,
    )
    return cap_free_variable_input_delta(
        base_input_values=warm_start_values,
        target_input_values=secant_target_values,
        fixed_variable_values={Y_PATH_FIXED_VARIABLE_NICKNAME: y_value},
        movement_scale_values=path_config.movement_scale_values,
        maximum_movement_norm=path_config.maximum_movement_norm,
    )


def cap_free_variable_input_delta(
    base_input_values: dict[str, float],
    target_input_values: dict[str, float],
    fixed_variable_values: dict[str, float],
    movement_scale_values: dict[str, float],
    maximum_movement_norm: float,
) -> dict[str, float]:
    """Cap free-variable movement from base to target in normalized units."""
    free_variable_nicknames = _build_free_variable_nicknames(fixed_variable_values)
    free_movement_scale_values = _build_free_movement_scale_values(
        free_variable_nicknames=free_variable_nicknames,
        movement_scale_values=movement_scale_values,
    )
    free_variable_deltas = [
        target_input_values[nickname] - base_input_values[nickname]
        for nickname in free_variable_nicknames
    ]
    capped_free_variable_deltas = _cap_movement_values(
        movement_values=free_variable_deltas,
        movement_scale_values=free_movement_scale_values,
        maximum_movement_norm=maximum_movement_norm,
    )
    capped_input_values = dict(base_input_values)
    for nickname, capped_delta in zip(
        free_variable_nicknames,
        capped_free_variable_deltas,
        strict=True,
    ):
        capped_input_values[nickname] = base_input_values[nickname] + capped_delta
    for nickname, fixed_value in fixed_variable_values.items():
        capped_input_values[nickname] = fixed_value
    return capped_input_values


def measure_normalized_free_variable_jump(
    from_input_values: dict[str, float],
    to_input_values: dict[str, float],
    fixed_variable_values: dict[str, float],
    movement_scale_values: dict[str, float],
) -> float:
    """Measure normalized movement between two stations over free variables only."""
    free_variable_nicknames = _build_free_variable_nicknames(fixed_variable_values)
    free_movement_scale_values = _build_free_movement_scale_values(
        free_variable_nicknames=free_variable_nicknames,
        movement_scale_values=movement_scale_values,
    )
    free_variable_deltas = [
        to_input_values[nickname] - from_input_values[nickname]
        for nickname in free_variable_nicknames
    ]
    return _normalized_movement_norm(
        movement_values=free_variable_deltas,
        movement_scale_values=free_movement_scale_values,
    )


def run_y_path_trace(
    evaluator: PenaltyGradientEvaluatorProtocol,
    path_config: YPathTraceConfig,
    record_jsonl_path: Path | str | None = None,
    record_csv_path: Path | str | None = None,
    resume: bool = False,
) -> YPathTraceResult:
    """Trace a low-penalty path while moving Y from start_y to end_y."""
    run_started_at = time.perf_counter()
    output_jsonl_path = Path(record_jsonl_path or DEFAULT_Y_PATH_TRACE_JSONL_PATH)
    output_csv_path = Path(record_csv_path or DEFAULT_Y_PATH_TRACE_CSV_PATH)
    all_y_station_values = build_y_station_values(
        start_y=path_config.start_y,
        end_y=path_config.end_y,
        y_step=path_config.y_step,
    )
    completed_station_results: list[YPathStationResult] = []
    resume_state = _load_y_path_resume_state(
        record_jsonl_path=output_jsonl_path,
        path_config=path_config,
        resume=resume,
    )
    if resume_state is not None:
        completed_station_results = list(resume_state.completed_station_results)
        pending_y_station_values = resume_state.pending_y_station_values
    else:
        output_jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        _write_y_path_header_record(
            record_jsonl_path=output_jsonl_path,
            path_config=path_config,
        )
        pending_y_station_values = all_y_station_values

    previous_station_final_values: dict[str, float] | None = None
    second_previous_station_final_values: dict[str, float] | None = None
    if completed_station_results:
        if len(completed_station_results) >= 1:
            previous_station_final_values = dict(
                completed_station_results[-1].final_input_values
            )
        if len(completed_station_results) >= 2:
            second_previous_station_final_values = dict(
                completed_station_results[-2].final_input_values
            )

    path_stop_reason = "completed_all_stations"
    for station_index, y_value in enumerate(
        pending_y_station_values,
        start=len(completed_station_results),
    ):
        station_initial_input_values = build_station_initial_input_values(
            y_value=y_value,
            previous_station_final_values=previous_station_final_values,
            second_previous_station_final_values=second_previous_station_final_values,
            path_config=path_config,
        )
        normalized_adjacent_jump = None
        if previous_station_final_values is not None:
            normalized_adjacent_jump = measure_normalized_free_variable_jump(
                from_input_values=previous_station_final_values,
                to_input_values=station_initial_input_values,
                fixed_variable_values={Y_PATH_FIXED_VARIABLE_NICKNAME: y_value},
                movement_scale_values=path_config.movement_scale_values,
            )
        lbfgs_config = LbfgsConfig(
            initial_input_values=station_initial_input_values,
            fixed_variable_values={Y_PATH_FIXED_VARIABLE_NICKNAME: y_value},
            penalty_tolerance=path_config.penalty_tolerance,
            gradient_tolerance=path_config.gradient_tolerance,
            maximum_iteration_count=path_config.maximum_iterations_per_y,
            history_size=path_config.history_size,
            maximum_line_search_steps=path_config.maximum_line_search_steps,
            maximum_movement_norm=path_config.maximum_movement_norm,
            movement_scale_values=dict(path_config.movement_scale_values),
        )
        lbfgs_result = run_projected_lbfgs(evaluator, lbfgs_config)
        station_result = YPathStationResult(
            station_index=station_index,
            y_value=y_value,
            initial_input_values=station_initial_input_values,
            final_input_values=dict(lbfgs_result.final_input_values),
            final_penalty=lbfgs_result.final_penalty,
            final_projected_gradient_norm=lbfgs_result.final_projected_gradient_norm,
            stop_reason=lbfgs_result.stop_reason,
            optimizer_message=lbfgs_result.optimizer_message,
            normalized_adjacent_jump=normalized_adjacent_jump,
            run_metrics=lbfgs_result.run_metrics,
        )
        completed_station_results.append(station_result)
        _append_y_path_station_record(
            record_jsonl_path=output_jsonl_path,
            station_result=station_result,
        )
        write_y_path_csv_summary(
            record_csv_path=output_csv_path,
            station_results=completed_station_results,
        )
        second_previous_station_final_values = previous_station_final_values
        previous_station_final_values = dict(station_result.final_input_values)
        if not _is_acceptable_y_path_station_result(
            station_result=station_result,
            path_config=path_config,
        ):
            path_stop_reason = "station_failed"
            break

    total_rhino_compute_call_count = sum(
        station_result.run_metrics.rhino_compute_call_count
        + station_result.run_metrics.penalty_only_rhino_compute_call_count
        for station_result in completed_station_results
    )
    return YPathTraceResult(
        station_results=tuple(completed_station_results),
        stop_reason=path_stop_reason,
        total_wall_clock_milliseconds=_elapsed_milliseconds_since(run_started_at),
        total_rhino_compute_call_count=total_rhino_compute_call_count,
    )


def write_y_path_csv_summary(
    record_csv_path: Path | str,
    station_results: list[YPathStationResult],
) -> Path:
    """Write one CSV summary for all completed Y path stations."""
    output_csv_path = Path(record_csv_path)
    output_csv_path.parent.mkdir(parents=True, exist_ok=True)
    field_names = [
        "station_index",
        "y_value",
        "final_penalty",
        "final_projected_gradient_norm",
        "stop_reason",
        "normalized_adjacent_jump",
        "evaluation_count",
        "rhino_compute_call_count",
        "penalty_only_evaluation_count",
        "penalty_only_rhino_compute_call_count",
        "total_wall_clock_milliseconds",
        "X",
        "Z",
        "RX",
        "RY",
        "RZ",
        "RS",
    ]
    with output_csv_path.open("w", encoding="utf-8", newline="") as csv_file:
        csv_writer = csv.DictWriter(csv_file, fieldnames=field_names)
        csv_writer.writeheader()
        for station_result in station_results:
            final_input_values = station_result.final_input_values
            csv_writer.writerow(
                {
                    "station_index": station_result.station_index,
                    "y_value": station_result.y_value,
                    "final_penalty": station_result.final_penalty,
                    "final_projected_gradient_norm": station_result.final_projected_gradient_norm,
                    "stop_reason": station_result.stop_reason,
                    "normalized_adjacent_jump": station_result.normalized_adjacent_jump,
                    "evaluation_count": station_result.run_metrics.evaluation_count,
                    "rhino_compute_call_count": station_result.run_metrics.rhino_compute_call_count,
                    "penalty_only_evaluation_count": (
                        station_result.run_metrics.penalty_only_evaluation_count
                    ),
                    "penalty_only_rhino_compute_call_count": (
                        station_result.run_metrics.penalty_only_rhino_compute_call_count
                    ),
                    "total_wall_clock_milliseconds": (
                        station_result.run_metrics.total_wall_clock_milliseconds
                    ),
                    "X": final_input_values["X"],
                    "Z": final_input_values["Z"],
                    "RX": final_input_values["RX"],
                    "RY": final_input_values["RY"],
                    "RZ": final_input_values["RZ"],
                    "RS": final_input_values["RS"],
                }
            )
    return output_csv_path


@dataclass(frozen=True)
class _YPathResumeState:
    """Resume state loaded from one existing JSONL path trace."""

    completed_station_results: tuple[YPathStationResult, ...]
    pending_y_station_values: list[float]


def _wrap_counting_evaluator(
    evaluator: PenaltyGradientEvaluatorProtocol,
) -> CountingPenaltyGradientEvaluator:
    if isinstance(evaluator, CountingPenaltyGradientEvaluator):
        return evaluator
    return CountingPenaltyGradientEvaluator(inner_evaluator=evaluator)


def _build_gradient_descent_result(
    final_input_values: dict[str, float],
    final_penalty: float,
    final_gradient_values: list[float],
    final_projected_gradient_norm: float,
    stop_reason: str,
    accepted_iterations: list[AcceptedGradientDescentIteration],
    rejected_line_search_trial_count: int,
    counting_evaluator: CountingPenaltyGradientEvaluator,
    initial_penalty: float,
    initial_input_values: dict[str, float],
    run_started_at: float,
) -> GradientDescentResult:
    run_metrics = GradientDescentRunMetrics(
        evaluation_count=counting_evaluator.evaluation_count,
        rhino_compute_call_count=counting_evaluator.rhino_compute_call_count,
        penalty_only_evaluation_count=counting_evaluator.penalty_only_evaluation_count,
        penalty_only_rhino_compute_call_count=(
            counting_evaluator.penalty_only_rhino_compute_call_count
        ),
        accepted_iteration_count=len(accepted_iterations),
        rejected_line_search_trial_count=rejected_line_search_trial_count,
        total_wall_clock_milliseconds=_elapsed_milliseconds_since(run_started_at),
        total_evaluate_milliseconds=(
            counting_evaluator.evaluate_milliseconds_total
            + counting_evaluator.penalty_only_evaluate_milliseconds_total
        ),
        initial_penalty=initial_penalty,
        initial_input_values=initial_input_values,
    )
    return GradientDescentResult(
        final_input_values=dict(final_input_values),
        final_penalty=final_penalty,
        final_gradient_values=list(final_gradient_values),
        final_projected_gradient_norm=final_projected_gradient_norm,
        stop_reason=stop_reason,
        accepted_iterations=tuple(accepted_iterations),
        rejected_line_search_trial_count=rejected_line_search_trial_count,
        run_metrics=run_metrics,
    )


def _descent_config_to_dict(descent_config: GradientDescentConfig) -> dict[str, Any]:
    return {
        "initial_input_values": dict(descent_config.initial_input_values),
        "fixed_variable_values": dict(descent_config.fixed_variable_values),
        "penalty_tolerance": descent_config.penalty_tolerance,
        "gradient_tolerance": descent_config.gradient_tolerance,
        "maximum_iteration_count": descent_config.maximum_iteration_count,
        "initial_step_size": descent_config.initial_step_size,
        "maximum_step_size": descent_config.maximum_step_size,
        "step_growth_factor": descent_config.step_growth_factor,
        "backtracking_reduction_factor": descent_config.backtracking_reduction_factor,
        "armijo_factor": descent_config.armijo_factor,
        "minimum_step_size": descent_config.minimum_step_size,
        "maximum_line_search_attempts": descent_config.maximum_line_search_attempts,
    }


def _lbfgs_config_to_dict(lbfgs_config: LbfgsConfig) -> dict[str, Any]:
    return {
        "initial_input_values": dict(lbfgs_config.initial_input_values),
        "fixed_variable_values": dict(lbfgs_config.fixed_variable_values),
        "penalty_tolerance": lbfgs_config.penalty_tolerance,
        "gradient_tolerance": lbfgs_config.gradient_tolerance,
        "maximum_iteration_count": lbfgs_config.maximum_iteration_count,
        "history_size": lbfgs_config.history_size,
        "maximum_line_search_steps": lbfgs_config.maximum_line_search_steps,
        "maximum_movement_norm": lbfgs_config.maximum_movement_norm,
        "movement_scale_values": dict(lbfgs_config.movement_scale_values),
    }


def _find_acceptable_capped_lbfgs_step(
    current_free_values: list[float],
    movement_values: list[float],
    current_input_values: dict[str, float],
    fixed_variable_values: dict[str, float],
    free_variable_nicknames: tuple[str, ...],
    current_objective: float,
    directional_derivative: float,
    evaluator: CountingPenaltyGradientEvaluator,
    config: LbfgsConfig,
) -> CappedLbfgsLineSearchResult:
    line_search_multiplier = 1.0
    rejected_trial_count = 0
    for _line_search_attempt_index in range(config.maximum_line_search_steps):
        trial_free_values = [
            current_value + line_search_multiplier * movement_value
            for current_value, movement_value in zip(
                current_free_values,
                movement_values,
                strict=True,
            )
        ]
        trial_input_values = _unpack_free_variable_values(
            free_values=trial_free_values,
            template_input_values=current_input_values,
            fixed_variable_values=fixed_variable_values,
            free_variable_nicknames=free_variable_nicknames,
        )
        trial_penalty_value = evaluator.evaluate_penalty(trial_input_values)
        armijo_threshold = (
            current_objective
            + DEFAULT_ARMIJO_FACTOR * line_search_multiplier * directional_derivative
        )
        if _objective_value(trial_penalty_value) <= armijo_threshold:
            return CappedLbfgsLineSearchResult(
                rejected_trial_count=rejected_trial_count,
                next_input_values=trial_input_values,
            )
        rejected_trial_count += 1
        line_search_multiplier *= DEFAULT_BACKTRACKING_REDUCTION_FACTOR
    return CappedLbfgsLineSearchResult(
        rejected_trial_count=rejected_trial_count,
        next_input_values=None,
    )


def _build_limited_memory_bfgs_direction(
    gradient_values: list[float],
    step_history: list[list[float]],
    gradient_delta_history: list[list[float]],
) -> list[float]:
    if not step_history:
        return [-component for component in gradient_values]

    q_values = list(gradient_values)
    alpha_values: list[float] = []
    rho_values: list[float] = []
    for step_values, gradient_delta_values in reversed(
        list(zip(step_history, gradient_delta_history, strict=True))
    ):
        curvature = _dot_product(step_values, gradient_delta_values)
        if curvature <= ZERO_NORM_TOLERANCE:
            alpha_values.append(0.0)
            rho_values.append(0.0)
            continue
        rho_value = 1.0 / curvature
        alpha_value = rho_value * _dot_product(step_values, q_values)
        q_values = [
            q_value - alpha_value * gradient_delta_value
            for q_value, gradient_delta_value in zip(
                q_values,
                gradient_delta_values,
                strict=True,
            )
        ]
        alpha_values.append(alpha_value)
        rho_values.append(rho_value)

    latest_step_values = step_history[-1]
    latest_gradient_delta_values = gradient_delta_history[-1]
    latest_curvature = _dot_product(latest_step_values, latest_gradient_delta_values)
    latest_gradient_delta_norm_squared = _squared_euclidean_norm(
        latest_gradient_delta_values
    )
    initial_inverse_hessian_scale = 1.0
    if latest_gradient_delta_norm_squared > ZERO_NORM_TOLERANCE:
        initial_inverse_hessian_scale = latest_curvature / latest_gradient_delta_norm_squared
    r_values = [initial_inverse_hessian_scale * q_value for q_value in q_values]

    reversed_history = list(zip(step_history, gradient_delta_history, strict=True))
    for history_index, (step_values, gradient_delta_values) in enumerate(reversed_history):
        alpha_value = alpha_values[len(reversed_history) - history_index - 1]
        rho_value = rho_values[len(reversed_history) - history_index - 1]
        beta_value = rho_value * _dot_product(gradient_delta_values, r_values)
        r_values = [
            r_value + step_value * (alpha_value - beta_value)
            for r_value, step_value in zip(r_values, step_values, strict=True)
        ]
    return [-component for component in r_values]


def _append_lbfgs_history(
    step_history: list[list[float]],
    gradient_delta_history: list[list[float]],
    step_values: list[float],
    gradient_delta_values: list[float],
    history_size: int,
) -> None:
    if _dot_product(step_values, gradient_delta_values) <= ZERO_NORM_TOLERANCE:
        return
    step_history.append(step_values)
    gradient_delta_history.append(gradient_delta_values)
    if len(step_history) <= history_size:
        return
    del step_history[0]
    del gradient_delta_history[0]


def _cap_movement_values(
    movement_values: list[float],
    movement_scale_values: list[float],
    maximum_movement_norm: float,
) -> list[float]:
    movement_norm = _normalized_movement_norm(movement_values, movement_scale_values)
    if movement_norm <= maximum_movement_norm:
        return list(movement_values)
    if movement_norm <= ZERO_NORM_TOLERANCE:
        return list(movement_values)
    movement_multiplier = maximum_movement_norm / movement_norm
    return [movement_value * movement_multiplier for movement_value in movement_values]


def _normalized_movement_norm(
    movement_values: list[float],
    movement_scale_values: list[float],
) -> float:
    return math.sqrt(
        sum(
            (movement_value / movement_scale_value)
            * (movement_value / movement_scale_value)
            for movement_value, movement_scale_value in zip(
                movement_values,
                movement_scale_values,
                strict=True,
            )
        )
    )


def _build_free_movement_scale_values(
    free_variable_nicknames: tuple[str, ...],
    movement_scale_values: dict[str, float],
) -> list[float]:
    free_movement_scale_values: list[float] = []
    for nickname in free_variable_nicknames:
        movement_scale_value = movement_scale_values.get(nickname)
        if movement_scale_value is None:
            raise GradientDescentError(f"Missing movement scale for {nickname!r}.")
        if movement_scale_value <= 0.0:
            raise GradientDescentError(
                f"Movement scale for {nickname!r} must be positive, got "
                f"{movement_scale_value!r}."
            )
        free_movement_scale_values.append(movement_scale_value)
    return free_movement_scale_values


def _build_free_variable_nicknames(
    fixed_variable_values: dict[str, float],
) -> tuple[str, ...]:
    return tuple(
        nickname
        for nickname in CONTEXTUAL_INPUT_NICKNAMES
        if nickname not in fixed_variable_values
    )


def _pack_free_variable_values(
    input_values: dict[str, float],
    free_variable_nicknames: tuple[str, ...],
) -> list[float]:
    return [input_values[nickname] for nickname in free_variable_nicknames]


def _pack_free_gradient_values(
    gradient_values: list[float],
    free_variable_nicknames: tuple[str, ...],
) -> list[float]:
    return [
        gradient_values[CONTEXTUAL_INPUT_NICKNAMES.index(nickname)]
        for nickname in free_variable_nicknames
    ]


def _unpack_free_variable_values(
    free_values: list[float],
    template_input_values: dict[str, float],
    fixed_variable_values: dict[str, float],
    free_variable_nicknames: tuple[str, ...],
) -> dict[str, float]:
    if len(free_values) != len(free_variable_nicknames):
        raise GradientDescentError(
            "L-BFGS-B optimizer vector length mismatch: "
            f"expected {len(free_variable_nicknames)}, got {len(free_values)}."
        )
    input_values = dict(template_input_values)
    for nickname, value in zip(free_variable_nicknames, free_values, strict=True):
        input_values[nickname] = float(value)
    for nickname, fixed_value in fixed_variable_values.items():
        input_values[nickname] = fixed_value
    return input_values


def _dot_product(left_values: list[float], right_values: list[float]) -> float:
    return sum(
        left_value * right_value
        for left_value, right_value in zip(left_values, right_values, strict=True)
    )


def _build_lbfgs_stop_reason(
    final_penalty: float,
    final_projected_gradient_norm: float,
    gradient_tolerance: float,
    penalty_tolerance: float,
    optimizer_success: bool,
    optimizer_iteration_count: int,
    maximum_iteration_count: int,
) -> str:
    if final_projected_gradient_norm <= gradient_tolerance:
        return "converged"
    if final_penalty <= penalty_tolerance:
        return "penalty_tolerance_reached"
    if optimizer_iteration_count >= maximum_iteration_count:
        return "max_iterations_reached"
    if optimizer_success:
        return "optimizer_converged"
    return "optimizer_stopped"


def _read_compute_call_count_per_evaluation(
    evaluator: PenaltyGradientEvaluatorProtocol,
) -> int:
    raw_compute_call_count = getattr(evaluator, "compute_call_count_per_evaluation", 0)
    return int(raw_compute_call_count)


def _read_penalty_only_compute_call_count(
    evaluator: PenaltyGradientEvaluatorProtocol,
) -> int:
    raw_compute_call_count = getattr(
        evaluator,
        "penalty_only_compute_call_count_per_evaluation",
        _read_compute_call_count_per_evaluation(evaluator),
    )
    return int(raw_compute_call_count)


def _supports_penalty_only_evaluation(
    evaluator: PenaltyGradientEvaluatorProtocol,
) -> bool:
    return hasattr(evaluator, "evaluate_penalty")


def _elapsed_milliseconds_since(started_at: float) -> float:
    return (time.perf_counter() - started_at) * 1000.0


def _apply_fixed_variable_values(
    input_values: dict[str, float],
    fixed_variable_values: dict[str, float],
) -> dict[str, float]:
    merged_input_values = dict(input_values)
    for nickname in CONTEXTUAL_INPUT_NICKNAMES:
        if nickname not in merged_input_values:
            raise GradientDescentError(f"Missing initial input value for {nickname!r}.")
    for nickname, fixed_value in fixed_variable_values.items():
        merged_input_values[nickname] = fixed_value
    return merged_input_values


def _build_projected_search_gradient(
    gradient_values: list[float],
    fixed_variable_values: dict[str, float],
) -> list[float]:
    projected_search_gradient = list(gradient_values)
    for nickname in fixed_variable_values:
        nickname_index = CONTEXTUAL_INPUT_NICKNAMES.index(nickname)
        projected_search_gradient[nickname_index] = 0.0
    return projected_search_gradient


def _find_acceptable_step(
    current_input_values: dict[str, float],
    projected_search_gradient: list[float],
    current_objective: float,
    projected_gradient_norm_squared: float,
    evaluator: PenaltyGradientEvaluatorProtocol,
    config: GradientDescentConfig,
    suggested_step_size: float,
) -> tuple[float | None, int, dict[str, float] | None]:
    step_size = min(suggested_step_size, config.maximum_step_size)
    rejected_trial_count = 0

    for _line_search_attempt_index in range(config.maximum_line_search_attempts):
        if step_size < config.minimum_step_size:
            return None, rejected_trial_count, None

        trial_input_values = _apply_projected_step(
            current_input_values=current_input_values,
            projected_search_gradient=projected_search_gradient,
            step_size=step_size,
            fixed_variable_values=config.fixed_variable_values,
        )
        trial_penalty_value = evaluator.evaluate_penalty(trial_input_values)
        trial_objective = _objective_value(trial_penalty_value)
        armijo_threshold = (
            current_objective
            - config.armijo_factor * step_size * projected_gradient_norm_squared
        )
        if trial_objective <= armijo_threshold:
            return step_size, rejected_trial_count, trial_input_values

        rejected_trial_count += 1
        step_size *= config.backtracking_reduction_factor

    return None, rejected_trial_count, None


def _apply_projected_step(
    current_input_values: dict[str, float],
    projected_search_gradient: list[float],
    step_size: float,
    fixed_variable_values: dict[str, float],
) -> dict[str, float]:
    next_input_values = dict(current_input_values)
    for nickname_index, nickname in enumerate(CONTEXTUAL_INPUT_NICKNAMES):
        if nickname in fixed_variable_values:
            next_input_values[nickname] = fixed_variable_values[nickname]
            continue
        next_input_values[nickname] = (
            current_input_values[nickname]
            - step_size * projected_search_gradient[nickname_index]
        )
    return next_input_values


def _objective_value(penalty_value: float) -> float:
    return penalty_value


def _is_converged(projected_gradient_norm: float, gradient_tolerance: float) -> bool:
    return projected_gradient_norm <= gradient_tolerance


def _squared_euclidean_norm(vector_values: list[float]) -> float:
    return sum(component * component for component in vector_values)


def _validate_finite_penalty_and_gradient(
    penalty_value: float,
    gradient_values: list[float],
) -> None:
    if not math.isfinite(penalty_value):
        raise GradientDescentError(f"Penalty value is not finite: {penalty_value!r}.")
    if len(gradient_values) != GRADIENT_COMPONENT_COUNT:
        raise GradientDescentError(
            f"Expected seven gradient values, got {len(gradient_values)}."
        )
    if not all(math.isfinite(gradient_component) for gradient_component in gradient_values):
        raise GradientDescentError(
            f"Gradient values are not finite: {gradient_values!r}."
        )


def _validate_y_path_step_direction(
    start_y: float,
    end_y: float,
    y_step: float,
) -> None:
    if y_step == 0.0:
        raise GradientDescentError("Y path step must not be zero.")
    if start_y < end_y and y_step < 0.0:
        raise GradientDescentError(
            f"Y path step {y_step} must be positive when moving from {start_y} to {end_y}."
        )
    if start_y > end_y and y_step > 0.0:
        raise GradientDescentError(
            f"Y path step {y_step} must be negative when moving from {start_y} to {end_y}."
        )


def _y_station_in_range(
    current_y: float,
    end_y: float,
    y_step: float,
) -> bool:
    if y_step > 0.0:
        return current_y <= end_y + abs(y_step) * ZERO_NORM_TOLERANCE
    return current_y >= end_y - abs(y_step) * ZERO_NORM_TOLERANCE


def _build_secant_predicted_input_values(
    previous_station_final_values: dict[str, float],
    second_previous_station_final_values: dict[str, float],
    next_y_value: float,
) -> dict[str, float]:
    predicted_input_values = {Y_PATH_FIXED_VARIABLE_NICKNAME: next_y_value}
    for nickname in CONTEXTUAL_INPUT_NICKNAMES:
        if nickname == Y_PATH_FIXED_VARIABLE_NICKNAME:
            continue
        previous_value = previous_station_final_values[nickname]
        second_previous_value = second_previous_station_final_values[nickname]
        predicted_input_values[nickname] = (
            previous_value + (previous_value - second_previous_value)
        )
    return predicted_input_values


def _write_y_path_header_record(
    record_jsonl_path: Path,
    path_config: YPathTraceConfig,
) -> None:
    header_record = {
        "record_kind": Y_PATH_RECORD_KIND_HEADER,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "path_config": _y_path_config_to_dict(path_config),
    }
    record_jsonl_path.write_text(
        json.dumps(header_record, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _append_y_path_station_record(
    record_jsonl_path: Path,
    station_result: YPathStationResult,
) -> None:
    station_record = {
        "record_kind": Y_PATH_RECORD_KIND_STATION,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "station": station_result.to_dict(),
    }
    with record_jsonl_path.open("a", encoding="utf-8") as jsonl_file:
        jsonl_file.write(json.dumps(station_record, ensure_ascii=False) + "\n")


def _load_y_path_resume_state(
    record_jsonl_path: Path,
    path_config: YPathTraceConfig,
    resume: bool,
) -> _YPathResumeState | None:
    if not resume:
        return None
    if not record_jsonl_path.is_file():
        raise GradientDescentError(
            f"Cannot resume Y path trace because record file was not found: {record_jsonl_path}."
        )
    header_config: dict[str, Any] | None = None
    completed_station_results: list[YPathStationResult] = []
    for line_index, raw_line in enumerate(
        record_jsonl_path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        if not raw_line.strip():
            continue
        record_payload = json.loads(raw_line)
        record_kind = record_payload.get("record_kind")
        if record_kind == Y_PATH_RECORD_KIND_HEADER:
            header_config = record_payload.get("path_config")
            continue
        if record_kind != Y_PATH_RECORD_KIND_STATION:
            raise GradientDescentError(
                f"Unsupported record kind at line {line_index}: {record_kind!r}."
            )
        station_payload = record_payload.get("station")
        if not isinstance(station_payload, dict):
            raise GradientDescentError(
                f"Station record at line {line_index} is missing station payload."
            )
        completed_station_results.append(_parse_y_path_station_result(station_payload))

    if header_config is None:
        raise GradientDescentError("Y path trace record is missing a header line.")
    if not _y_path_configs_match_for_resume(
        stored_config=header_config,
        requested_config=path_config,
    ):
        raise GradientDescentError(
            "Resume path config does not match the stored JSONL header config."
        )
    all_y_station_values = build_y_station_values(
        start_y=path_config.start_y,
        end_y=path_config.end_y,
        y_step=path_config.y_step,
    )
    if len(completed_station_results) >= len(all_y_station_values):
        raise GradientDescentError("Y path trace is already complete; nothing to resume.")
    pending_y_station_values = all_y_station_values[len(completed_station_results) :]
    return _YPathResumeState(
        completed_station_results=tuple(completed_station_results),
        pending_y_station_values=pending_y_station_values,
    )


def _parse_y_path_station_result(station_payload: dict[str, Any]) -> YPathStationResult:
    run_metrics_payload = station_payload["run_metrics"]
    run_metrics = GradientDescentRunMetrics(
        evaluation_count=int(run_metrics_payload["evaluation_count"]),
        rhino_compute_call_count=int(run_metrics_payload["rhino_compute_call_count"]),
        penalty_only_evaluation_count=int(
            run_metrics_payload["penalty_only_evaluation_count"]
        ),
        penalty_only_rhino_compute_call_count=int(
            run_metrics_payload["penalty_only_rhino_compute_call_count"]
        ),
        accepted_iteration_count=int(run_metrics_payload["accepted_iteration_count"]),
        rejected_line_search_trial_count=int(
            run_metrics_payload["rejected_line_search_trial_count"]
        ),
        total_wall_clock_milliseconds=float(
            run_metrics_payload["total_wall_clock_milliseconds"]
        ),
        total_evaluate_milliseconds=float(run_metrics_payload["total_evaluate_milliseconds"]),
        initial_penalty=float(run_metrics_payload["initial_penalty"]),
        initial_input_values=dict(run_metrics_payload["initial_input_values"]),
    )
    return YPathStationResult(
        station_index=int(station_payload["station_index"]),
        y_value=float(station_payload["y_value"]),
        initial_input_values=dict(station_payload["initial_input_values"]),
        final_input_values=dict(station_payload["final_input_values"]),
        final_penalty=float(station_payload["final_penalty"]),
        final_projected_gradient_norm=float(station_payload["final_projected_gradient_norm"]),
        stop_reason=str(station_payload["stop_reason"]),
        optimizer_message=str(station_payload["optimizer_message"]),
        normalized_adjacent_jump=station_payload.get("normalized_adjacent_jump"),
        run_metrics=run_metrics,
    )


def _y_path_config_to_dict(path_config: YPathTraceConfig) -> dict[str, Any]:
    return {
        "start_y": path_config.start_y,
        "end_y": path_config.end_y,
        "y_step": path_config.y_step,
        "initial_input_values": dict(path_config.initial_input_values),
        "finite_difference_step": path_config.finite_difference_step,
        "maximum_movement_norm": path_config.maximum_movement_norm,
        "maximum_iterations_per_y": path_config.maximum_iterations_per_y,
        "penalty_tolerance": path_config.penalty_tolerance,
        "gradient_tolerance": path_config.gradient_tolerance,
        "history_size": path_config.history_size,
        "maximum_line_search_steps": path_config.maximum_line_search_steps,
        "movement_scale_values": dict(path_config.movement_scale_values),
        "use_secant_prediction": path_config.use_secant_prediction,
        "continue_on_station_failure": path_config.continue_on_station_failure,
    }


def _y_path_configs_match_for_resume(
    stored_config: dict[str, Any],
    requested_config: YPathTraceConfig,
) -> bool:
    requested_config_dict = _y_path_config_to_dict(requested_config)
    for config_key, requested_value in requested_config_dict.items():
        stored_value = stored_config.get(config_key)
        if isinstance(requested_value, dict):
            if stored_value != requested_value:
                return False
            continue
        if stored_value != requested_value:
            return False
    return True


def _is_acceptable_y_path_station_result(
    station_result: YPathStationResult,
    path_config: YPathTraceConfig,
) -> bool:
    if path_config.continue_on_station_failure:
        return True
    if station_result.stop_reason in {
        "converged",
        "penalty_tolerance_reached",
        "optimizer_converged",
        "max_iterations_reached",
    }:
        return True
    return False
