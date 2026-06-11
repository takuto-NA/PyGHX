"""Integration tests for in-graph penalty and Gradient outputs."""

from __future__ import annotations

import math
import os
import shutil
from pathlib import Path

import pytest

from pyghx.compute import ComputeInputValue, evaluate_document
from pyghx.ghx_component_edit import (
    find_context_bake_by_compute_param_name,
    load_ghx_root_from_path,
    read_component_output_param_guid,
    wire_context_bake_to_output_param,
    write_ghx_document,
)
from pyghx.gradient_transform import (
    STREAM_FILTER_OUTPUT_PARAM_NAME,
    find_stream_filter_object,
    transform_penalty_graph_for_gradient,
)
from pyghx.inspect import inspect_document
from pyghx.validate import validate_document
from tests.helpers import DEFAULT_RHINO_COMPUTE_URL, is_rhino_compute_available

FINITE_DIFFERENCE_STEP = 1.0
CONTEXTUAL_INPUT_NICKNAMES = ("X", "Y", "Z", "RX", "RY", "RZ", "RS")
GRADIENT_TOLERANCE = 1e-3
VECTORIZED_PENALTY_BRANCH_COUNT = 8

SAMPLE_INPUT_CASES: tuple[dict[str, float], ...] = (
    {
        "X": 1.0,
        "Y": 1.0,
        "Z": 1.0,
        "RX": 1.0,
        "RY": 1.0,
        "RZ": 1.0,
        "RS": 1.0,
    },
    {
        "X": 100.0,
        "Y": 50.0,
        "Z": 30.0,
        "RX": 10.0,
        "RY": 5.0,
        "RZ": 15.0,
        "RS": 45.0,
    },
)


def gradient_source_ghx_path() -> Path | None:
    """Return the optional private penalty GHX path from the environment."""
    raw_path = os.environ.get("PYGHX_GRADIENT_SOURCE_GHX")
    if not raw_path:
        return None
    path = Path(raw_path)
    if not path.is_file():
        return None
    return path


def _build_compute_input_values(sample_inputs: dict[str, float]) -> list[ComputeInputValue]:
    return [
        ComputeInputValue(nickname=nickname, value=sample_inputs[nickname])
        for nickname in CONTEXTUAL_INPUT_NICKNAMES
    ]


def _extract_scalar_output(outputs: dict[str, object], parameter_name: str) -> float:
    output_values = outputs.get(parameter_name.lower(), outputs.get(parameter_name))
    if not isinstance(output_values, list) or not output_values:
        raise AssertionError(f"Expected one scalar value for {parameter_name!r}, got {output_values!r}.")
    return float(output_values[0])


def _extract_gradient_output(outputs: dict[str, object]) -> list[float]:
    gradient_values = outputs.get("gradient", outputs.get("Gradient"))
    if not isinstance(gradient_values, list) or len(gradient_values) != 7:
        raise AssertionError(f"Expected seven gradient values, got {gradient_values!r}.")
    return [float(value) for value in gradient_values]


def _extract_vectorized_penalty_cases(outputs: dict[str, object]) -> list[float]:
    penalty_values = outputs.get("penalty")
    if not isinstance(penalty_values, list):
        raise AssertionError(f"Expected penalty list output, got {penalty_values!r}.")
    if len(penalty_values) != VECTORIZED_PENALTY_BRANCH_COUNT:
        raise AssertionError(
            "Expected eight vectorized penalty values, "
            f"got {len(penalty_values)} values: {penalty_values!r}."
        )
    return [float(value) for value in penalty_values]


def _build_stream_filter_penalty_probe_ghx(
    gradient_ghx_path: Path,
    probe_output_path: Path,
) -> Path:
    """Wire penalty Context Bake to Stream Filter output for eight-case probing."""
    shutil.copy2(gradient_ghx_path, probe_output_path)
    root_element = load_ghx_root_from_path(probe_output_path)
    stream_filter_object = find_stream_filter_object(root_element)
    stream_filter_output_param_guid = read_component_output_param_guid(
        stream_filter_object,
        STREAM_FILTER_OUTPUT_PARAM_NAME,
    )
    penalty_context_bake_object = find_context_bake_by_compute_param_name(
        root_element,
        "penalty",
    )
    wire_context_bake_to_output_param(
        penalty_context_bake_object,
        source_output_param_guid=stream_filter_output_param_guid,
        compute_param_name="penalty",
        root_element=root_element,
    )
    write_ghx_document(root_element, probe_output_path)
    return probe_output_path


def _compute_forward_difference_from_penalty_cases(
    penalty_cases: list[float],
) -> tuple[float, list[float]]:
    base_penalty = penalty_cases[0]
    gradient_values = [
        (penalty_cases[case_index] - base_penalty) / FINITE_DIFFERENCE_STEP
        for case_index in range(1, VECTORIZED_PENALTY_BRANCH_COUNT)
    ]
    return base_penalty, gradient_values


