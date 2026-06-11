"""Evaluate GHX definitions through RhinoCompute."""

from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pyghx.compute_encoding import build_inner_tree_data_entries
from pyghx.constants import (
    CONTEXT_BAKE_COMPONENT_NAME,
    DEFAULT_RHINO_COMPUTE_URL,
    SUPPORTED_RHINO_COMPUTE_INPUT_KINDS,
)
from pyghx.preflight import (
    blocking_preflight_diagnostics,
    build_preflight_diagnostics,
    has_blocking_preflight_errors,
)
from pyghx.inspect import inspect_document

RHINO_COMPUTE_BRANCH_KEY = "0"
GRASSHOPPER_SOLVE_PROBE_INPUT_DELTA = 1e-6


@dataclass(frozen=True)
class ComputeTimingBreakdown:
    """Per-phase timings for one RhinoCompute evaluation."""

    inspect_milliseconds: float
    preflight_milliseconds: float
    read_definition_milliseconds: float
    base64_encode_milliseconds: float
    build_input_trees_milliseconds: float
    json_serialize_milliseconds: float
    http_wait_until_headers_milliseconds: float
    http_read_response_body_milliseconds: float
    normalize_outputs_milliseconds: float
    request_payload_bytes: int
    response_payload_bytes: int
    response_pointer: str | None
    grasshopper_solve_estimate_milliseconds: float | None = None
    result_cache_lookup_milliseconds: float | None = None
    definition_transfer_estimate_milliseconds: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "inspect_milliseconds": self.inspect_milliseconds,
            "preflight_milliseconds": self.preflight_milliseconds,
            "read_definition_milliseconds": self.read_definition_milliseconds,
            "base64_encode_milliseconds": self.base64_encode_milliseconds,
            "build_input_trees_milliseconds": self.build_input_trees_milliseconds,
            "json_serialize_milliseconds": self.json_serialize_milliseconds,
            "http_wait_until_headers_milliseconds": self.http_wait_until_headers_milliseconds,
            "http_read_response_body_milliseconds": self.http_read_response_body_milliseconds,
            "normalize_outputs_milliseconds": self.normalize_outputs_milliseconds,
            "request_payload_bytes": self.request_payload_bytes,
            "response_payload_bytes": self.response_payload_bytes,
            "response_pointer": self.response_pointer,
            "grasshopper_solve_estimate_milliseconds": self.grasshopper_solve_estimate_milliseconds,
            "result_cache_lookup_milliseconds": self.result_cache_lookup_milliseconds,
            "definition_transfer_estimate_milliseconds": self.definition_transfer_estimate_milliseconds,
            "client_total_milliseconds": self.client_total_milliseconds,
            "rhino_compute_round_trip_milliseconds": self.rhino_compute_round_trip_milliseconds,
        }

    @property
    def client_total_milliseconds(self) -> float:
        return (
            self.inspect_milliseconds
            + self.preflight_milliseconds
            + self.read_definition_milliseconds
            + self.base64_encode_milliseconds
            + self.build_input_trees_milliseconds
            + self.json_serialize_milliseconds
            + self.http_wait_until_headers_milliseconds
            + self.http_read_response_body_milliseconds
            + self.normalize_outputs_milliseconds
        )

    @property
    def rhino_compute_round_trip_milliseconds(self) -> float:
        return (
            self.json_serialize_milliseconds
            + self.http_wait_until_headers_milliseconds
            + self.http_read_response_body_milliseconds
        )


@dataclass(frozen=True)
class ComputeInputValue:
    """One contextual input value for RhinoCompute evaluation."""

    nickname: str
    value: Any
    kind: str = "number"


@dataclass(frozen=True)
class ComputeResult:
    """Normalized RhinoCompute evaluation result."""

    success: bool
    outputs: dict[str, Any]
    raw_response: dict[str, Any] | None
    diagnostics: tuple[dict[str, str], ...]
    timing: ComputeTimingBreakdown | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "success": self.success,
            "outputs": self.outputs,
            "raw_response": self.raw_response,
            "diagnostics": list(self.diagnostics),
        }
        if self.timing is not None:
            payload["timing"] = self.timing.to_dict()
        return payload


