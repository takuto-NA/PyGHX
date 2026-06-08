"""Build machine-readable GHX summaries for AI agents."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pyghx.constants import (
    CONTEXT_BAKE_COMPONENT_NAME,
    CONTEXTUAL_INPUT_COMPONENT_NAMES,
    RHINO_COMPUTE_CONTEXT_BAKE_PARAM_NAME,
    SCHEMA_VERSION,
    SUPPORTED_RHINO_COMPUTE_INPUT_KINDS,
)
from pyghx.loader import (
    GhxDefinitionObject,
    GhxDocument,
    GhxLoadError,
    build_instance_guid_owner_map,
    load_ghx_document,
)


def inspect_document(source_path: Path | str, include_objects: bool = False) -> dict[str, Any]:
    """Inspect a GHX file and return a JSON-serializable summary."""
    document = load_ghx_document(source_path)
    return build_summary(document, include_objects=include_objects)


def build_summary(document: GhxDocument, include_objects: bool = False) -> dict[str, Any]:
    """Build a summary dictionary from a loaded document."""
    instance_guid_to_object = build_instance_guid_owner_map(document.objects)
    connections = _build_connections(document.objects, instance_guid_to_object)
    contextual_inputs = _build_contextual_inputs(document.objects)
    context_bake_outputs = _build_context_bake_outputs(
        document.objects,
        instance_guid_to_object,
    )
    compute_contract = _build_compute_contract(contextual_inputs, context_bake_outputs)
    unknown_elements = _build_unknown_elements(document)
    diagnostics = _build_diagnostics(document, contextual_inputs, context_bake_outputs)
    summary_text = _build_summary_text(
        document_name=document.document_name,
        object_count=document.object_count,
        contextual_inputs=contextual_inputs,
        context_bake_outputs=context_bake_outputs,
    )

    summary: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "source_path": str(document.archive.source_path) if document.archive.source_path else None,
        "summary_text": summary_text,
        "document_metadata": {
            "document_name": document.document_name,
            "archive_name": document.archive.name,
        },
        "object_count": document.object_count,
        "compute_contract": compute_contract,
        "connections": connections,
        "contextual_inputs": contextual_inputs,
        "context_bake_outputs": context_bake_outputs,
        "unknown_elements": unknown_elements,
        "diagnostics": diagnostics,
    }
    if include_objects:
        summary["objects"] = _build_object_summaries(document.objects)
    return summary


def _build_object_summaries(objects: tuple[GhxDefinitionObject, ...]) -> list[dict[str, Any]]:
    return [
        {
            "index": definition_object.index,
            "component_name": definition_object.component_name,
            "component_guid": definition_object.component_guid,
            "instance_guid": definition_object.instance_guid,
            "nickname": definition_object.nickname,
            "optional": definition_object.optional,
        }
        for definition_object in objects
    ]


def _build_connections(
    objects: tuple[GhxDefinitionObject, ...],
    instance_guid_to_object: dict[str, GhxDefinitionObject],
) -> list[dict[str, str | None]]:
    connections: list[dict[str, str | None]] = []
    for definition_object in objects:
        for source_guid in definition_object.source_guids:
            source_object = instance_guid_to_object.get(source_guid)
            connections.append(
                {
                    "target_component_name": definition_object.component_name,
                    "target_nickname": definition_object.nickname,
                    "source_component_name": source_object.component_name if source_object else None,
                    "source_nickname": source_object.nickname if source_object else None,
                }
            )
    return connections


def _build_contextual_inputs(objects: tuple[GhxDefinitionObject, ...]) -> list[dict[str, Any]]:
    contextual_inputs: list[dict[str, Any]] = []
    for definition_object in objects:
        if definition_object.component_name not in CONTEXTUAL_INPUT_COMPONENT_NAMES:
            continue

        input_kind = CONTEXTUAL_INPUT_COMPONENT_NAMES[definition_object.component_name]
        contextual_inputs.append(
            {
                "kind": input_kind,
                "component_name": definition_object.component_name,
                "nickname": definition_object.nickname,
                "optional": definition_object.optional,
                "supported_for_compute": input_kind in SUPPORTED_RHINO_COMPUTE_INPUT_KINDS,
            }
        )
    return contextual_inputs


def _build_context_bake_outputs(
    objects: tuple[GhxDefinitionObject, ...],
    instance_guid_to_object: dict[str, GhxDefinitionObject],
) -> list[dict[str, Any]]:
    context_bake_outputs: list[dict[str, Any]] = []
    used_labels: set[str] = set()
    bake_index = 0

    for definition_object in objects:
        if definition_object.component_name != CONTEXT_BAKE_COMPONENT_NAME:
            continue

        source_objects = [
            instance_guid_to_object[source_guid]
            for source_guid in definition_object.source_guids
            if source_guid in instance_guid_to_object
        ]
        primary_source = source_objects[0] if source_objects else None
        label = _build_unique_output_label(
            source_nickname=primary_source.nickname if primary_source else None,
            source_component_name=primary_source.component_name if primary_source else None,
            bake_index=bake_index,
            used_labels=used_labels,
        )
        compute_param_name = _resolve_compute_param_name(definition_object)
        context_bake_outputs.append(
            {
                "index": bake_index,
                "label": label,
                "compute_param_name": compute_param_name,
                "instance_guid": definition_object.instance_guid,
                "nickname": definition_object.nickname,
                "source_nickname": primary_source.nickname if primary_source else None,
                "source_component_name": primary_source.component_name if primary_source else None,
                "source_instance_guids": list(definition_object.source_guids),
            }
        )
        bake_index += 1
    return context_bake_outputs


def _resolve_compute_param_name(definition_object: GhxDefinitionObject) -> str:
    if definition_object.param_input_nicknames:
        return definition_object.param_input_nicknames[0]
    return RHINO_COMPUTE_CONTEXT_BAKE_PARAM_NAME


def _build_unique_output_label(
    source_nickname: str | None,
    source_component_name: str | None,
    bake_index: int,
    used_labels: set[str],
) -> str:
    base_label = _slugify_label(source_nickname or source_component_name or f"context_bake_{bake_index}")
    if base_label not in used_labels:
        used_labels.add(base_label)
        return base_label

    suffix = 2
    while True:
        candidate_label = f"{base_label}_{suffix}"
        if candidate_label not in used_labels:
            used_labels.add(candidate_label)
            return candidate_label
        suffix += 1


def _slugify_label(raw_label: str) -> str:
    normalized_label = raw_label.strip().lower()
    normalized_label = re.sub(r"[^a-z0-9]+", "_", normalized_label)
    normalized_label = normalized_label.strip("_")
    if normalized_label:
        return normalized_label
    return "context_bake"


def _build_compute_contract(
    contextual_inputs: list[dict[str, Any]],
    context_bake_outputs: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "inputs": [
            {
                "nickname": contextual_input["nickname"],
                "kind": contextual_input["kind"],
                "optional": contextual_input["optional"],
                "supported": contextual_input["supported_for_compute"],
            }
            for contextual_input in contextual_inputs
        ],
        "outputs": [
            {
                "label": context_bake_output["label"],
                "compute_param_name": context_bake_output["compute_param_name"],
                "source_nickname": context_bake_output["source_nickname"],
                "source_component_name": context_bake_output["source_component_name"],
                "context_bake_index": context_bake_output["index"],
                "instance_guid": context_bake_output["instance_guid"],
            }
            for context_bake_output in context_bake_outputs
        ],
    }


def _build_summary_text(
    document_name: str | None,
    object_count: int,
    contextual_inputs: list[dict[str, Any]],
    context_bake_outputs: list[dict[str, Any]],
) -> str:
    document_label = document_name or "GHX document"

    if not contextual_inputs and not context_bake_outputs:
        return (
            f"{document_label} contains {object_count} objects and exposes no "
            "RhinoCompute contextual inputs or Context Bake outputs."
        )

    input_descriptions = [
        _describe_contextual_input(contextual_input) for contextual_input in contextual_inputs
    ]
    output_descriptions = [
        _describe_context_bake_output(context_bake_output)
        for context_bake_output in context_bake_outputs
    ]
    return (
        f"{document_label} provides contextual inputs [{', '.join(input_descriptions)}] "
        f"and Context Bake outputs [{', '.join(output_descriptions)}]."
    )


def _describe_contextual_input(contextual_input: dict[str, Any]) -> str:
    optional_suffix = " optional" if contextual_input.get("optional") else ""
    supported_suffix = (
        " supported by PyGHX compute"
        if contextual_input.get("supported_for_compute")
        else " inspect-only in PyGHX compute"
    )
    nickname = contextual_input.get("nickname") or contextual_input.get("component_name")
    return f"{nickname}:{contextual_input['kind']}{optional_suffix}{supported_suffix}"


def _describe_context_bake_output(context_bake_output: dict[str, Any]) -> str:
    source_label = (
        context_bake_output.get("source_nickname")
        or context_bake_output.get("source_component_name")
        or "unknown source"
    )
    return (
        f"{context_bake_output['label']} from {source_label} "
        f"via compute param {context_bake_output['compute_param_name']}"
    )


def _build_unknown_elements(document: GhxDocument) -> list[dict[str, str]]:
    unknown_elements: list[dict[str, str]] = []
    for component_name in document.unknown_component_names:
        unknown_elements.append(
            {
                "kind": "unknown_component",
                "component_name": component_name,
            }
        )
    return unknown_elements


def _build_diagnostics(
    document: GhxDocument,
    contextual_inputs: list[dict[str, Any]],
    context_bake_outputs: list[dict[str, Any]],
) -> list[dict[str, str]]:
    diagnostics: list[dict[str, str]] = []
    if not contextual_inputs:
        diagnostics.append(
            {
                "level": "warning",
                "code": "no_contextual_inputs",
                "message": "No contextual inputs were detected in this GHX.",
            }
        )
    if not context_bake_outputs:
        diagnostics.append(
            {
                "level": "warning",
                "code": "no_context_bake_outputs",
                "message": "No Context Bake outputs were detected in this GHX.",
            }
        )
    if document.unknown_component_names:
        diagnostics.append(
            {
                "level": "info",
                "code": "unknown_components_present",
                "message": (
                    "Unknown component names were detected: "
                    + ", ".join(document.unknown_component_names)
                ),
            }
        )
    return diagnostics


def inspect_document_safe(
    source_path: Path | str,
    include_objects: bool = False,
) -> dict[str, Any]:
    """Inspect a GHX file, returning diagnostics instead of raising on load failure."""
    try:
        return inspect_document(source_path, include_objects=include_objects)
    except GhxLoadError as load_error:
        summary = {
            "schema_version": SCHEMA_VERSION,
            "source_path": str(source_path),
            "summary_text": "GHX document could not be parsed.",
            "document_metadata": {},
            "object_count": 0,
            "compute_contract": {"inputs": [], "outputs": []},
            "connections": [],
            "contextual_inputs": [],
            "context_bake_outputs": [],
            "unknown_elements": [],
            "diagnostics": [
                {
                    "level": "error",
                    "code": "xml_parse_error",
                    "message": str(load_error),
                }
            ],
        }
        if include_objects:
            summary["objects"] = []
        return summary
