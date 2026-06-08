"""Extract subgraph patterns from reference GHX files into local catalogs."""

from __future__ import annotations

import xml.etree.ElementTree as element_tree
from pathlib import Path

from pyghx.inspect import inspect_document
from pyghx.loader import load_ghx_document
from pyghx.reference.catalog import (
    CATALOG_FILENAME,
    CATALOG_SCHEMA_VERSION,
    PatternCatalog,
    PatternCatalogEntry,
    save_pattern_catalog,
)
from pyghx.reference.patterns import detect_patterns
from pyghx.validate import validate_document

LOGGER_MANAGER_COMPONENT_NAME = "LoggerManager"
LOGGER_LIBRARY_NAME = "Logger"
GROUP_COMPONENT_NAME = "Group"


def extract_patterns(
    source_path: Path | str,
    output_dir: Path | str,
    exclude_embedded_geometry: bool = True,
) -> Path:
    """Extract patterns from a reference GHX into a local catalog directory."""
    source_file_path = Path(source_path)
    output_directory = Path(output_dir)
    output_directory.mkdir(parents=True, exist_ok=True)

    document = load_ghx_document(source_file_path)
    pattern_candidates = detect_patterns(
        document,
        exclude_embedded_geometry=exclude_embedded_geometry,
    )
    pattern_ids = [pattern_candidate.pattern_id for pattern_candidate in pattern_candidates]
    if len(pattern_ids) != len(set(pattern_ids)):
        raise RuntimeError("Duplicate pattern_id values were detected during extraction.")

    catalog_entries: list[PatternCatalogEntry] = []
    for pattern_candidate in pattern_candidates:
        pattern_filename = f"{pattern_candidate.pattern_id}.ghx"
        pattern_output_path = output_directory / pattern_filename
        build_pattern_ghx(
            source_file_path=source_file_path,
            member_instance_guids=pattern_candidate.member_instance_guids,
            output_path=pattern_output_path,
            document_name=pattern_filename,
        )

        pattern_summary = inspect_document(pattern_output_path)
        validation_result = validate_document(pattern_output_path)
        compute_inputs = pattern_summary["compute_contract"]["inputs"]
        rhino_compute_ready = (
            validation_result.valid
            and bool(compute_inputs)
            and all(input_entry["supported"] for input_entry in compute_inputs)
        )
        catalog_entries.append(
            PatternCatalogEntry(
                pattern_id=pattern_candidate.pattern_id,
                title=pattern_candidate.title,
                pattern_ghx=pattern_filename,
                object_count=pattern_summary["object_count"],
                valid=validation_result.valid,
                rhino_compute_ready=rhino_compute_ready,
                geometry_embedded=pattern_candidate.geometry_embedded,
                compute_contract=pattern_summary["compute_contract"],
                boundary_inputs=_build_boundary_inputs(pattern_summary),
            )
        )

    catalog = PatternCatalog(
        schema_version=CATALOG_SCHEMA_VERSION,
        source_basename=source_file_path.name,
        patterns=tuple(catalog_entries),
    )
    catalog_path = output_directory / CATALOG_FILENAME
    save_pattern_catalog(catalog, catalog_path)
    return catalog_path


def build_pattern_ghx(
    source_file_path: Path,
    member_instance_guids: set[str] | frozenset[str],
    output_path: Path,
    document_name: str,
) -> Path:
    """Build one pattern GHX containing only selected instance GUID objects."""
    root_element = element_tree.parse(source_file_path).getroot()
    definition_element = _find_child_chunk_element(root_element, "Definition")
    if definition_element is None:
        raise RuntimeError("Definition chunk was not found in reference GHX.")

    _remove_archive_thumbnail(root_element)
    _remove_logger_library(definition_element)
    _remove_logger_manager_object(definition_element)
    _filter_definition_objects(definition_element, set(member_instance_guids))
    _update_definition_name(definition_element, document_name)
    _refresh_chunk_counts(root_element)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    element_tree.indent(root_element, space="  ")
    element_tree.ElementTree(root_element).write(
        output_path,
        encoding="utf-8",
        xml_declaration=True,
    )
    return output_path


def _build_boundary_inputs(pattern_summary: dict) -> list[dict]:
    compute_contract = pattern_summary.get("compute_contract", {})
    return list(compute_contract.get("inputs", []))


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


def _remove_archive_thumbnail(root_element: element_tree.Element) -> None:
    archive_chunks_element = root_element.find("chunks")
    if archive_chunks_element is None:
        return

    for child_element in list(archive_chunks_element.findall("chunk")):
        if child_element.get("name") == "Thumbnail":
            archive_chunks_element.remove(child_element)


def _remove_logger_library(definition_element: element_tree.Element) -> None:
    gha_libraries_element = _find_child_chunk_element(definition_element, "GHALibraries")
    if gha_libraries_element is None:
        return

    library_chunks_element = gha_libraries_element.find("chunks")
    if library_chunks_element is None:
        return

    for library_element in list(library_chunks_element.findall("chunk")):
        library_name_item = library_element.find('./items/item[@name="Name"]')
        if library_name_item is not None and library_name_item.text == LOGGER_LIBRARY_NAME:
            library_chunks_element.remove(library_element)


def _remove_logger_manager_object(definition_element: element_tree.Element) -> None:
    definition_objects_element = _find_child_chunk_element(definition_element, "DefinitionObjects")
    if definition_objects_element is None:
        return

    object_chunks_element = definition_objects_element.find("chunks")
    if object_chunks_element is None:
        return

    for object_element in list(object_chunks_element.findall("chunk")):
        object_name_item = object_element.find('./items/item[@name="Name"]')
        if object_name_item is None:
            continue
        if object_name_item.text != LOGGER_MANAGER_COMPONENT_NAME:
            continue
        object_chunks_element.remove(object_element)


def _filter_definition_objects(
    definition_element: element_tree.Element,
    member_instance_guids: set[str],
) -> None:
    definition_objects_element = _find_child_chunk_element(definition_element, "DefinitionObjects")
    if definition_objects_element is None:
        raise RuntimeError("DefinitionObjects chunk was not found.")

    object_chunks_element = definition_objects_element.find("chunks")
    if object_chunks_element is None:
        raise RuntimeError("DefinitionObjects chunks element was not found.")

    retained_object_elements: list[element_tree.Element] = []
    for object_element in object_chunks_element.findall("chunk"):
        if object_element.get("name") != "Object":
            continue

        object_name_item = object_element.find('./items/item[@name="Name"]')
        if object_name_item is not None and object_name_item.text == GROUP_COMPONENT_NAME:
            continue

        instance_guid_item = object_element.find(
            './chunks/chunk[@name="Container"]/items/item[@name="InstanceGuid"]'
        )
        if instance_guid_item is None or instance_guid_item.text not in member_instance_guids:
            continue

        retained_object_elements.append(object_element)

    for object_element in list(object_chunks_element.findall("chunk")):
        object_chunks_element.remove(object_element)

    for object_index, object_element in enumerate(retained_object_elements):
        object_element.set("index", str(object_index))
        object_chunks_element.append(object_element)

    object_count_item = definition_objects_element.find('./items/item[@name="ObjectCount"]')
    if object_count_item is None:
        raise RuntimeError("ObjectCount item was not found.")
    object_count_item.text = str(len(retained_object_elements))


def _update_definition_name(definition_element: element_tree.Element, document_name: str) -> None:
    definition_properties_element = _find_child_chunk_element(
        definition_element,
        "DefinitionProperties",
    )
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
