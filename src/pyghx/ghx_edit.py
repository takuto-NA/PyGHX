"""Shared GHX XML editing primitives for PyGHX graph mutations."""

from __future__ import annotations

import copy
import uuid
import xml.etree.ElementTree as element_tree
from pathlib import Path


class GhxEditError(Exception):
    """Raised when GHX XML cannot be edited safely."""


def parse_ghx_root_element(source_path: Path | str) -> element_tree.Element:
    """Parse a GHX file and return its root element."""
    return element_tree.parse(source_path).getroot()


def write_ghx_root_element(root_element: element_tree.Element, output_path: Path) -> None:
    """Write a GHX root element to disk with refreshed chunk counts."""
    refresh_chunk_counts(root_element)
    element_tree.indent(root_element, space="  ")
    element_tree.ElementTree(root_element).write(
        output_path,
        encoding="utf-8",
        xml_declaration=True,
    )


def refresh_chunk_counts(parent_element: element_tree.Element) -> None:
    """Recursively refresh chunks count attributes."""
    chunks_element = parent_element.find("chunks")
    if chunks_element is None:
        return
    child_chunks = chunks_element.findall("chunk")
    chunks_element.set("count", str(len(child_chunks)))
    for child_chunk in child_chunks:
        refresh_chunk_counts(child_chunk)


def find_child_chunk_element(
    parent_element: element_tree.Element,
    chunk_name: str,
) -> element_tree.Element | None:
    """Return the first child chunk with the given name."""
    chunks_element = parent_element.find("chunks")
    if chunks_element is None:
        return None
    for child_element in chunks_element.findall("chunk"):
        if child_element.get("name") == chunk_name:
            return child_element
    return None


def find_object_element_in_object_chunks(
    object_chunks_element: element_tree.Element,
    component_name: str,
) -> element_tree.Element | None:
    """Return the first Object chunk whose Name item matches component_name."""
    for object_element in object_chunks_element.findall("chunk"):
        object_name_item = object_element.find('./items/item[@name="Name"]')
        if object_name_item is not None and object_name_item.text == component_name:
            return object_element
    return None


def find_items_element(parent_element: element_tree.Element) -> element_tree.Element | None:
    """Return the direct items element under one XML parent."""
    return parent_element.find("items")


def set_chunk_item_text(
    parent_element: element_tree.Element,
    item_name: str,
    item_text: str,
) -> None:
    """Set one named item on a chunk that owns an items child element."""
    items_element = find_items_element(parent_element)
    if items_element is None:
        raise GhxEditError(f"Items element was not found while setting {item_name!r}.")
    set_item_text(items_element, item_name, item_text)


def find_object_container_element(object_element: element_tree.Element) -> element_tree.Element:
    """Return the Container chunk for one Object element."""
    container_element = object_element.find('./chunks/chunk[@name="Container"]')
    if container_element is None:
        raise GhxEditError("Container chunk was not found.")
    return container_element


def set_object_container_nickname(object_element: element_tree.Element, nickname: str) -> None:
    """Set Container NickName on one Object chunk."""
    set_chunk_item_text(find_object_container_element(object_element), "NickName", nickname)


def set_object_container_item_text(
    object_element: element_tree.Element,
    item_name: str,
    item_text: str,
) -> None:
    """Set one Container item on an Object chunk."""
    set_chunk_item_text(find_object_container_element(object_element), item_name, item_text)


def read_object_param_instance_guid(
    object_element: element_tree.Element,
    parameter_nickname: str,
) -> str:
    """Return one param_input/param_output InstanceGuid by NickName."""
    container_element = find_object_container_element(object_element)
    container_chunks_element = container_element.find("chunks")
    if container_chunks_element is None:
        raise GhxEditError("Container chunks element was not found.")

    for parameter_chunk in container_chunks_element.findall("chunk"):
        chunk_name = parameter_chunk.get("name")
        if chunk_name not in {"param_input", "param_output"}:
            continue
        nickname_item = parameter_chunk.find('./items/item[@name="NickName"]')
        if nickname_item is None or nickname_item.text != parameter_nickname:
            continue
        instance_guid_item = parameter_chunk.find('./items/item[@name="InstanceGuid"]')
        if instance_guid_item is None or not instance_guid_item.text:
            raise GhxEditError(f"Parameter {parameter_nickname!r} is missing InstanceGuid.")
        return instance_guid_item.text

    raise GhxEditError(f"Parameter {parameter_nickname!r} was not found.")


