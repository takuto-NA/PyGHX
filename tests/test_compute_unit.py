"""Unit tests for RhinoCompute response normalization."""

from __future__ import annotations

from pyghx.compute import _normalize_outputs, extract_numeric_result


def test_normalize_outputs_reads_all_inner_tree_paths() -> None:
    raw_response = {
        "values": [
            {
                "ParamName": "Context Bake",
                "InnerTree": {
                    "{0;0}": [{"data": "5"}],
                },
            }
        ]
    }
    summary = {
        "context_bake_outputs": [
            {
                "nickname": "Context Bake",
            }
        ]
    }
    normalized_outputs = _normalize_outputs(raw_response, summary)
    assert normalized_outputs["Context Bake"] == [5]


def test_extract_numeric_result_prefers_named_output() -> None:
    outputs = {"Context Bake": [5]}
    assert extract_numeric_result(outputs) == 5
