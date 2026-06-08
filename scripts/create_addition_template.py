"""Create Logger-free addition_compute.ghx from tests/fixtures/addition.ghx."""

from __future__ import annotations

import xml.etree.ElementTree as element_tree
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = REPOSITORY_ROOT / "tests" / "fixtures" / "addition.ghx"
OUTPUT_PATH = REPOSITORY_ROOT / "src" / "pyghx" / "templates" / "addition_compute.ghx"
LOGGER_MANAGER_COMPONENT_NAME = "LoggerManager"
LOGGER_LIBRARY_NAME = "Logger"
ADDITION_COMPUTE_DOCUMENT_NAME = "addition_compute.ghx"


def create_addition_compute_template() -> Path:
    root_element = element_tree.parse(SOURCE_PATH).getroot()
    definition_element = _find_child_chunk(root_element, "Definition")
    if definition_element is None:
        raise RuntimeError("Definition chunk was not found in addition fixture.")

    _remove_archive_thumbnail(root_element)
    _remove_logger_library(definition_element)
    _remove_logger_manager_object(definition_element)
    _update_definition_name(definition_element, ADDITION_COMPUTE_DOCUMENT_NAME)
    _refresh_chunk_counts(root_element)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    element_tree.indent(root_element, space="  ")
    element_tree.ElementTree(root_element).write(
        OUTPUT_PATH,
        encoding="utf-8",
        xml_declaration=True,
    )
    return OUTPUT_PATH


def _find_child_chunk(parent_element: element_tree.Element, chunk_name: str) -> element_tree.Element | None:
    chunks_element = parent_element.find("chunks")
    if chunks_element is None:
        return None

    for child_element in chunks_element.findall("chunk"):
        if child_element.get("name") == chunk_name:
            return child_element
    return None


def _remove_archive_thumbnail(root_element: element_tree.Element) -> None:
    archive_chunks_element = root_element.find("chunks")
    if archive_chunks_element is None:
        raise RuntimeError("Archive chunks element was not found.")

    for child_element in list(archive_chunks_element.findall("chunk")):
        if child_element.get("name") == "Thumbnail":
            archive_chunks_element.remove(child_element)


def _remove_logger_library(definition_element: element_tree.Element) -> None:
    gha_libraries_element = _find_child_chunk(definition_element, "GHALibraries")
    if gha_libraries_element is None:
        raise RuntimeError("GHALibraries chunk was not found.")

    library_chunks_element = gha_libraries_element.find("chunks")
    if library_chunks_element is None:
        raise RuntimeError("GHALibraries chunks element was not found.")

    for library_element in list(library_chunks_element.findall("chunk")):
        library_name_item = library_element.find('./items/item[@name="Name"]')
        if library_name_item is not None and library_name_item.text == LOGGER_LIBRARY_NAME:
            library_chunks_element.remove(library_element)


def _remove_logger_manager_object(definition_element: element_tree.Element) -> None:
    definition_objects_element = _find_child_chunk(definition_element, "DefinitionObjects")
    if definition_objects_element is None:
        raise RuntimeError("DefinitionObjects chunk was not found.")

    object_chunks_element = definition_objects_element.find("chunks")
    if object_chunks_element is None:
        raise RuntimeError("DefinitionObjects chunks element was not found.")

    for object_element in list(object_chunks_element.findall("chunk")):
        object_name_item = object_element.find('./items/item[@name="Name"]')
        if object_name_item is not None and object_name_item.text == LOGGER_MANAGER_COMPONENT_NAME:
            object_chunks_element.remove(object_element)

    remaining_object_count = len(object_chunks_element.findall("chunk"))
    object_count_item = definition_objects_element.find('./items/item[@name="ObjectCount"]')
    if object_count_item is None:
        raise RuntimeError("ObjectCount item was not found.")
    object_count_item.text = str(remaining_object_count)

    for object_index, object_element in enumerate(object_chunks_element.findall("chunk")):
        object_element.set("index", str(object_index))


def _update_definition_name(definition_element: element_tree.Element, document_name: str) -> None:
    definition_properties_element = _find_child_chunk(definition_element, "DefinitionProperties")
    if definition_properties_element is None:
        raise RuntimeError("DefinitionProperties chunk was not found.")

    document_name_item = definition_properties_element.find('./items/item[@name="Name"]')
    if document_name_item is None:
        raise RuntimeError("DefinitionProperties Name item was not found.")
    document_name_item.text = document_name


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


if __name__ == "__main__":
    template_path = create_addition_compute_template()
    print(template_path)