def evaluate_document(
    source_path: Path | str,
    input_values: list[ComputeInputValue],
    compute_url: str = DEFAULT_RHINO_COMPUTE_URL,
    collect_timing: bool = False,
    estimate_grasshopper_solve: bool = False,
) -> ComputeResult:
    """Evaluate a GHX definition on RhinoCompute."""
    path = Path(source_path)
    inspect_started_at = time.perf_counter()
    summary = inspect_document(path)
    inspect_milliseconds = _elapsed_milliseconds_since(inspect_started_at)
    diagnostics: list[dict[str, str]] = []
    coalesced_input_values = _coalesce_input_values(input_values, summary)
    unsupported_inputs = _find_unsupported_inputs(summary, coalesced_input_values)
    if unsupported_inputs:
        for unsupported_input in unsupported_inputs:
            diagnostics.append(
                {
                    "level": "error",
                    "code": "unsupported_input_kind",
                    "message": (
                        f"Input {unsupported_input.nickname!r} has kind "
                        f"{unsupported_input.kind!r}, which is not supported for RhinoCompute "
                        "execution in this MVP."
                    ),
                }
            )
        return ComputeResult(
            success=False,
            outputs={},
            raw_response=None,
            diagnostics=tuple(diagnostics),
            timing=_empty_timing(inspect_milliseconds) if collect_timing else None,
        )

    missing_nicknames = _find_missing_input_nicknames(summary, coalesced_input_values)
    if missing_nicknames:
        diagnostics.append(
            {
                "level": "error",
                "code": "missing_contextual_inputs",
                "message": "Missing contextual inputs: " + ", ".join(missing_nicknames),
            }
        )
        return ComputeResult(
            success=False,
            outputs={},
            raw_response=None,
            diagnostics=tuple(diagnostics),
            timing=_empty_timing(inspect_milliseconds) if collect_timing else None,
        )

    preflight_started_at = time.perf_counter()
    preflight_diagnostics = build_preflight_diagnostics(path)
    preflight_milliseconds = _elapsed_milliseconds_since(preflight_started_at)
    if has_blocking_preflight_errors(preflight_diagnostics):
        diagnostics.extend(blocking_preflight_diagnostics(preflight_diagnostics))
        diagnostics.append(
            {
                "level": "error",
                "code": "ghx_validation_error",
                "message": (
                    "GHX validation failed before RhinoCompute execution. "
                    "Run `pyghx validate` for the full diagnostic list."
                ),
            }
        )
        return ComputeResult(
            success=False,
            outputs={},
            raw_response=None,
            diagnostics=tuple(diagnostics),
            timing=_partial_timing(
                inspect_milliseconds=inspect_milliseconds,
                preflight_milliseconds=preflight_milliseconds,
            )
            if collect_timing
            else None,
        )

    request_body, request_build_timing = _build_request_body_with_timing(
        path,
        coalesced_input_values,
        summary,
    )
    try:
        raw_response, http_timing = _post_grasshopper_request_with_timing(
            compute_url,
            request_body,
        )
    except urllib.error.HTTPError as http_error:
        error_body = http_error.read().decode("utf-8", errors="replace")
        diagnostics.append(
            {
                "level": "error",
                "code": "rhino_compute_http_error",
                "message": (
                    f"HTTP {http_error.code}: {error_body or http_error.reason}. "
                    "Run `pyghx validate` to check GHX structure before retrying."
                ),
            }
        )
        return ComputeResult(
            success=False,
            outputs={},
            raw_response=None,
            diagnostics=tuple(diagnostics),
            timing=_partial_timing(
                inspect_milliseconds=inspect_milliseconds,
                preflight_milliseconds=preflight_milliseconds,
                request_build_timing=request_build_timing,
            )
            if collect_timing
            else None,
        )
    except urllib.error.URLError as url_error:
        diagnostics.append(
            {
                "level": "error",
                "code": "rhino_compute_unreachable",
                "message": str(url_error.reason if hasattr(url_error, "reason") else url_error),
            }
        )
        return ComputeResult(
            success=False,
            outputs={},
            raw_response=None,
            diagnostics=tuple(diagnostics),
            timing=_partial_timing(
                inspect_milliseconds=inspect_milliseconds,
                preflight_milliseconds=preflight_milliseconds,
                request_build_timing=request_build_timing,
            )
            if collect_timing
            else None,
        )

    normalize_started_at = time.perf_counter()
    normalized_outputs = _normalize_outputs(raw_response, summary)
    normalize_outputs_milliseconds = _elapsed_milliseconds_since(normalize_started_at)

    timing: ComputeTimingBreakdown | None = None
    if collect_timing:
        grasshopper_solve_estimate_milliseconds = None
        result_cache_lookup_milliseconds = None
        definition_transfer_estimate_milliseconds = None
        response_pointer = raw_response.get("pointer")
        if estimate_grasshopper_solve and response_pointer:
            (
                grasshopper_solve_estimate_milliseconds,
                result_cache_lookup_milliseconds,
            ) = _estimate_grasshopper_server_phases(
                compute_url=compute_url,
                response_pointer=response_pointer,
                input_values=coalesced_input_values,
                summary=summary,
            )
            if grasshopper_solve_estimate_milliseconds is not None:
                definition_transfer_estimate_milliseconds = max(
                    0.0,
                    http_timing.wait_until_headers_milliseconds
                    - grasshopper_solve_estimate_milliseconds,
                )

        timing = ComputeTimingBreakdown(
            inspect_milliseconds=inspect_milliseconds,
            preflight_milliseconds=preflight_milliseconds,
            read_definition_milliseconds=request_build_timing.read_definition_milliseconds,
            base64_encode_milliseconds=request_build_timing.base64_encode_milliseconds,
            build_input_trees_milliseconds=request_build_timing.build_input_trees_milliseconds,
            json_serialize_milliseconds=http_timing.json_serialize_milliseconds,
            http_wait_until_headers_milliseconds=http_timing.wait_until_headers_milliseconds,
            http_read_response_body_milliseconds=http_timing.read_response_body_milliseconds,
            normalize_outputs_milliseconds=normalize_outputs_milliseconds,
            request_payload_bytes=http_timing.request_payload_bytes,
            response_payload_bytes=http_timing.response_payload_bytes,
            response_pointer=raw_response.get("pointer"),
            grasshopper_solve_estimate_milliseconds=grasshopper_solve_estimate_milliseconds,
            result_cache_lookup_milliseconds=result_cache_lookup_milliseconds,
            definition_transfer_estimate_milliseconds=definition_transfer_estimate_milliseconds,
        )

    return ComputeResult(
        success=True,
        outputs=normalized_outputs,
        raw_response=raw_response,
        diagnostics=tuple(diagnostics),
        timing=timing,
    )


