"""Build machine-readable GHX summaries for AI agents."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pyghx.constants import (
    CONTEXT_BAKE_COMPONENT_NAME,
    CONTEXTUAL_INPUT_COMPONENT_NAMES,
    SCHEMA_VERSION,
)
from pyghx.loader import (
    GhxDefinitionObject,
    GhxDocument,
    GhxLoadError,
    build_instance_guid_owner_map,
    load_ghx_document,
)


def inspect_document(source_path: Path | str) -> dict[str, Any]:
    """Inspect a GHX file and return a JSON-serializable summary."""
    document = load_ghx_document(source_path)
    return build_summary(document)


def build_summary(document: GhxDocument) -> dict[str, Any]:
    """Build a summary dictionary from a loaded document."""
    instance_guid_to_object = build_instance_guid_owner_map(document.objects)
    connections = _build_connections(document.objects, instance_guid_to_object)
    contextual_inputs = _build_contextual_inputs(document.objects)
    context_bake_outputs = _build_context_bake_outputs(
        document.objects,
        instance_guid_to_object,
    )
    unknown_elements = _build_unknown_elements(document)
    diagnostics = _build_diagnostics(document, contextual_inputs, context_bake_outputs)

    return {
        "schema_version": SCHEMA_VERSION,
        "source_path": str(document.archive.source_path) if document.archive.source_path else None,
        "document_metadata": {
            "document_name": document.document_name,
            "archive_name": document.archive.name,
        },
        "object_count": document.object_count,
        "objects": [
            {
                "index": definition_object.index,
                "component_name": definition_object.component_name,
                "component_guid": definition_object.component_guid,
                "instance_guid": definition_object.instance_guid,
                "nickname": definition_object.nickname,
                "optional": definition_object.optional,
            }
            for definition_object in document.objects
        ],
        "connections": connections,
        "contextual_inputs": contextual_inputs,
        "context_bake_outputs": context_bake_outputs,
        "unknown_elements": unknown_elements,
        "diagnostics": diagnostics,
    }


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
                    "target_instance_guid": definition_object.instance_guid,
                    "target_component_name": definition_object.component_name,
                    "target_nickname": definition_object.nickname,
                    "source_instance_guid": source_guid,
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
        contextual_inputs.append(
            {
                "kind": CONTEXTUAL_INPUT_COMPONENT_NAMES[definition_object.component_name],
                "component_name": definition_object.component_name,
                "instance_guid": definition_object.instance_guid,
                "nickname": definition_object.nickname,
                "optional": definition_object.optional,
            }
        )
    return contextual_inputs


def _build_context_bake_outputs(
    objects: tuple[GhxDefinitionObject, ...],
    instance_guid_to_object: dict[str, GhxDefinitionObject],
) -> list[dict[str, Any]]:
    context_bake_outputs: list[dict[str, Any]] = []
    for definition_object in objects:
        if definition_object.component_name != CONTEXT_BAKE_COMPONENT_NAME:
            continue

        source_objects = [
            instance_guid_to_object[source_guid]
            for source_guid in definition_object.source_guids
            if source_guid in instance_guid_to_object
        ]
        context_bake_outputs.append(
            {
                "component_name": definition_object.component_name,
                "instance_guid": definition_object.instance_guid,
                "nickname": definition_object.nickname,
                "source_instance_guids": list(definition_object.source_guids),
                "source_component_names": [
                    source_object.component_name for source_object in source_objects
                ],
                "source_nicknames": [
                    source_object.nickname for source_object in source_objects
                ],
            }
        )
    return context_bake_outputs


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


def inspect_document_safe(source_path: Path | str) -> dict[str, Any]:
    """Inspect a GHX file, returning diagnostics instead of raising on load failure."""
    try:
        return inspect_document(source_path)
    except GhxLoadError as load_error:
        return {
            "schema_version": SCHEMA_VERSION,
            "source_path": str(source_path),
            "document_metadata": {},
            "object_count": 0,
            "objects": [],
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
