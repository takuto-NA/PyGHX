"""Evaluate GHX definitions through RhinoCompute."""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pyghx.constants import (
    CONTEXT_BAKE_COMPONENT_NAME,
    DEFAULT_RHINO_COMPUTE_URL,
    SUPPORTED_RHINO_COMPUTE_INPUT_KINDS,
)
from pyghx.inspect import inspect_document


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "outputs": self.outputs,
            "raw_response": self.raw_response,
            "diagnostics": list(self.diagnostics),
        }


def evaluate_document(
    source_path: Path | str,
    input_values: list[ComputeInputValue],
    compute_url: str = DEFAULT_RHINO_COMPUTE_URL,
) -> ComputeResult:
    """Evaluate a GHX definition on RhinoCompute."""
    path = Path(source_path)
    summary = inspect_document(path)
    diagnostics: list[dict[str, str]] = []
    unsupported_inputs = _find_unsupported_inputs(summary, input_values)
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
        )

    missing_nicknames = _find_missing_input_nicknames(summary, input_values)
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
        )

    request_body = _build_request_body(path, input_values)
    try:
        raw_response = _post_grasshopper_request(compute_url, request_body)
    except urllib.error.HTTPError as http_error:
        error_body = http_error.read().decode("utf-8", errors="replace")
        diagnostics.append(
            {
                "level": "error",
                "code": "rhino_compute_http_error",
                "message": f"HTTP {http_error.code}: {error_body or http_error.reason}",
            }
        )
        return ComputeResult(
            success=False,
            outputs={},
            raw_response=None,
            diagnostics=tuple(diagnostics),
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
        )

    normalized_outputs = _normalize_outputs(raw_response, summary)
    return ComputeResult(
        success=True,
        outputs=normalized_outputs,
        raw_response=raw_response,
        diagnostics=tuple(diagnostics),
    )


def _find_unsupported_inputs(
    summary: dict[str, Any],
    input_values: list[ComputeInputValue],
) -> list[ComputeInputValue]:
    nickname_to_kind = {
        contextual_input["nickname"]: contextual_input["kind"]
        for contextual_input in summary.get("contextual_inputs", [])
        if contextual_input.get("nickname")
    }
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


def _build_request_body(path: Path, input_values: list[ComputeInputValue]) -> dict[str, Any]:
    definition_text = path.read_text(encoding="utf-8-sig")
    encoded_definition = base64.b64encode(definition_text.encode("utf-8")).decode("utf-8")
    values = [_build_data_tree(input_value) for input_value in input_values]
    return {
        "algo": encoded_definition,
        "values": values,
    }


def _build_data_tree(input_value: ComputeInputValue) -> dict[str, Any]:
    branch_key = "0"
    return {
        "ParamName": input_value.nickname,
        "InnerTree": {
            branch_key: [{"data": str(input_value.value)}],
        },
    }


def _post_grasshopper_request(compute_url: str, request_body: dict[str, Any]) -> dict[str, Any]:
    normalized_url = compute_url.rstrip("/") + "/grasshopper"
    request_data = json.dumps(request_body).encode("utf-8")
    request = urllib.request.Request(
        normalized_url,
        data=request_data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        response_text = response.read().decode("utf-8")
    return json.loads(response_text)


def _normalize_outputs(
    raw_response: dict[str, Any],
    summary: dict[str, Any],
) -> dict[str, Any]:
    output_nicknames = [
        context_bake_output.get("nickname") or CONTEXT_BAKE_COMPONENT_NAME
        for context_bake_output in summary.get("context_bake_outputs", [])
    ]
    if not output_nicknames:
        output_nicknames = [CONTEXT_BAKE_COMPONENT_NAME]

    normalized_outputs: dict[str, Any] = {}
    response_values = raw_response.get("values", [])
    for response_value in response_values:
        parameter_name = response_value.get("ParamName")
        if parameter_name is None:
            continue
        normalized_outputs[parameter_name] = _extract_inner_tree_values(response_value)

    if len(normalized_outputs) == 1 and len(output_nicknames) == 1:
        only_key = next(iter(normalized_outputs))
        if only_key != output_nicknames[0]:
            normalized_outputs[output_nicknames[0]] = normalized_outputs.pop(only_key)

    return normalized_outputs


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
            if "." in stripped or "e" in stripped.lower():
                return float(stripped)
            return int(stripped)
        except ValueError:
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