def _coalesce_input_values(
    input_values: list[ComputeInputValue],
    summary: dict[str, Any],
) -> list[ComputeInputValue]:
    """Merge repeated point inputs for the same nickname into one list value."""
    nickname_to_kind = _build_nickname_to_kind_map(summary)
    merged_values: dict[str, ComputeInputValue] = {}

    for input_value in input_values:
        resolved_kind = nickname_to_kind.get(input_value.nickname, input_value.kind)
        existing_value = merged_values.get(input_value.nickname)
        if existing_value is None:
            merged_values[input_value.nickname] = ComputeInputValue(
                nickname=input_value.nickname,
                value=input_value.value,
                kind=resolved_kind,
            )
            continue

        if resolved_kind != "point":
            merged_values[input_value.nickname] = input_value
            continue

        merged_points = _normalize_point_value_list(existing_value.value)
        merged_points.extend(_normalize_point_value_list(input_value.value))
        merged_values[input_value.nickname] = ComputeInputValue(
            nickname=input_value.nickname,
            value=merged_points,
            kind="point",
        )

    return list(merged_values.values())


def _normalize_point_value_list(value: Any) -> list[tuple[float, float, float]]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return [value]
    raise ValueError(f"Unsupported point value for coalescing: {value!r}.")


def _build_nickname_to_kind_map(summary: dict[str, Any]) -> dict[str, str]:
    return {
        contextual_input["nickname"]: contextual_input["kind"]
        for contextual_input in summary.get("contextual_inputs", [])
        if contextual_input.get("nickname")
    }


def _find_unsupported_inputs(
    summary: dict[str, Any],
    input_values: list[ComputeInputValue],
) -> list[ComputeInputValue]:
    nickname_to_kind = _build_nickname_to_kind_map(summary)
    unsupported: list[ComputeInputValue] = []
    for input_value in input_values:
        contextual_kind = nickname_to_kind.get(input_value.nickname, input_value.kind)
        if contextual_kind not in SUPPORTED_RHINO_COMPUTE_INPUT_KINDS:
            unsupported.append(
                ComputeInputValue(
                    nickname=input_value.nickname,
                    value=input_value.value,
                    kind=contextual_kind,
                )
            )
    return unsupported