def set_object_param_item_text(
    object_element: element_tree.Element,
    parameter_lookup_value: str,
    item_name: str,
    item_text: str,
    match_item_name: str = "NickName",
) -> None:
    """Set one item on a param_input/param_output chunk located by NickName or Name."""
    container_element = find_object_container_element(object_element)
    container_chunks_element = container_element.find("chunks")
    if container_chunks_element is None:
        raise GhxEditError("Container chunks element was not found.")

    for parameter_chunk in container_chunks_element.findall("chunk"):
        chunk_name = parameter_chunk.get("name")
        if chunk_name not in {"param_input", "param_output"}:
            continue
        lookup_item = parameter_chunk.find(f'./items/item[@name="{match_item_name}"]')
        if lookup_item is None or lookup_item.text != parameter_lookup_value:
            continue
        item_element = parameter_chunk.find(f'./items/item[@name="{item_name}"]')
        if item_element is None:
            raise GhxEditError(
                f"Parameter {parameter_lookup_value!r} is missing item {item_name!r}."
            )
        item_element.text = item_text
        return

    raise GhxEditError(f"Parameter {parameter_lookup_value!r} was not found.")


def offset_object_bounds_y(object_element: element_tree.Element, vertical_offset: int) -> None:
    """Offset one component's Bounds Y coordinate by vertical_offset."""
    if vertical_offset == 0:
        return

    container_element = find_object_container_element(object_element)
    for bounds_element in container_element.iter("item"):
        if bounds_element.get("name") != "Bounds":
            continue
        y_element = bounds_element.find("Y")
        if y_element is not None and y_element.text is not None:
            y_element.text = str(int(float(y_element.text)) + vertical_offset)


def find_definition_objects_element(
    root_element: element_tree.Element,
) -> element_tree.Element | None:
    """Return the DefinitionObjects chunk."""
    definition_element = find_child_chunk_element(root_element, "Definition")
    if definition_element is None:
        return None
    return find_child_chunk_element(definition_element, "DefinitionObjects")


def iter_object_elements(root_element: element_tree.Element):
    """Yield each Object chunk under DefinitionObjects."""
    definition_objects_element = find_definition_objects_element(root_element)
    if definition_objects_element is None:
        return
    object_chunks_element = definition_objects_element.find("chunks")
    if object_chunks_element is None:
        return
    for object_element in object_chunks_element.findall("chunk"):
        if object_element.get("name") == "Object":
            yield object_element


def find_object_element_by_component_name(
    root_element: element_tree.Element,
    component_name: str,
) -> element_tree.Element | None:
    """Return the first Object chunk with the given component Name item."""
    for object_element in iter_object_elements(root_element):
        object_name_item = object_element.find('./items/item[@name="Name"]')
        if object_name_item is not None and object_name_item.text == component_name:
            return object_element
    return None


def find_object_element_by_instance_guid(
    root_element: element_tree.Element,
    instance_guid: str,
) -> element_tree.Element | None:
    """Return the Object chunk whose Container InstanceGuid matches."""
    for object_element in iter_object_elements(root_element):
        container_element = object_element.find('./chunks/chunk[@name="Container"]')
        if container_element is None:
            continue
        instance_guid_item = container_element.find('./items/item[@name="InstanceGuid"]')
        if instance_guid_item is not None and instance_guid_item.text == instance_guid:
            return object_element
    return None


def find_item_text(items_element: element_tree.Element | None, item_name: str) -> str | None:
    """Return the text of one named item under an items element."""
    if items_element is None:
        return None
    for item_element in items_element.findall("item"):
        if item_element.get("name") == item_name:
            return item_element.text
    return None


_ITEM_TYPE_BY_NAME = {
    "Source": ("gh_guid", "9"),
    "InstanceGuid": ("gh_guid", "9"),
    "InputCount": ("gh_int32", "3"),
    "OutputCount": ("gh_int32", "3"),
    "SourceCount": ("gh_int32", "3"),
    "ObjectCount": ("gh_int32", "3"),
}


