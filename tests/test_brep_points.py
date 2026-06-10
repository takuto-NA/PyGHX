"""Inspect, validate, and compute contract tests for the Brep Points fixture."""

from __future__ import annotations

import pytest

from pyghx.compute import ComputeInputValue, _build_request_body
from pyghx.inspect import inspect_document
from pyghx.validate import validate_document
from tests.helpers import BREP_POINTS_FIXTURE_PATH


def test_brep_points_fixture_validates_without_unknown_components() -> None:
    validation_result = validate_document(BREP_POINTS_FIXTURE_PATH)
    assert validation_result.valid is True
    assert not any(
        diagnostic["code"] == "unknown_component"
        for diagnostic in validation_result.diagnostics
    )


def test_brep_points_compute_contract() -> None:
    summary = inspect_document(BREP_POINTS_FIXTURE_PATH)
    assert summary["unknown_elements"] == []
    assert summary["compute_contract"]["inputs"] == [
        {
            "nickname": "Get Point",
            "compute_param_name": "Get Point",
            "kind": "point",
            "optional": False,
            "supported": True,
        },
        {
            "nickname": "Get File Path",
            "compute_param_name": "Get File Path",
            "kind": "file_path",
            "optional": False,
            "supported": True,
        },
    ]
    output_labels = [
        context_bake_output["label"]
        for context_bake_output in summary["context_bake_outputs"]
    ]
    output_param_names = [
        context_bake_output["compute_param_name"]
        for context_bake_output in summary["context_bake_outputs"]
    ]
    assert output_labels == ["inside", "distance", "point", "normal"]
    assert output_param_names == ["Inside", "Distance", "Point", "Normal"]


def test_brep_points_file_path_and_point_input_builds_grasshopper_request_body() -> None:
    summary = inspect_document(BREP_POINTS_FIXTURE_PATH)
    request_body = _build_request_body(
        BREP_POINTS_FIXTURE_PATH,
        [
            ComputeInputValue(
                nickname="Get File Path",
                value=r"C:\models\example.stp",
                kind="file_path",
            ),
            ComputeInputValue(
                nickname="Get Point",
                value=(1.0, 2.0, 0.0),
                kind="point",
            ),
        ],
        summary,
    )
    param_name_to_data = {
        value_entry["ParamName"]: value_entry["InnerTree"]["0"][0]["data"]
        for value_entry in request_body["values"]
    }
    assert param_name_to_data["Get File Path"] == '"C:\\\\models\\\\example.stp"'
    assert param_name_to_data["Get Point"] == '{"X": 1.0, "Y": 2.0, "Z": 0.0}'


@pytest.mark.parametrize(
    "component_name",
    [
        "Brep",
        "Point",
        "Point In Brep",
        "Brep Closest Point",
        "Deconstruct Brep",
    ],
)
def test_brep_points_covers_brep_related_components(component_name: str) -> None:
    summary = inspect_document(BREP_POINTS_FIXTURE_PATH, include_objects=True)
    component_names = {
        object_entry["component_name"] for object_entry in summary["objects"]
    }
    assert component_name in component_names
