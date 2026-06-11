"""Unit tests for RhinoCompute timing breakdown."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from pyghx.compute import (
    ComputeInputValue,
    _HttpRequestTiming,
    _RequestBuildTiming,
    evaluate_document,
)
from tests.helpers import ADDITION_FIXTURE_PATH, DEFAULT_RHINO_COMPUTE_URL


def test_evaluate_document_collect_timing_includes_phase_fields() -> None:
    mocked_raw_response = {
        "pointer": "md5_test_pointer",
        "values": [
            {
                "ParamName": "Context Bake",
                "InnerTree": {
                    "0": [{"type": "System.Double", "data": "5"}],
                },
            }
        ],
    }
    mocked_http_timing = _HttpRequestTiming(
        json_serialize_milliseconds=1.5,
        wait_until_headers_milliseconds=42.0,
        read_response_body_milliseconds=0.5,
        request_payload_bytes=128,
        response_payload_bytes=64,
    )
    mocked_request_build_timing = _RequestBuildTiming(
        read_definition_milliseconds=2.0,
        base64_encode_milliseconds=3.0,
        build_input_trees_milliseconds=1.0,
    )

    with (
        patch(
            "pyghx.compute._build_request_body_with_timing",
            return_value=({"algo": "encoded", "values": []}, mocked_request_build_timing),
        ),
        patch(
            "pyghx.compute._post_grasshopper_request_with_timing",
            return_value=(mocked_raw_response, mocked_http_timing),
        ),
        patch(
            "pyghx.compute._estimate_grasshopper_server_phases",
            return_value=(10.0, 2.0),
        ),
    ):
        compute_result = evaluate_document(
            ADDITION_FIXTURE_PATH,
            input_values=[
                ComputeInputValue(nickname="X", value=2),
                ComputeInputValue(nickname="Y", value=3),
            ],
            compute_url=DEFAULT_RHINO_COMPUTE_URL,
            collect_timing=True,
            estimate_grasshopper_solve=True,
        )

    assert compute_result.success is True
    assert compute_result.timing is not None
    assert compute_result.timing.inspect_milliseconds >= 0.0
    assert compute_result.timing.preflight_milliseconds >= 0.0
    assert compute_result.timing.read_definition_milliseconds == 2.0
    assert compute_result.timing.base64_encode_milliseconds == 3.0
    assert compute_result.timing.http_wait_until_headers_milliseconds == 42.0
    assert compute_result.timing.grasshopper_solve_estimate_milliseconds == 10.0
    assert compute_result.timing.result_cache_lookup_milliseconds == 2.0
    assert compute_result.timing.definition_transfer_estimate_milliseconds == 32.0
    assert "timing" in compute_result.to_dict()
