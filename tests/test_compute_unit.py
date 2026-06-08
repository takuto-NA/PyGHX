"""Unit tests for RhinoCompute response normalization."""

from __future__ import annotations

from pyghx.compute import _normalize_outputs, extract_numeric_result


def test_normalize_outputs_maps_compute_param_name_to_label() -> None:
    raw_response = {
        "values": [
            {
                "ParamName": "Content",
                "InnerTree": {
                    "{0;0}": [{"data": "5"}],
                },
            }
        ]
    }
    summary = {
        "compute_contract": {
            "outputs": [
                {
                    "label": "addition",
                    "compute_param_name": "Content",
                    "source_component_name": "Addition",
                }
            ]
        }
    }
    normalized_outputs = _normalize_outputs(raw_response, summary)
    assert normalized_outputs == {"addition": [5]}


def test_extract_numeric_result_reads_labeled_output() -> None:
    outputs = {"addition": [5]}
    assert extract_numeric_result(outputs) == 5