@pytest.mark.skipif(
    gradient_source_ghx_path() is None,
    reason="Set PYGHX_GRADIENT_SOURCE_GHX to a local penalty GHX file.",
)
def test_gradient_transform_contract(tmp_path: Path) -> None:
    source_ghx_path = gradient_source_ghx_path()
    assert source_ghx_path is not None

    gradient_ghx_path = tmp_path / "definition_gradient.ghx"
    transform_penalty_graph_for_gradient(source_ghx_path, gradient_ghx_path)

    validation_result = validate_document(gradient_ghx_path)
    assert validation_result.valid is True

    inspect_summary = inspect_document(gradient_ghx_path)
    compute_input_nicknames = {
        contextual_input["nickname"]
        for contextual_input in inspect_summary["contextual_inputs"]
    }
    compute_output_names = {
        output["compute_param_name"] for output in inspect_summary["compute_contract"]["outputs"]
    }
    assert compute_input_nicknames == set(CONTEXTUAL_INPUT_NICKNAMES)
    assert compute_output_names == {"penalty", "Gradient"}


@pytest.mark.skipif(
    gradient_source_ghx_path() is None,
    reason="Set PYGHX_GRADIENT_SOURCE_GHX to a local penalty GHX file.",
)
@pytest.mark.skipif(
    not is_rhino_compute_available(),
    reason="RhinoCompute is not available on localhost:5000.",
)
def test_gradient_matches_vectorized_forward_difference_for_two_samples(tmp_path: Path) -> None:
    source_ghx_path = gradient_source_ghx_path()
    assert source_ghx_path is not None

    gradient_ghx_path = tmp_path / "definition_gradient.ghx"
    transform_penalty_graph_for_gradient(source_ghx_path, gradient_ghx_path)

    for sample_index, sample_inputs in enumerate(SAMPLE_INPUT_CASES):
        probe_ghx_path = tmp_path / f"penalty_probe_{sample_index}.ghx"
        _build_stream_filter_penalty_probe_ghx(gradient_ghx_path, probe_ghx_path)
        input_values = _build_compute_input_values(sample_inputs)

        probe_result = evaluate_document(
            probe_ghx_path,
            input_values=input_values,
            compute_url=DEFAULT_RHINO_COMPUTE_URL,
        )
        assert probe_result.success is True
        vectorized_penalty_cases = _extract_vectorized_penalty_cases(probe_result.outputs)

        gradient_result = evaluate_document(
            gradient_ghx_path,
            input_values=input_values,
            compute_url=DEFAULT_RHINO_COMPUTE_URL,
        )
        assert gradient_result.success is True

        expected_base_penalty, expected_gradient = _compute_forward_difference_from_penalty_cases(
            vectorized_penalty_cases
        )
        actual_base_penalty = _extract_scalar_output(gradient_result.outputs, "penalty")
        actual_gradient = _extract_gradient_output(gradient_result.outputs)

        assert math.isclose(
            actual_base_penalty,
            expected_base_penalty,
            rel_tol=0.0,
            abs_tol=GRADIENT_TOLERANCE,
        )
        for actual_value, expected_value in zip(actual_gradient, expected_gradient, strict=True):
            assert math.isclose(
                actual_value,
                expected_value,
                rel_tol=0.0,
                abs_tol=GRADIENT_TOLERANCE,
            )


@pytest.mark.skipif(
    gradient_source_ghx_path() is None,
    reason="Set PYGHX_GRADIENT_SOURCE_GHX to a local penalty GHX file.",
)
@pytest.mark.skipif(
    not is_rhino_compute_available(),
    reason="RhinoCompute is not available on localhost:5000.",
)
def test_gradient_one_call_reduces_rhino_compute_round_trips(tmp_path: Path) -> None:
    source_ghx_path = gradient_source_ghx_path()
    assert source_ghx_path is not None

    gradient_ghx_path = tmp_path / "definition_gradient.ghx"
    transform_penalty_graph_for_gradient(source_ghx_path, gradient_ghx_path)

    sample_inputs = SAMPLE_INPUT_CASES[1]
    input_values = _build_compute_input_values(sample_inputs)

    isolated_round_trip_milliseconds = 0.0
    for nickname in CONTEXTUAL_INPUT_NICKNAMES:
        perturbed_inputs = dict(sample_inputs)
        perturbed_inputs[nickname] = perturbed_inputs[nickname] + FINITE_DIFFERENCE_STEP
        perturbed_result = evaluate_document(
            source_ghx_path,
            input_values=_build_compute_input_values(perturbed_inputs),
            compute_url=DEFAULT_RHINO_COMPUTE_URL,
            collect_timing=True,
        )
        assert perturbed_result.success is True
        assert perturbed_result.timing is not None
        isolated_round_trip_milliseconds += perturbed_result.timing.rhino_compute_round_trip_milliseconds

    base_result = evaluate_document(
        source_ghx_path,
        input_values=input_values,
        compute_url=DEFAULT_RHINO_COMPUTE_URL,
        collect_timing=True,
    )
    assert base_result.success is True
    assert base_result.timing is not None
    isolated_round_trip_milliseconds += base_result.timing.rhino_compute_round_trip_milliseconds

    gradient_result = evaluate_document(
        gradient_ghx_path,
        input_values=input_values,
        compute_url=DEFAULT_RHINO_COMPUTE_URL,
        collect_timing=True,
    )
    assert gradient_result.success is True
    assert gradient_result.timing is not None

    assert gradient_result.timing.rhino_compute_round_trip_milliseconds < isolated_round_trip_milliseconds
