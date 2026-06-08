"""Attach RhinoCompute Context Bake boundaries to extracted pattern GHX files."""

from __future__ import annotations

import copy
import uuid
import xml.etree.ElementTree as element_tree
from importlib import resources
from pathlib import Path
from typing import Any

from pyghx.constants import (
    CONTEXT_BAKE_COMPONENT_NAME,
    CONTEXTUAL_INPUT_COMPONENT_NAMES,
)
from pyghx.inspect import inspect_document
from pyghx.loader import GhxDefinitionObject, GhxDocument, load_ghx_document

ADDITION_COMPUTE_TEMPLATE_NAME = "addition_compute.ghx"
CONTEXT_BAKE_COMPONENT_TYPE_GUID = "ae2531b4-bab2-4bb1-b5bf-f2143d10c132"
SINK_COMPONENT_NAME_PRIORITY = (
    "Addition",
    "Mass Addition",
    "Vector XYZ",
    "Number",
)


def pattern_needs_compute_boundary(pattern_summary: dict[str, Any]) -> bool:
    """Return True when a pattern has supported inputs but no Context Bake output."""
    if pattern_summary.get("context_bake_outputs"):
        return False

    compute_inputs = pattern_summary.get("compute_contract", {}).get("inputs", [])
    return any(input_entry.get("supported") for input_entry in compute_inputs)


def ensure_rhino_compute_boundary_for_supported_pattern(
    pattern_ghx_path: Path | str,
) -> Path:
    """Add Context Bake only when the pattern has supported RhinoCompute inputs."""
    path = Path(pattern_ghx_path)
    pattern_summary = inspect_document(path)
    if not pattern_needs_compute_boundary(pattern_summary):
        return path

    return ensure_rhino_compute_boundary(path)


def ensure_rhino_compute_boundary(pattern_ghx_path: Path | str) -> Path:
    """Ensure a pattern GHX has a Context Bake output wired for RhinoCompute."""
    path = Path(pattern_ghx_path)
    document = load_ghx_document(path)
    if _document_has_context_bake(document):
        return path

    sink_object = _find_sink_object(document)
    if sink_object.instance_guid is None:
        raise RuntimeError("Sink object is missing InstanceGuid.")

    root_element = element_tree.parse(path).getroot()
    definition_element = _find_child_chunk_element(root_element, "Definition")
    if definition_element is None:
        raise RuntimeError("Definition chunk was not found in pattern GHX.")

    definition_objects_element = _find_child_chunk_element(definition_element, "DefinitionObjects")
    if definition_objects_element is None:
        raise RuntimeError("DefinitionObjects chunk was not found in pattern GHX.")

    object_chunks_element = definition_objects_element.find("chunks")
    if object_chunks_element is None:
        raise RuntimeError("DefinitionObjects chunks element was not found.")

    sink_object_element = _find_object_element_for_instance_guid(
        object_chunks_element,
        sink_object.instance_guid,
    )
    if sink_object_element is None:
        raise RuntimeError("Sink object XML was not found in pattern GHX.")

    sink_output_param_guid = _find_output_param_guid(sink_object_element)
    context_bake_object_element = _build_context_bake_object_element(sink_output_param_guid)
    object_index = len(object_chunks_element.findall('chunk[@name="Object"]'))
    context_bake_object_element.set("index", str(object_index))
    object_chunks_element.append(context_bake_object_element)

    object_count_item = definition_objects_element.find('./items/item[@name="ObjectCount"]')
    if object_count_item is None:
        raise RuntimeError("ObjectCount item was not found.")
    object_count_item.text = str(object_index + 1)

    _refresh_chunk_counts(root_element)
    element_tree.indent(root_element, space="  ")
    element_tree.ElementTree(root_element).write(
        path,
        encoding="utf-8",
        xml_declaration=True,
    )
    return path


def _document_has_context_bake(document: GhxDocument) -> bool:
    return any(
        definition_object.component_name == CONTEXT_BAKE_COMPONENT_NAME
        for definition_object in document.objects
    )


def _find_sink_object(document: GhxDocument) -> GhxDefinitionObject:
    contextual_component_names = set(CONTEXTUAL_INPUT_COMPONENT_NAMES)
    for component_name in SINK_COMPONENT_NAME_PRIORITY:
        for definition_object in document.objects:
            if definition_object.component_name != component_name:
                continue
            if definition_object.component_name in contextual_component_names:
                continue
            return definition_object

    raise RuntimeError(
        "No sink component was found to wire Context Bake for RhinoCompute."
    )


