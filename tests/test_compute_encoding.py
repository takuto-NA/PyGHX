"""Unit tests for RhinoCompute input encoding."""

from __future__ import annotations

import json

import pytest

from pyghx.compute import ComputeInputValue, _build_data_tree
from pyghx.compute_encoding import (
    build_inner_tree_data_entries,
    encode_number_parameter_for_grasshopper,
    encode_point3d_parameter_for_grasshopper,
    encode_text_parameter_for_grasshopper,
    parse_point3d_coordinates,
)


def test_encode_point3d_parameter_matches_grasshopper_json_string() -> None:
    encoded_value = encode_point3d_parameter_for_grasshopper(30.0, 0.0, 0.0)
    assert encoded_value == json.dumps({"X": 30.0, "Y": 0.0, "Z": 0.0})


def test_encode_text_parameter_uses_json_dumps_for_windows_paths() -> None:
    encoded_value = encode_text_parameter_for_grasshopper(r"C:\Users\owner\run_file")
    assert encoded_value == json.dumps(r"C:\Users\owner\run_file")
    assert encoded_value.startswith('"')
    assert encoded_value.endswith('"')
    assert encoded_value != r"C:\Users\owner\run_file"


def test_encode_number_parameter_stringifies_numeric_value() -> None:
    assert encode_number_parameter_for_grasshopper(5) == "5"
    assert encode_number_parameter_for_grasshopper(2.5) == "2.5"


def test_parse_point3d_coordinates_accepts_comma_separated_values() -> None:
    assert parse_point3d_coordinates("1,2,3") == (1.0, 2.0, 3.0)
    assert parse_point3d_coordinates("1.5, 2.5 , 0") == (1.5, 2.5, 0.0)


def test_parse_point3d_coordinates_rejects_invalid_input() -> None:
    with pytest.raises(ValueError):
        parse_point3d_coordinates("1,2")


def test_build_inner_tree_data_entries_for_point_list() -> None:
    entries = build_inner_tree_data_entries(
        kind="point",
        value=[
            (1.0, 2.0, 3.0),
            (4.0, 5.0, 6.0),
        ],
    )
    assert entries == [
        {"data": encode_point3d_parameter_for_grasshopper(1.0, 2.0, 3.0)},
        {"data": encode_point3d_parameter_for_grasshopper(4.0, 5.0, 6.0)},
    ]


def test_build_data_tree_uses_compute_param_name_from_summary() -> None:
    summary = {
        "contextual_inputs": [
            {
                "nickname": "X",
                "compute_param_name": "X",
                "kind": "number",
            }
        ]
    }
    data_tree = _build_data_tree(
        ComputeInputValue(nickname="X", value=2),
        summary,
    )
    assert data_tree["ParamName"] == "X"
    assert data_tree["InnerTree"]["0"] == [{"data": "2"}]


def test_build_data_tree_encodes_single_point_as_json_string() -> None:
    summary = {
        "contextual_inputs": [
            {
                "nickname": "Get Point",
                "compute_param_name": "Get Point",
                "kind": "point",
            }
        ]
    }
    data_tree = _build_data_tree(
        ComputeInputValue(
            nickname="Get Point",
            value=(1.0, 2.0, 0.0),
            kind="point",
        ),
        summary,
    )
    assert data_tree["ParamName"] == "Get Point"
    assert data_tree["InnerTree"]["0"] == [
        {"data": encode_point3d_parameter_for_grasshopper(1.0, 2.0, 0.0)}
    ]
