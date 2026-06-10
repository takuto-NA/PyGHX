"""C# Script and RhinoCompute contract diagnostics for GHX validation."""

from __future__ import annotations

from collections import Counter
from pyghx.constants import CONTEXT_BAKE_COMPONENT_NAME, CONTEXTUAL_INPUT_COMPONENT_NAMES
from pyghx.inspect import inspect_document
from pyghx.loader import load_ghx_document
from pyghx.script_component import (
    C_SHARP_SCRIPT_COMPONENT_NAME,
    ScriptComponentError,
    decode_script_source_text,
    extract_script_components,
)
from pyghx.script_source import (
    ScriptSourceError,
    build_run_script_signature_warning,
    parse_run_script_signature,
)


def build_script_validation_diagnostics(source_path: str) -> list[dict[str, str]]:
    """Return C# Script and compute-contract diagnostics for one GHX file."""
    diagnostics: list[dict[str, str]] = []
    diagnostics.extend(_build_duplicate_compute_param_diagnostics(source_path))
    diagnostics.extend(_build_script_component_diagnostics(source_path))
    return diagnostics


def _build_duplicate_compute_param_diagnostics(source_path: str) -> list[dict[str, str]]:
    summary = inspect_document(source_path)
    diagnostics: list[dict[str, str]] = []

    input_param_names = [
        contextual_input["compute_param_name"]
        for contextual_input in summary.get("contextual_inputs", [])
    ]
    duplicate_input_names = _find_duplicate_values(input_param_names)
    for duplicate_input_name in duplicate_input_names:
        diagnostics.append(
            {
                "level": "error",
                "code": "duplicate_compute_input_param_name",
                "message": (
                    "Multiple contextual inputs share the same RhinoCompute param name "
                    f"{duplicate_input_name!r}. Parameter names must be unique."
                ),
            }
        )

    output_param_names = [
        context_bake_output["compute_param_name"]
        for context_bake_output in summary.get("context_bake_outputs", [])
    ]
    duplicate_output_names = _find_duplicate_values(output_param_names)
    for duplicate_output_name in duplicate_output_names:
        diagnostics.append(
            {
                "level": "warning",
                "code": "duplicate_compute_output_param_name",
                "message": (
                    "Multiple Context Bake outputs share the same RhinoCompute param name "
                    f"{duplicate_output_name!r}. Parameter names must be unique for "
                    "single-shot RhinoCompute execution."
                ),
            }
        )
    return diagnostics


def _build_script_component_diagnostics(source_path: str) -> list[dict[str, str]]:
    document = load_ghx_document(source_path)
    script_summaries = extract_script_components(document)
    if not script_summaries:
        return []

    diagnostics: list[dict[str, str]] = []
    has_context_bake = any(
        definition_object.component_name == CONTEXT_BAKE_COMPONENT_NAME
        for definition_object in document.objects
    )
    has_contextual_input = any(
        definition_object.component_name in CONTEXTUAL_INPUT_COMPONENT_NAMES
        for definition_object in document.objects
    )
    if has_contextual_input and not has_context_bake:
        diagnostics.append(
            {
                "level": "error",
                "code": "missing_context_bake_for_compute",
                "message": (
                    "Contextual inputs were detected but no Context Bake output exists "
                    "for RhinoCompute execution."
                ),
            }
        )

    for script_summary in script_summaries:
        script_label = script_summary.nickname or C_SHARP_SCRIPT_COMPONENT_NAME
        if not script_summary.encoded_source_text:
            diagnostics.append(
                {
                    "level": "error",
                    "code": "missing_script_source_text",
                    "message": f"C# Script {script_label!r} is missing Script > Text content.",
                }
            )
            continue

        try:
            decoded_source_text = decode_script_source_text(script_summary.encoded_source_text)
        except ScriptComponentError:
            diagnostics.append(
                {
                    "level": "error",
                    "code": "invalid_script_source_encoding",
                    "message": (
                        f"C# Script {script_label!r} has invalid base64-encoded source text."
                    ),
                }
            )
            continue

        if not decoded_source_text.strip():
            diagnostics.append(
                {
                    "level": "error",
                    "code": "empty_script_source_text",
                    "message": f"C# Script {script_label!r} has empty source text.",
                }
            )

        signature_warning = build_run_script_signature_warning(decoded_source_text)
        if signature_warning is not None:
            diagnostics.append(
                {
                    "level": "warning",
                    "code": "missing_run_script_signature",
                    "message": f"C# Script {script_label!r}: {signature_warning}",
                }
            )
        else:
            diagnostics.extend(
                _build_run_script_parameter_diagnostics(
                    script_label=script_label,
                    decoded_source_text=decoded_source_text,
                    script_summary=script_summary,
                )
            )

        diagnostics.extend(
            _build_script_input_wiring_diagnostics(
                script_label=script_label,
                script_summary=script_summary,
                document=document,
            )
        )

        if script_summary.outputs and not script_summary.context_bake_reachable_output_nicknames:
            diagnostics.append(
                {
                    "level": "warning",
                    "code": "script_output_not_wired_to_context_bake",
                    "message": (
                        f"C# Script {script_label!r} has outputs that are not wired to "
                        "any Context Bake component."
                    ),
                }
            )
    return diagnostics


