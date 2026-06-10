"""GHX XML structural integrity diagnostics and metadata refresh helpers."""

from __future__ import annotations

import xml.etree.ElementTree as element_tree
from collections import Counter
from pathlib import Path
from typing import Any

from pyghx.loader import GhxDocument, GhxLoadError, load_ghx_document

DIAGNOSTIC_LEVEL_ERROR = "error"
DIAGNOSTIC_LEVEL_WARNING = "warning"

GHALIBRARIES_CHUNK_NAME = "GHALibraries"
LIBRARY_CHUNK_NAME = "Library"
DEFINITION_OBJECTS_CHUNK_NAME = "DefinitionObjects"
OBJECT_CHUNK_NAME = "Object"
OBJECT_COUNT_ITEM_NAME = "ObjectCount"
LIBRARY_COUNT_ITEM_NAME = "Count"
INSTANCE_GUID_ITEM_NAME = "InstanceGuid"
SOURCE_ITEM_NAME = "Source"


def build_ghx_integrity_diagnostics(source_path: Path | str) -> list[dict[str, str]]:
    """Return structural integrity diagnostics for one GHX file."""
    path = Path(source_path)
    try:
        document = load_ghx_document(path)
    except GhxLoadError as load_error:
        return [
            {
                "level": DIAGNOSTIC_LEVEL_ERROR,
                "code": "xml_parse_error",
                "message": str(load_error),
            }
        ]

    root_element = element_tree.parse(path).getroot()
    return build_ghx_integrity_diagnostics_from_document(document, root_element)


def build_ghx_integrity_diagnostics_from_document(
    document: GhxDocument,
    root_element: element_tree.Element,
) -> list[dict[str, str]]:
    """Return structural integrity diagnostics from a loaded document and XML root."""
    diagnostics: list[dict[str, str]] = []
    diagnostics.extend(_build_items_and_chunks_count_diagnostics(root_element))
    diagnostics.extend(_build_definition_objects_diagnostics(root_element))
    diagnostics.extend(_build_instance_guid_diagnostics(root_element))
    diagnostics.extend(_build_source_wiring_diagnostics(root_element))
    diagnostics.extend(_build_gha_libraries_count_diagnostics(root_element))
    _ = document  # document reserved for future checks tied to parsed objects
    return diagnostics


def has_preflight_blocking_integrity_errors(diagnostics: list[dict[str, str]]) -> bool:
    """Return True when any integrity diagnostic is an error-level blocker."""
    return any(
        diagnostic["level"] == DIAGNOSTIC_LEVEL_ERROR
        for diagnostic in diagnostics
    )


def refresh_definition_object_chunk_metadata(definition_objects_element: element_tree.Element) -> None:
    """Sync DefinitionObjects ObjectCount and Object chunk indices with actual children."""
    object_chunks_element = definition_objects_element.find("chunks")
    if object_chunks_element is None:
        return

    object_elements = object_chunks_element.findall("chunk")
    object_chunks_element.set("count", str(len(object_elements)))
    for object_index, object_element in enumerate(object_elements):
        object_element.set("index", str(object_index))

    object_count_item = definition_objects_element.find(
        f'./items/item[@name="{OBJECT_COUNT_ITEM_NAME}"]'
    )
    if object_count_item is not None:
        object_count_item.text = str(len(object_elements))


def refresh_gha_libraries_count(definition_element: element_tree.Element) -> None:
    """Sync GHALibraries Count with the number of Library chunks."""
    gha_libraries_element = _find_child_chunk_element(definition_element, GHALIBRARIES_CHUNK_NAME)
    if gha_libraries_element is None:
        return

    library_chunks_element = gha_libraries_element.find("chunks")
    if library_chunks_element is None:
        return

    library_count_item = gha_libraries_element.find(
        f'./items/item[@name="{LIBRARY_COUNT_ITEM_NAME}"]'
    )
    if library_count_item is None:
        return

    library_count_item.text = str(len(library_chunks_element.findall("chunk")))