def _build_context_bake_object_element(sink_output_param_guid: str) -> element_tree.Element:
    template_object_element = _load_context_bake_template_object_element()
    context_bake_object_element = copy.deepcopy(template_object_element)

    context_bake_instance_guid = str(uuid.uuid4())
    content_param_guid = str(uuid.uuid4())

    container_element = context_bake_object_element.find('./chunks/chunk[@name="Container"]')
    if container_element is None:
        raise RuntimeError("Context Bake template is missing Container chunk.")

    context_bake_instance_item = container_element.find('./items/item[@name="InstanceGuid"]')
    if context_bake_instance_item is None:
        raise RuntimeError("Context Bake template is missing InstanceGuid.")
    context_bake_instance_item.text = context_bake_instance_guid

    content_param_element = container_element.find('./chunks/chunk[@name="param_input"]')
    if content_param_element is None:
        raise RuntimeError("Context Bake template is missing Content param_input.")

    content_instance_item = content_param_element.find('./items/item[@name="InstanceGuid"]')
    if content_instance_item is None:
        raise RuntimeError("Context Bake Content param is missing InstanceGuid.")
    content_instance_item.text = content_param_guid

    source_item = content_param_element.find('./items/item[@name="Source"]')
    if source_item is None:
        raise RuntimeError("Context Bake Content param is missing Source item.")
    source_item.text = sink_output_param_guid

    component_guid_item = context_bake_object_element.find('./items/item[@name="GUID"]')
    if component_guid_item is not None:
        component_guid_item.text = CONTEXT_BAKE_COMPONENT_TYPE_GUID

    return context_bake_object_element


def _load_context_bake_template_object_element() -> element_tree.Element:
    template_path = resources.files("pyghx.templates") / ADDITION_COMPUTE_TEMPLATE_NAME
    root_element = element_tree.parse(str(template_path)).getroot()
    definition_element = _find_child_chunk_element(root_element, "Definition")
    if definition_element is None:
        raise RuntimeError("Definition chunk was not found in addition compute template.")

    definition_objects_element = _find_child_chunk_element(definition_element, "DefinitionObjects")
    if definition_objects_element is None:
        raise RuntimeError("DefinitionObjects chunk was not found in addition compute template.")

    object_chunks_element = definition_objects_element.find("chunks")
    if object_chunks_element is None:
        raise RuntimeError("DefinitionObjects chunks element was not found in template.")

    for object_element in object_chunks_element.findall("chunk"):
        if object_element.get("name") != "Object":
            continue
        object_name_item = object_element.find('./items/item[@name="Name"]')
        if object_name_item is not None and object_name_item.text == CONTEXT_BAKE_COMPONENT_NAME:
            return object_element

    raise RuntimeError("Context Bake object was not found in addition compute template.")


def _find_object_element_for_instance_guid(
    object_chunks_element: element_tree.Element,
    instance_guid: str,
) -> element_tree.Element | None:
    for object_element in object_chunks_element.findall("chunk"):
        if object_element.get("name") != "Object":
            continue
        instance_guid_item = object_element.find(
            './chunks/chunk[@name="Container"]/items/item[@name="InstanceGuid"]'
        )
        if instance_guid_item is not None and instance_guid_item.text == instance_guid:
            return object_element
    return None


def _find_output_param_guid(object_element: element_tree.Element) -> str:
    for nested_chunk in object_element.iter("chunk"):
        if nested_chunk.get("name") != "OutputParam":
            continue
        instance_guid_item = nested_chunk.find('./items/item[@name="InstanceGuid"]')
        if instance_guid_item is not None and instance_guid_item.text:
            return instance_guid_item.text

    container_element = object_element.find('./chunks/chunk[@name="Container"]')
    if container_element is None:
        raise RuntimeError("Sink object is missing Container chunk.")

    instance_guid_item = container_element.find('./items/item[@name="InstanceGuid"]')
    if instance_guid_item is None or not instance_guid_item.text:
        raise RuntimeError("Sink object is missing InstanceGuid.")

    return instance_guid_item.text


def _find_child_chunk_element(
    parent_element: element_tree.Element,
    chunk_name: str,
) -> element_tree.Element | None:
    chunks_element = parent_element.find("chunks")
    if chunks_element is None:
        return None

    for child_element in chunks_element.findall("chunk"):
        if child_element.get("name") == chunk_name:
            return child_element
    return None


def _refresh_chunk_counts(root_element: element_tree.Element) -> None:
    _set_chunks_count_attribute(root_element)


def _set_chunks_count_attribute(parent_element: element_tree.Element) -> None:
    chunks_element = parent_element.find("chunks")
    if chunks_element is None:
        return

    child_chunks = chunks_element.findall("chunk")
    chunks_element.set("count", str(len(child_chunks)))

    for child_chunk in child_chunks:
        _set_chunks_count_attribute(child_chunk)
