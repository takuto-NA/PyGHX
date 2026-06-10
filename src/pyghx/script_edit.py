"""Edit C# Script components and contextual inputs in GHX files."""

from __future__ import annotations

import re
import xml.etree.ElementTree as element_tree
from pathlib import Path

from pyghx.script_component import (
    C_SHARP_SCRIPT_COMPONENT_NAME,
    ScriptComponentError,
    encode_script_source_text,
    get_script_source_text,
)

CONTEXTUAL_INPUT_COMPONENT_NAME = "Get Number"
CONTEXT_BAKE_COMPONENT_NAME = "Context Bake"
RUN_SCRIPT_SIGNATURE_PATTERN = re.compile(
    r"private\s+void\s+RunScript\s*\(([^)]*)\)",
    re.MULTILINE,
)


def set_script_source_text(
    source_path: Path | str,
    source_text: str,
    instance_guid: str | None = None,
) -> Path:
    """Replace decoded C# Script source text in a GHX file."""
    path = Path(source_path)
    root_element = element_tree.parse(path).getroot()
    script_text_item = _find_script_text_item(root_element, instance_guid)
    if script_text_item is None:
        raise ScriptComponentError("C# Script Text item was not found.")

    script_text_item.text = encode_script_source_text(source_text)
    _write_ghx(root_element, path)
    return path


def rename_contextual_input_nickname(
    source_path: Path | str,
    instance_guid: str,
    nickname: str,
) -> Path:
    """Rename one contextual Get Number input nickname."""
    path = Path(source_path)
    root_element = element_tree.parse(path).getroot()
    nickname_item = _find_contextual_input_nickname_item(root_element, instance_guid)
    if nickname_item is None:
        raise ScriptComponentError(
            f"Contextual input object was not found: {instance_guid!r}."
        )
    nickname_item.text = nickname
    _write_ghx(root_element, path)
    return path


def remove_context_bake_by_instance_guid(
    source_path: Path | str,
    instance_guid: str,
) -> Path:
    """Remove one Context Bake component from a GHX file."""
    path = Path(source_path)
    root_element = element_tree.parse(path).getroot()
    definition_objects_element = _find_definition_objects_element(root_element)
    if definition_objects_element is None:
        raise ScriptComponentError("DefinitionObjects chunk was not found.")

    object_chunks_element = definition_objects_element.find("chunks")
    if object_chunks_element is None:
        raise ScriptComponentError("DefinitionObjects chunks element was not found.")

    removed_object = False
    for object_element in list(object_chunks_element.findall("chunk")):
        object_name_item = object_element.find('./items/item[@name="Name"]')
        if object_name_item is None or object_name_item.text != CONTEXT_BAKE_COMPONENT_NAME:
            continue
        container_element = object_element.find('./chunks/chunk[@name="Container"]')
        if container_element is None:
            continue
        container_instance_guid_item = container_element.find('./items/item[@name="InstanceGuid"]')
        if container_instance_guid_item is None:
            continue
        if container_instance_guid_item.text != instance_guid:
            continue
        object_chunks_element.remove(object_element)
        removed_object = True
        break

    if not removed_object:
        raise ScriptComponentError(f"Context Bake object was not found: {instance_guid!r}.")

    remaining_object_count = len(object_chunks_element.findall("chunk"))
    object_count_item = definition_objects_element.find('./items/item[@name="ObjectCount"]')
    if object_count_item is None:
        raise ScriptComponentError("ObjectCount item was not found.")
    object_count_item.text = str(remaining_object_count)
    for object_index, object_element in enumerate(object_chunks_element.findall("chunk")):
        object_element.set("index", str(object_index))

    _write_ghx(root_element, path)
    return path


def repair_duplicate_contextual_input_nicknames(
    source_path: Path | str,
    nickname_assignments: list[tuple[str, str]],
) -> Path:
    """Assign unique nicknames to contextual inputs by instance GUID."""
    path = Path(source_path)
    for instance_guid, nickname in nickname_assignments:
        rename_contextual_input_nickname(path, instance_guid, nickname)
    return path


def read_script_source_text(source_path: Path | str, instance_guid: str | None = None) -> str:
    """Return decoded C# Script source text."""
    return get_script_source_text(source_path, instance_guid=instance_guid)


def build_run_script_signature_warning(source_text: str) -> str | None:
    """Return a warning when RunScript signature is missing from script source."""
    if RUN_SCRIPT_SIGNATURE_PATTERN.search(source_text):
        return None
    return "RunScript signature was not found in C# Script source text."


def _find_script_text_item(
    root_element: element_tree.Element,
    instance_guid: str | None,
) -> element_tree.Element | None:
    for object_element in _iter_object_elements(root_element):
        object_name_item = object_element.find('./items/item[@name="Name"]')
        if object_name_item is None or object_name_item.text != C_SHARP_SCRIPT_COMPONENT_NAME:
            continue
        container_element = object_element.find('./chunks/chunk[@name="Container"]')
        if container_element is None:
            continue
        container_instance_guid_item = container_element.find('./items/item[@name="InstanceGuid"]')
        if instance_guid is not None:
            if container_instance_guid_item is None:
                continue
            if container_instance_guid_item.text != instance_guid:
                continue
        return container_element.find('./chunks/chunk[@name="Script"]/items/item[@name="Text"]')
    return None


def _find_contextual_input_nickname_item(
    root_element: element_tree.Element,
    instance_guid: str,
) -> element_tree.Element | None:
    for object_element in _iter_object_elements(root_element):
        object_name_item = object_element.find('./items/item[@name="Name"]')
        if object_name_item is None or object_name_item.text != CONTEXTUAL_INPUT_COMPONENT_NAME:
            continue
        container_element = object_element.find('./chunks/chunk[@name="Container"]')
        if container_element is None:
            continue
        container_instance_guid_item = container_element.find('./items/item[@name="InstanceGuid"]')
        if container_instance_guid_item is None or container_instance_guid_item.text != instance_guid:
            continue
        return container_element.find('./items/item[@name="NickName"]')
    return None


def _find_definition_objects_element(
    root_element: element_tree.Element,
) -> element_tree.Element | None:
    definition_element = _find_child_chunk_element(root_element, "Definition")
    if definition_element is None:
        return None
    return _find_child_chunk_element(definition_element, "DefinitionObjects")


def _iter_object_elements(root_element: element_tree.Element):
    definition_element = _find_child_chunk_element(root_element, "Definition")
    if definition_element is None:
        return
    definition_objects_element = _find_child_chunk_element(definition_element, "DefinitionObjects")
    if definition_objects_element is None:
        return
    object_chunks_element = definition_objects_element.find("chunks")
    if object_chunks_element is None:
        return
    for object_element in object_chunks_element.findall("chunk"):
        if object_element.get("name") == "Object":
            yield object_element


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


def _write_ghx(root_element: element_tree.Element, output_path: Path) -> None:
    _refresh_chunk_counts(root_element)
    element_tree.indent(root_element, space="  ")
    element_tree.ElementTree(root_element).write(
        output_path,
        encoding="utf-8",
        xml_declaration=True,
    )


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