def _build_items_and_chunks_count_diagnostics(
    root_element: element_tree.Element,
) -> list[dict[str, str]]:
    diagnostics: list[dict[str, str]] = []
    for items_element in root_element.iter("items"):
        declared_count_text = items_element.get("count")
        if declared_count_text is None:
            continue

        actual_count = len(items_element.findall("item"))
        declared_count = _parse_non_negative_int(declared_count_text)
        if declared_count is None:
            continue

        if declared_count != actual_count:
            diagnostics.append(
                _warning_diagnostic(
                    code="items_count_mismatch",
                    message=(
                        f"items/@count is {declared_count} but {actual_count} "
                        "direct item children were found."
                    ),
                )
            )

    for chunks_element in root_element.iter("chunks"):
        declared_count_text = chunks_element.get("count")
        if declared_count_text is None:
            continue

        parent_chunk = chunks_element.find("..")
        parent_name = parent_chunk.get("name") if parent_chunk is not None else "unknown"
        if parent_name == DEFINITION_OBJECTS_CHUNK_NAME:
            continue

        actual_count = len(chunks_element.findall("chunk"))
        declared_count = _parse_non_negative_int(declared_count_text)
        if declared_count is None:
            continue

        if declared_count != actual_count:
            diagnostics.append(
                _warning_diagnostic(
                    code="chunks_count_mismatch",
                    message=(
                        f"chunks/@count is {declared_count} under {parent_name!r} "
                        f"but {actual_count} direct chunk children were found."
                    ),
                )
            )

    return diagnostics


def _build_definition_objects_diagnostics(
    root_element: element_tree.Element,
) -> list[dict[str, str]]:
    definition_objects_element = _find_child_chunk_element(
        root_element,
        DEFINITION_OBJECTS_CHUNK_NAME,
    )
    if definition_objects_element is None:
        return []

    diagnostics: list[dict[str, str]] = []
    object_chunks_element = definition_objects_element.find("chunks")
    if object_chunks_element is None:
        return diagnostics

    object_elements = [
        chunk_element
        for chunk_element in object_chunks_element.findall("chunk")
        if chunk_element.get("name") == OBJECT_CHUNK_NAME
    ]
    actual_object_count = len(object_elements)

    object_count_item = definition_objects_element.find(
        f'./items/item[@name="{OBJECT_COUNT_ITEM_NAME}"]'
    )
    if object_count_item is not None and object_count_item.text is not None:
        declared_object_count = _parse_non_negative_int(object_count_item.text)
        if (
            declared_object_count is not None
            and declared_object_count != actual_object_count
        ):
            diagnostics.append(
                _error_diagnostic(
                    code="object_count_mismatch",
                    message=(
                        f"DefinitionObjects ObjectCount is {declared_object_count} "
                        f"but {actual_object_count} Object chunks were found."
                    ),
                )
            )

    declared_chunks_count_text = object_chunks_element.get("count")
    if declared_chunks_count_text is not None:
        declared_chunks_count = _parse_non_negative_int(declared_chunks_count_text)
        actual_chunks_count = len(object_chunks_element.findall("chunk"))
        if (
            declared_chunks_count is not None
            and declared_chunks_count != actual_chunks_count
        ):
            diagnostics.append(
                _error_diagnostic(
                    code="definition_objects_chunks_count_mismatch",
                    message=(
                        f"DefinitionObjects chunks/@count is {declared_chunks_count} "
                        f"but {actual_chunks_count} Object chunks were found."
                    ),
                )
            )

    object_index_values: list[int] = []
    for object_element in object_elements:
        index_text = object_element.get("index")
        if index_text is None:
            diagnostics.append(
                _error_diagnostic(
                    code="object_index_missing",
                    message="An Object chunk is missing an index attribute.",
                )
            )
            continue

        parsed_index = _parse_non_negative_int(index_text)
        if parsed_index is None:
            diagnostics.append(
                _error_diagnostic(
                    code="object_index_invalid",
                    message=f"Object chunk index {index_text!r} is not a non-negative integer.",
                )
            )
            continue

        object_index_values.append(parsed_index)

    if object_index_values:
        expected_indices = list(range(len(object_index_values)))
        if sorted(object_index_values) != expected_indices:
            diagnostics.append(
                _error_diagnostic(
                    code="object_index_mismatch",
                    message=(
                        "DefinitionObjects Object chunk indices must be contiguous "
                        f"from 0 to {len(object_index_values) - 1}; found {sorted(object_index_values)}."
                    ),
                )
            )

        duplicate_indices = [
            index_value
            for index_value, occurrence_count in Counter(object_index_values).items()
            if occurrence_count > 1
        ]
        if duplicate_indices:
            diagnostics.append(
                _error_diagnostic(
                    code="object_index_duplicate",
                    message=(
                        "DefinitionObjects Object chunk indices must be unique; "
                        f"duplicates: {sorted(duplicate_indices)}."
                    ),
                )
            )

    return diagnostics