def _find_missing_input_nicknames(
    summary: dict[str, Any],
    input_values: list[ComputeInputValue],
) -> list[str]:
    required_nicknames = {
        contextual_input["nickname"]
        for contextual_input in summary.get("contextual_inputs", [])
        if contextual_input.get("nickname") and contextual_input.get("optional") is False
    }
    provided_nicknames = {input_value.nickname for input_value in input_values}
    return sorted(required_nicknames - provided_nicknames)


@dataclass(frozen=True)
class _RequestBuildTiming:
    read_definition_milliseconds: float
    base64_encode_milliseconds: float
    build_input_trees_milliseconds: float


@dataclass(frozen=True)
class _HttpRequestTiming:
    json_serialize_milliseconds: float
    wait_until_headers_milliseconds: float
    read_response_body_milliseconds: float
    request_payload_bytes: int
    response_payload_bytes: int


def _elapsed_milliseconds_since(started_at: float) -> float:
    return (time.perf_counter() - started_at) * 1000


def _empty_timing(inspect_milliseconds: float) -> ComputeTimingBreakdown:
    return ComputeTimingBreakdown(
        inspect_milliseconds=inspect_milliseconds,
        preflight_milliseconds=0.0,
        read_definition_milliseconds=0.0,
        base64_encode_milliseconds=0.0,
        build_input_trees_milliseconds=0.0,
        json_serialize_milliseconds=0.0,
        http_wait_until_headers_milliseconds=0.0,
        http_read_response_body_milliseconds=0.0,
        normalize_outputs_milliseconds=0.0,
        request_payload_bytes=0,
        response_payload_bytes=0,
        response_pointer=None,
    )


def _partial_timing(
    inspect_milliseconds: float,
    preflight_milliseconds: float = 0.0,
    request_build_timing: _RequestBuildTiming | None = None,
    http_timing: _HttpRequestTiming | None = None,
    normalize_outputs_milliseconds: float = 0.0,
) -> ComputeTimingBreakdown:
    return ComputeTimingBreakdown(
        inspect_milliseconds=inspect_milliseconds,
        preflight_milliseconds=preflight_milliseconds,
        read_definition_milliseconds=(
            request_build_timing.read_definition_milliseconds
            if request_build_timing is not None
            else 0.0
        ),
        base64_encode_milliseconds=(
            request_build_timing.base64_encode_milliseconds
            if request_build_timing is not None
            else 0.0
        ),
        build_input_trees_milliseconds=(
            request_build_timing.build_input_trees_milliseconds
            if request_build_timing is not None
            else 0.0
        ),
        json_serialize_milliseconds=(
            http_timing.json_serialize_milliseconds if http_timing is not None else 0.0
        ),
        http_wait_until_headers_milliseconds=(
            http_timing.wait_until_headers_milliseconds if http_timing is not None else 0.0
        ),
        http_read_response_body_milliseconds=(
            http_timing.read_response_body_milliseconds if http_timing is not None else 0.0
        ),
        normalize_outputs_milliseconds=normalize_outputs_milliseconds,
        request_payload_bytes=http_timing.request_payload_bytes if http_timing is not None else 0,
        response_payload_bytes=http_timing.response_payload_bytes if http_timing is not None else 0,
        response_pointer=None,
    )


def _build_request_body(
    path: Path,
    input_values: list[ComputeInputValue],
    summary: dict[str, Any],
) -> dict[str, Any]:
    request_body, _request_build_timing = _build_request_body_with_timing(
        path,
        input_values,
        summary,
    )
    return request_body


def _build_request_body_with_timing(
    path: Path,
    input_values: list[ComputeInputValue],
    summary: dict[str, Any],
) -> tuple[dict[str, Any], _RequestBuildTiming]:
    read_started_at = time.perf_counter()
    definition_text = path.read_text(encoding="utf-8-sig")
    read_definition_milliseconds = _elapsed_milliseconds_since(read_started_at)

    encode_started_at = time.perf_counter()
    encoded_definition = base64.b64encode(definition_text.encode("utf-8")).decode("utf-8")
    base64_encode_milliseconds = _elapsed_milliseconds_since(encode_started_at)

    build_trees_started_at = time.perf_counter()
    values = [_build_data_tree(input_value, summary) for input_value in input_values]
    build_input_trees_milliseconds = _elapsed_milliseconds_since(build_trees_started_at)

    request_body = {
        "algo": encoded_definition,
        "values": values,
    }
    request_build_timing = _RequestBuildTiming(
        read_definition_milliseconds=read_definition_milliseconds,
        base64_encode_milliseconds=base64_encode_milliseconds,
        build_input_trees_milliseconds=build_input_trees_milliseconds,
    )
    return request_body, request_build_timing