def set_item_text(
    items_element: element_tree.Element,
    item_name: str,
    item_text: str,
    *,
    item_index: str | None = None,
) -> None:
    """Set or create one named item under an items element."""
    if items_element is None:
        raise GhxEditError(f"Items element is required to set {item_name!r}.")

    for item_element in items_element.findall("item"):
        if item_element.get("name") != item_name:
            continue
        if item_index is not None and item_element.get("index") != item_index:
            continue
        item_element.text = item_text
        return

    new_item_attributes = {"name": item_name}
    if item_index is not None:
        new_item_attributes["index"] = item_index
    new_item_element = element_tree.SubElement(items_element, "item", new_item_attributes)
    type_name, type_code = _ITEM_TYPE_BY_NAME.get(item_name, ("gh_string", "10"))
    new_item_element.set("type_name", type_name)
    new_item_element.set("type_code", type_code)
    new_item_element.text = item_text


def collect_all_instance_guids(root_element: element_tree.Element) -> set[str]:
    """Collect every InstanceGuid value in the GHX document."""
    instance_guids: set[str] = set()
    for object_element in iter_object_elements(root_element):
        for item_element in object_element.iter("item"):
            if item_element.get("name") == "InstanceGuid" and item_element.text:
                instance_guids.add(item_element.text)
    return instance_guids


def generate_unique_instance_guid(root_element: element_tree.Element) -> str:
    """Generate a GUID that is not already used in the document."""
    existing_instance_guids = collect_all_instance_guids(root_element)
    while True:
        candidate_guid = str(uuid.uuid4())
        if candidate_guid not in existing_instance_guids:
            return candidate_guid


def append_definition_object(
    root_element: element_tree.Element,
    object_element: element_tree.Element,
) -> None:
    """Append one Object chunk and refresh ObjectCount and indexes."""
    definition_objects_element = find_definition_objects_element(root_element)
    if definition_objects_element is None:
        raise GhxEditError("DefinitionObjects chunk was not found.")

    object_chunks_element = definition_objects_element.find("chunks")
    if object_chunks_element is None:
        raise GhxEditError("DefinitionObjects chunks element was not found.")

    object_index = len(object_chunks_element.findall('chunk[@name="Object"]'))
    object_element.set("index", str(object_index))
    object_chunks_element.append(object_element)

    object_count_item = definition_objects_element.find('./items/item[@name="ObjectCount"]')
    if object_count_item is None:
        raise GhxEditError("ObjectCount item was not found.")
    object_count_item.text = str(object_index + 1)


def remove_definition_object_by_instance_guid(
    root_element: element_tree.Element,
    instance_guid: str,
) -> None:
    """Remove one Object chunk by Container InstanceGuid."""
    definition_objects_element = find_definition_objects_element(root_element)
    if definition_objects_element is None:
        raise GhxEditError("DefinitionObjects chunk was not found.")

    object_chunks_element = definition_objects_element.find("chunks")
    if object_chunks_element is None:
        raise GhxEditError("DefinitionObjects chunks element was not found.")

    removed_object = False
    for object_element in list(object_chunks_element.findall("chunk")):
        container_element = object_element.find('./chunks/chunk[@name="Container"]')
        if container_element is None:
            continue
        instance_guid_item = container_element.find('./items/item[@name="InstanceGuid"]')
        if instance_guid_item is None or instance_guid_item.text != instance_guid:
            continue
        object_chunks_element.remove(object_element)
        removed_object = True
        break

    if not removed_object:
        raise GhxEditError(f"Object was not found for InstanceGuid {instance_guid!r}.")

    remaining_object_count = len(object_chunks_element.findall('chunk[@name="Object"]'))
    object_count_item = definition_objects_element.find('./items/item[@name="ObjectCount"]')
    if object_count_item is None:
        raise GhxEditError("ObjectCount item was not found.")
    object_count_item.text = str(remaining_object_count)

    for object_index, object_element in enumerate(object_chunks_element.findall('chunk[@name="Object"]')):
        object_element.set("index", str(object_index))


def deep_copy_element(element: element_tree.Element) -> element_tree.Element:
    """Return a deep copy of one XML element."""
    return copy.deepcopy(element)


def reindex_named_chunks(
    chunks_element: element_tree.Element,
    chunk_name: str,
) -> list[element_tree.Element]:
    """Reindex chunks with the given name and return them in order."""
    matching_chunks = [
        child_chunk
        for child_chunk in chunks_element.findall("chunk")
        if child_chunk.get("name") == chunk_name
    ]
    for chunk_index, child_chunk in enumerate(matching_chunks):
        child_chunk.set("index", str(chunk_index))
    return matching_chunks


def update_items_count(items_element: element_tree.Element) -> None:
    """Refresh the items count attribute from child item count."""
    item_elements = items_element.findall("item")
    items_element.set("count", str(len(item_elements)))
