"""Operational smoke tests for KNOWN_COMPONENT_NAMES."""

from __future__ import annotations

import pytest

from pyghx.compute import ComputeInputValue, evaluate_document, extract_numeric_result
from pyghx.constants import KNOWN_COMPONENT_NAMES
from pyghx.inspect import inspect_document
from pyghx.reference import extract_patterns, load_pattern_catalog
from pyghx.validate import validate_document
from tests.component_coverage import (
    find_fixture_path_for_component,
    load_component_instances,
    public_known_component_names,
    reference_ghx_path,
    reference_known_component_names,
    reference_only_known_component_names,
    uncovered_known_component_names,
)
from tests.helpers import (
    ADDITION_FIXTURE_PATH,
    DEFAULT_RHINO_COMPUTE_URL,
    is_rhino_compute_available,
)

PUBLIC_KNOWN_COMPONENT_NAMES = sorted(public_known_component_names())
REFERENCE_ONLY_KNOWN_COMPONENT_NAMES = sorted(
    KNOWN_COMPONENT_NAMES - public_known_component_names()
)
PUBLIC_COMPUTE_READY_COMPONENT_NAMES = ("Get Number", "Addition", "Context Bake")


def test_known_component_registry_matches_constants() -> None:
    assert "LoggerManager" in KNOWN_COMPONENT_NAMES
    assert "Vector XYZ" in KNOWN_COMPONENT_NAMES
    assert len(KNOWN_COMPONENT_NAMES) >= len(PUBLIC_KNOWN_COMPONENT_NAMES)


@pytest.mark.parametrize("component_name", PUBLIC_KNOWN_COMPONENT_NAMES)
def test_public_known_component_load_inspect_validate(component_name: str) -> None:
    fixture_path = find_fixture_path_for_component(component_name)
    assert fixture_path is not None

    document, instances = load_component_instances(fixture_path, component_name)
    assert instances
    assert component_name not in document.unknown_component_names

    for instance in instances:
        assert instance.instance_guid is not None

    validation_result = validate_document(fixture_path)
    assert validation_result.valid is True

    summary = inspect_document(fixture_path, include_objects=True)
    summary_component_names = {
        object_entry["component_name"] for object_entry in summary["objects"]
    }
    assert component_name in summary_component_names


def test_all_known_components_have_fixture_coverage() -> None:
    missing_component_names = uncovered_known_component_names()
    if missing_component_names and reference_ghx_path() is None:
        public_only = sorted(public_known_component_names())
        pytest.skip(
            "Some KNOWN components require PYGHX_REFERENCE_GHX for coverage: "
            + ", ".join(sorted(missing_component_names))
            + ". Public coverage: "
            + ", ".join(public_only)
        )

    assert not missing_component_names


@pytest.mark.private_reference
def test_reference_only_known_components_are_present() -> None:
    reference_path = reference_ghx_path()
    if reference_path is None:
        pytest.skip("PYGHX_REFERENCE_GHX is not set.")

    missing_component_names = (
        reference_only_known_component_names() - reference_known_component_names()
    )
    assert not missing_component_names


@pytest.mark.private_reference
@pytest.mark.parametrize("component_name", REFERENCE_ONLY_KNOWN_COMPONENT_NAMES)
def test_reference_known_component_load_inspect(component_name: str) -> None:
    reference_path = reference_ghx_path()
    if reference_path is None:
        pytest.skip("PYGHX_REFERENCE_GHX is not set.")

    document, instances = load_component_instances(reference_path, component_name)
    assert instances, f"{component_name!r} was not found in the reference GHX."
    assert component_name not in document.unknown_component_names

    for instance in instances:
        assert instance.instance_guid is not None

    summary = inspect_document(reference_path, include_objects=True)
    matching_objects = [
        object_entry
        for object_entry in summary["objects"]
        if object_entry["component_name"] == component_name
    ]
    assert matching_objects


@pytest.mark.private_reference
def test_reference_ghx_validates() -> None:
    reference_path = reference_ghx_path()
    if reference_path is None:
        pytest.skip("PYGHX_REFERENCE_GHX is not set.")

    validation_result = validate_document(reference_path)
    assert validation_result.valid is True


@pytest.mark.integration
def test_public_compute_ready_components_execute_on_rhino_compute() -> None:
    if not is_rhino_compute_available():
        pytest.skip("RhinoCompute is not available at http://localhost:5000/")

    for component_name in PUBLIC_COMPUTE_READY_COMPONENT_NAMES:
        _, instances = load_component_instances(ADDITION_FIXTURE_PATH, component_name)
        assert instances, f"{component_name!r} is missing from addition.ghx."

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


@pytest.mark.private_reference
@pytest.mark.integration
def test_reference_compute_ready_patterns_execute_on_rhino_compute(tmp_path) -> None:
    reference_path = reference_ghx_path()
    if reference_path is None:
        pytest.skip("PYGHX_REFERENCE_GHX is not set.")

    if not is_rhino_compute_available():
        pytest.skip("RhinoCompute is not available at http://localhost:5000/")

    catalog_path = extract_patterns(reference_path, output_dir=tmp_path / "patterns")
    catalog = load_pattern_catalog(catalog_path)
    compute_ready_patterns = [
        pattern for pattern in catalog.patterns if pattern.rhino_compute_ready
    ]
    assert compute_ready_patterns

    pattern_input_values = {
        "get_number_to_number_RS": (
            [ComputeInputValue(nickname="RS", value=1.0)],
            1.0,
        ),
        "vector_xyz_X_Y_Z": (
            [
                ComputeInputValue(nickname="X", value=1),
                ComputeInputValue(nickname="Y", value=2),
                ComputeInputValue(nickname="Z", value=3),
            ],
            None,
        ),
        "vector_xyz_RX_RY_RZ": (
            [
                ComputeInputValue(nickname="RX", value=4),
                ComputeInputValue(nickname="RY", value=5),
                ComputeInputValue(nickname="RZ", value=6),
            ],
            None,
        ),
    }

    for pattern_entry in compute_ready_patterns:
        pattern_ghx_path = catalog_path.parent / pattern_entry.pattern_ghx
        input_values, expected_numeric_result = pattern_input_values[pattern_entry.pattern_id]

        compute_result = evaluate_document(
            pattern_ghx_path,
            input_values=input_values,
            compute_url=DEFAULT_RHINO_COMPUTE_URL,
        )
        assert compute_result.success is True, (
            f"RhinoCompute failed for {pattern_entry.pattern_id}: "
            + "; ".join(diagnostic["message"] for diagnostic in compute_result.diagnostics)
        )
        if expected_numeric_result is not None:
            assert extract_numeric_result(compute_result.outputs) == expected_numeric_result
