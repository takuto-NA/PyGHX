"""Mutate known-good GHX fixtures to reproduce structural integrity failures."""

from __future__ import annotations

import copy
import xml.etree.ElementTree as element_tree
from pathlib import Path


def write_mutated_ghx_fixture(
    source_fixture_path: Path,
    output_fixture_path: Path,
    mutation_callback,
) -> Path:
    """Copy a fixture, apply one mutation, and write the result."""
    root_element = element_tree.parse(source_fixture_path).getroot()
    mutation_callback(root_element)
    output_fixture_path.parent.mkdir(parents=True, exist_ok=True)
    element_tree.indent(root_element, space="  ")
    element_tree.ElementTree(root_element).write(
        output_fixture_path,
        encoding="utf-8",
        xml_declaration=True,
    )
    return output_fixture_path


def mutate_definition_objects_object_count(
    root_element: element_tree.Element,
    stale_object_count: int,
) -> None:
    """Set DefinitionObjects ObjectCount to a stale value."""
    definition_objects_element = _find_definition_objects_element(root_element)
    object_count_item = definition_objects_element.find(
        './items/item[@name="ObjectCount"]'
    )
    if object_count_item is None:
        raise RuntimeError("ObjectCount item was not found.")
    object_count_item.text = str(stale_object_count)


def mutate_definition_objects_chunks_count(
    root_element: element_tree.Element,
    stale_chunks_count: int,
) -> None:
    """Set DefinitionObjects chunks/@count to a stale value."""
    definition_objects_element = _find_definition_objects_element(root_element)
    object_chunks_element = definition_objects_element.find("chunks")
    if object_chunks_element is None:
        raise RuntimeError("DefinitionObjects chunks element was not found.")
    object_chunks_element.set("count", str(stale_chunks_count))


def mutate_definition_objects_object_index_gap(root_element: element_tree.Element) -> None:
    """Leave Object index 0 missing so indices are non-contiguous."""
    definition_objects_element = _find_definition_objects_element(root_element)
    object_chunks_element = definition_objects_element.find("chunks")
    if object_chunks_element is None:
        raise RuntimeError("DefinitionObjects chunks element was not found.")

    object_elements = object_chunks_element.findall("chunk")
    if len(object_elements) < 2:
        raise RuntimeError("At least two Object chunks are required for index gap mutation.")

    first_object_element = object_elements[0]
    first_object_element.set("index", "1")


def mutate_duplicate_instance_guid(root_element: element_tree.Element) -> None:
    """Duplicate the first Object container InstanceGuid onto a second object."""
    definition_objects_element = _find_definition_objects_element(root_element)
    object_chunks_element = definition_objects_element.find("chunks")
    if object_chunks_element is None:
        raise RuntimeError("DefinitionObjects chunks element was not found.")

    object_elements = object_chunks_element.findall("chunk")
    if len(object_elements) < 2:
        raise RuntimeError("At least two Object chunks are required for GUID duplication.")

    first_container = object_elements[0].find('./chunks/chunk[@name="Container"]')
    second_container = object_elements[1].find('./chunks/chunk[@name="Container"]')
    if first_container is None or second_container is None:
        raise RuntimeError("Container chunks were not found.")

    first_instance_guid_item = first_container.find('./items/item[@name="InstanceGuid"]')
    second_instance_guid_item = second_container.find('./items/item[@name="InstanceGuid"]')
    if first_instance_guid_item is None or second_instance_guid_item is None:
        raise RuntimeError("InstanceGuid items were not found.")

    second_instance_guid_item.text = first_instance_guid_item.text


def mutate_unresolved_source_guid(root_element: element_tree.Element) -> None:
    """Point the first Source item at a GUID that does not exist."""
    for item_element in root_element.iter("item"):
        if item_element.get("name") != "Source":
            continue
        item_element.text = "00000000-0000-0000-0000-000000000099"
        return
    raise RuntimeError("No Source item was found to mutate.")


def mutate_gha_libraries_count(
    root_element: element_tree.Element,
    stale_library_count: int,
) -> None:
    """Set GHALibraries Count to a stale value."""
    definition_element = root_element.find('./chunks/chunk[@name="Definition"]')
    if definition_element is None:
        raise RuntimeError("Definition chunk was not found.")

    gha_libraries_element = definition_element.find('./chunks/chunk[@name="GHALibraries"]')
    if gha_libraries_element is None:
        raise RuntimeError("GHALibraries chunk was not found.")

    library_count_item = gha_libraries_element.find('./items/item[@name="Count"]')
    if library_count_item is None:
        raise RuntimeError("GHALibraries Count item was not found.")
    library_count_item.text = str(stale_library_count)


def _find_definition_objects_element(root_element: element_tree.Element) -> element_tree.Element:
    definition_objects_element = root_element.find(
        './chunks/chunk[@name="Definition"]/chunks/chunk[@name="DefinitionObjects"]'
    )
    if definition_objects_element is None:
        raise RuntimeError("DefinitionObjects chunk was not found.")
    return definition_objects_element