def _build_pointer_request_body(
    response_pointer: str,
    input_values: list[ComputeInputValue],
    summary: dict[str, Any],
) -> dict[str, Any]:
    return {
        "pointer": response_pointer,
        "values": [_build_data_tree(input_value, summary) for input_value in input_values],
    }


def _probe_input_values_for_solve_estimate(
    input_values: list[ComputeInputValue],
    summary: dict[str, Any],
) -> list[ComputeInputValue]:
    nickname_to_kind = _build_nickname_to_kind_map(summary)
    for input_value in input_values:
        contextual_kind = nickname_to_kind.get(input_value.nickname, input_value.kind)
        if contextual_kind != "number":
            continue
        if not isinstance(input_value.value, (int, float)):
            continue
        return [
            ComputeInputValue(
                nickname=probed_input_value.nickname,
                value=(
                    float(probed_input_value.value) + GRASSHOPPER_SOLVE_PROBE_INPUT_DELTA
                    if probed_input_value.nickname == input_value.nickname
                    else probed_input_value.value
                ),
                kind=probed_input_value.kind,
            )
            for probed_input_value in input_values
        ]
    return list(input_values)


def _estimate_grasshopper_server_phases(
    compute_url: str,
    response_pointer: str,
    input_values: list[ComputeInputValue],
    summary: dict[str, Any],
) -> tuple[float | None, float | None]:
    """Estimate Grasshopper solve vs result-cache lookup using pointer follow-up requests."""
    cache_lookup_request_body = _build_pointer_request_body(
        response_pointer,
        input_values,
        summary,
    )
    try:
        _, cache_lookup_http_timing = _post_grasshopper_request_with_timing(
            compute_url,
            cache_lookup_request_body,
        )
    except (urllib.error.HTTPError, urllib.error.URLError):
        return None, None

    probe_input_values = _probe_input_values_for_solve_estimate(input_values, summary)
    solve_probe_request_body = _build_pointer_request_body(
        response_pointer,
        probe_input_values,
        summary,
    )
    try:
        _, solve_probe_http_timing = _post_grasshopper_request_with_timing(
            compute_url,
            solve_probe_request_body,
        )
    except (urllib.error.HTTPError, urllib.error.URLError):
        return None, cache_lookup_http_timing.wait_until_headers_milliseconds

    return (
        solve_probe_http_timing.wait_until_headers_milliseconds,
        cache_lookup_http_timing.wait_until_headers_milliseconds,
    )


def _resolve_compute_param_name(input_value: ComputeInputValue, summary: dict[str, Any]) -> str:
    for contextual_input in summary.get("contextual_inputs", []):
        if contextual_input.get("nickname") != input_value.nickname:
            continue
        compute_param_name = contextual_input.get("compute_param_name")
        if compute_param_name:
            return compute_param_name
    return input_value.nickname


def _resolve_input_kind(input_value: ComputeInputValue, summary: dict[str, Any]) -> str:
    nickname_to_kind = _build_nickname_to_kind_map(summary)
    return nickname_to_kind.get(input_value.nickname, input_value.kind)


def _build_data_tree(input_value: ComputeInputValue, summary: dict[str, Any]) -> dict[str, Any]:
    input_kind = _resolve_input_kind(input_value, summary)
    branch_entries = build_inner_tree_data_entries(input_kind, input_value.value)
    return {
        "ParamName": _resolve_compute_param_name(input_value, summary),
        "InnerTree": {
            RHINO_COMPUTE_BRANCH_KEY: branch_entries,
        },
    }


def _post_grasshopper_request(compute_url: str, request_body: dict[str, Any]) -> dict[str, Any]:
    raw_response, _http_timing = _post_grasshopper_request_with_timing(compute_url, request_body)
    return raw_response