def _build_instance_guid_diagnostics(
    root_element: element_tree.Element,
) -> list[dict[str, str]]:
    instance_guid_values = [
        item_element.text
        for item_element in root_element.iter("item")
        if item_element.get("name") == INSTANCE_GUID_ITEM_NAME and item_element.text
    ]
    duplicate_guids = [
        guid_value
        for guid_value, occurrence_count in Counter(instance_guid_values).items()
        if occurrence_count > 1
    ]
    if not duplicate_guids:
        return []

    return [
        _error_diagnostic(
            code="duplicate_instance_guid",
            message=(
                "Duplicate InstanceGuid values were found: "
                + ", ".join(sorted(duplicate_guids))
            ),
        )
    ]


def _build_source_wiring_diagnostics(
    root_element: element_tree.Element,
) -> list[dict[str, str]]:
    instance_guid_values = {
        item_element.text
        for item_element in root_element.iter("item")
        if item_element.get("name") == INSTANCE_GUID_ITEM_NAME and item_element.text
    }
    unresolved_source_guids: list[str] = []
    for item_element in root_element.iter("item"):
        if item_element.get("name") != SOURCE_ITEM_NAME:
            continue
        if not item_element.text:
            continue
        if item_element.text not in instance_guid_values:
            unresolved_source_guids.append(item_element.text)

    if not unresolved_source_guids:
        return []

    return [
        _error_diagnostic(
            code="unresolved_source_guid",
            message=(
                "Source GUIDs do not resolve to any InstanceGuid: "
                + ", ".join(sorted(set(unresolved_source_guids)))
            ),
        )
    ]


def _build_gha_libraries_count_diagnostics(
    root_element: element_tree.Element,
) -> list[dict[str, str]]:
    definition_element = _find_child_chunk_element(root_element, "Definition")
    if definition_element is None:
        return []

    gha_libraries_element = _find_child_chunk_element(definition_element, GHALIBRARIES_CHUNK_NAME)
    if gha_libraries_element is None:
        return []

    library_count_item = gha_libraries_element.find(
        f'./items/item[@name="{LIBRARY_COUNT_ITEM_NAME}"]'
    )
    library_chunks_element = gha_libraries_element.find("chunks")
    if library_count_item is None or library_count_item.text is None:
        return []
    if library_chunks_element is None:
        return []

    declared_library_count = _parse_non_negative_int(library_count_item.text)
    actual_library_count = len(
        [
            chunk_element
            for chunk_element in library_chunks_element.findall("chunk")
            if chunk_element.get("name") == LIBRARY_CHUNK_NAME
        ]
    )
    if declared_library_count is None:
        return []

    if declared_library_count != actual_library_count:
        return [
            _warning_diagnostic(
                code="library_count_mismatch",
                message=(
                    f"GHALibraries Count is {declared_library_count} "
                    f"but {actual_library_count} Library chunks were found."
                ),
            )
        ]

    return []


def _find_child_chunk_element(
    parent_element: element_tree.Element,
    chunk_name: str,
) -> element_tree.Element | None:
    if parent_element.tag == "Archive":
        if chunk_name == "Definition":
            return parent_element.find('./chunks/chunk[@name="Definition"]')
        if chunk_name == DEFINITION_OBJECTS_CHUNK_NAME:
            return parent_element.find(
                './chunks/chunk[@name="Definition"]/chunks/chunk[@name="DefinitionObjects"]'
            )
        if chunk_name == GHALIBRARIES_CHUNK_NAME:
            return parent_element.find(
                './chunks/chunk[@name="Definition"]/chunks/chunk[@name="GHALibraries"]'
            )
        return None

    chunks_element = parent_element.find("chunks")
    if chunks_element is None:
        return None

    for child_element in chunks_element.findall("chunk"):
        if child_element.get("name") == chunk_name:
            return child_element
    return None


def _parse_non_negative_int(raw_value: str) -> int | None:
    try:
        parsed_value = int(raw_value)
    except ValueError:
        return None
    if parsed_value < 0:
        return None
    return parsed_value


def _error_diagnostic(code: str, message: str) -> dict[str, str]:
    return {
        "level": DIAGNOSTIC_LEVEL_ERROR,
        "code": code,
        "message": message,
    }


def _warning_diagnostic(code: str, message: str) -> dict[str, str]:
    return {
        "level": DIAGNOSTIC_LEVEL_WARNING,
        "code": code,
        "message": message,
    }
