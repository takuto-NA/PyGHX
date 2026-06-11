"""Projected gradient descent for gradient-enabled penalty GHX definitions."""

from __future__ import annotations

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
    }


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