def _post_grasshopper_request_with_timing(
    compute_url: str,
    request_body: dict[str, Any],
) -> tuple[dict[str, Any], _HttpRequestTiming]:
    normalized_url = compute_url.rstrip("/") + "/grasshopper"

    serialize_started_at = time.perf_counter()
    request_data = json.dumps(request_body).encode("utf-8")
    json_serialize_milliseconds = _elapsed_milliseconds_since(serialize_started_at)

    request = urllib.request.Request(
        normalized_url,
        data=request_data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    wait_until_headers_started_at = time.perf_counter()
    with urllib.request.urlopen(request, timeout=120) as response:
        wait_until_headers_milliseconds = _elapsed_milliseconds_since(wait_until_headers_started_at)
        read_response_started_at = time.perf_counter()
        response_bytes = response.read()
        read_response_body_milliseconds = _elapsed_milliseconds_since(read_response_started_at)

    response_text = response_bytes.decode("utf-8")
    http_timing = _HttpRequestTiming(
        json_serialize_milliseconds=json_serialize_milliseconds,
        wait_until_headers_milliseconds=wait_until_headers_milliseconds,
        read_response_body_milliseconds=read_response_body_milliseconds,
        request_payload_bytes=len(request_data),
        response_payload_bytes=len(response_bytes),
    )
    return json.loads(response_text), http_timing


def _normalize_outputs(
    raw_response: dict[str, Any],
    summary: dict[str, Any],
) -> dict[str, Any]:
    normalized_by_param_name: dict[str, list[Any]] = {}
    for response_value in raw_response.get("values", []):
        parameter_name = response_value.get("ParamName")
        if parameter_name is None:
            continue
        normalized_by_param_name[parameter_name] = _extract_inner_tree_values(response_value)

    normalized_outputs: dict[str, Any] = {}
    compute_outputs = summary.get("compute_contract", {}).get("outputs", [])
    for compute_output in compute_outputs:
        output_label = compute_output["label"]
        compute_param_name = compute_output["compute_param_name"]
        if compute_param_name not in normalized_by_param_name:
            continue
        normalized_outputs[output_label] = normalized_by_param_name[compute_param_name]

    if normalized_outputs:
        return normalized_outputs

    legacy_output_names = [
        context_bake_output.get("nickname") or CONTEXT_BAKE_COMPONENT_NAME
        for context_bake_output in summary.get("context_bake_outputs", [])
    ]
    if not legacy_output_names:
        legacy_output_names = [CONTEXT_BAKE_COMPONENT_NAME]

    fallback_outputs = dict(normalized_by_param_name)
    if len(fallback_outputs) == 1 and len(legacy_output_names) == 1:
        only_key = next(iter(fallback_outputs))
        if only_key != legacy_output_names[0]:
            fallback_outputs[legacy_output_names[0]] = fallback_outputs.pop(only_key)
    return fallback_outputs


def _extract_inner_tree_values(response_value: dict[str, Any]) -> list[Any]:
    extracted_values: list[Any] = []
    inner_tree = response_value.get("InnerTree", {})
    for branch_values in inner_tree.values():
        for branch_entry in branch_values:
            extracted_values.append(_normalize_branch_data(branch_entry.get("data")))
    return extracted_values


def _normalize_branch_data(raw_data: Any) -> Any:
    if raw_data is None:
        return None
    if isinstance(raw_data, (int, float, bool)):
        return raw_data
    if isinstance(raw_data, str):
        stripped = raw_data.strip()
        try:
            if stripped.startswith("{") or stripped.startswith('"'):
                return json.loads(stripped)
            if "." in stripped or "e" in stripped.lower():
                return float(stripped)
            return int(stripped)
        except (ValueError, json.JSONDecodeError):
            return raw_data
    return raw_data


def extract_numeric_result(outputs: dict[str, Any], parameter_name: str = "Context Bake") -> float | int | None:
    """Extract the first numeric value from a normalized output parameter."""
    if parameter_name not in outputs:
        for output_values in outputs.values():
            numeric_value = _first_numeric_value(output_values)
            if numeric_value is not None:
                return numeric_value
        return None
    return _first_numeric_value(outputs[parameter_name])


def _first_numeric_value(output_values: list[Any]) -> float | int | None:
    for output_value in output_values:
        if isinstance(output_value, (int, float)):
            return output_value
    return None