def _build_run_script_parameter_diagnostics(
    script_label: str,
    decoded_source_text: str,
    script_summary,
) -> list[dict[str, str]]:
    diagnostics: list[dict[str, str]] = []
    try:
        run_script_input_names, _run_script_output_names = parse_run_script_signature(
            decoded_source_text
        )
    except ScriptSourceError:
        return diagnostics

    script_input_names = tuple(script_input.name for script_input in script_summary.inputs)
    if run_script_input_names != script_input_names:
        diagnostics.append(
            {
                "level": "error",
                "code": "run_script_signature_mismatch",
                "message": (
                    f"C# Script {script_label!r} RunScript input variables "
                    f"{list(run_script_input_names)!r} do not match ParameterData inputs "
                    f"{list(script_input_names)!r}."
                ),
            }
        )

    duplicate_script_input_names = _find_duplicate_values(list(script_input_names))
    for duplicate_script_input_name in duplicate_script_input_names:
        diagnostics.append(
            {
                "level": "error",
                "code": "script_parameter_duplicate_name",
                "message": (
                    f"C# Script {script_label!r} has duplicate input parameter name "
                    f"{duplicate_script_input_name!r}."
                ),
            }
        )
    return diagnostics


def _build_script_input_wiring_diagnostics(
    script_label: str,
    script_summary,
    document,
) -> list[dict[str, str]]:
    diagnostics: list[dict[str, str]] = []
    contextual_component_names = set(CONTEXTUAL_INPUT_COMPONENT_NAMES)
    component_name_by_instance_guid = {
        definition_object.instance_guid: definition_object.component_name
        for definition_object in document.objects
        if definition_object.instance_guid is not None
    }

    for script_input in script_summary.inputs:
        if not script_input.source_instance_guids:
            diagnostics.append(
                {
                    "level": "error",
                    "code": "script_input_not_wired",
                    "message": (
                        f"C# Script {script_label!r} input {script_input.name!r} "
                        "is not wired to any contextual source."
                    ),
                }
            )
            continue

        for source_instance_guid in script_input.source_instance_guids:
            source_component_name = component_name_by_instance_guid.get(source_instance_guid)
            if source_component_name in contextual_component_names:
                continue
            diagnostics.append(
                {
                    "level": "error",
                    "code": "script_input_missing_contextual_source",
                    "message": (
                        f"C# Script {script_label!r} input {script_input.name!r} "
                        f"is wired to {source_instance_guid!r}, which is not a supported "
                        "contextual input component."
                    ),
                }
            )
    return diagnostics


def _find_duplicate_values(values: list[str]) -> list[str]:
    value_counts = Counter(values)
    return sorted(
        value_name
        for value_name, occurrence_count in value_counts.items()
        if occurrence_count > 1
    )
