"""Create import_two_models.ghx with two Import 3DM chains for RhinoCompute tests."""

from __future__ import annotations

import copy
import uuid
import xml.etree.ElementTree as element_tree
from pathlib import Path

from pyghx.ghx_integrity import (
    refresh_definition_object_chunk_metadata,
    refresh_gha_libraries_count,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = REPOSITORY_ROOT / "tests" / "fixtures" / "import_model.ghx"
OUTPUT_PATH = REPOSITORY_ROOT / "tests" / "fixtures" / "import_two_models.ghx"
IMPORT_TWO_MODELS_DOCUMENT_NAME = "import_two_models.ghx"
TARGET_FILE_PATH_NICKNAME = "Target"
OBSTACLE_FILE_PATH_NICKNAME = "Obstacle"
TARGET_IMPORT_NICKNAME = "Import Target"
OBSTACLE_IMPORT_NICKNAME = "Import Obstacle"
TARGET_GEOMETRY_PARAM_NICKNAME = "TargetGeometry"
OBSTACLE_GEOMETRY_PARAM_NICKNAME = "ObstacleGeometry"
CONTEXT_BAKE_CONTENT_PARAM_NICKNAME = "Content"
VERTICAL_LAYOUT_OFFSET = 120
LOGGER_MANAGER_COMPONENT_NAME = "LoggerManager"
LOGGER_LIBRARY_NAME = "Logger"


def create_import_two_models_fixture() -> Path:
    root_element = element_tree.parse(SOURCE_PATH).getroot()
    definition_element = _find_child_chunk(root_element, "Definition")
    if definition_element is None:
        raise RuntimeError("Definition chunk was not found in import_model fixture.")

    _remove_archive_thumbnail(root_element)
    _remove_logger_library(definition_element)
    _remove_logger_manager_object(definition_element)
    _update_definition_name(definition_element, IMPORT_TWO_MODELS_DOCUMENT_NAME)

    definition_objects_element = _find_child_chunk(definition_element, "DefinitionObjects")
    if definition_objects_element is None:
        raise RuntimeError("DefinitionObjects chunk was not found.")

    object_chunks_element = definition_objects_element.find("chunks")
    if object_chunks_element is None:
        raise RuntimeError("DefinitionObjects chunks element was not found.")

    import_object_element = _find_object_chunk_by_component_name(object_chunks_element, "Import 3DM")
    file_path_object_element = _find_object_chunk_by_component_name(object_chunks_element, "Get File Path")
    context_bake_object_element = _find_object_chunk_by_component_name(object_chunks_element, "Context Bake")
    if import_object_element is None or file_path_object_element is None or context_bake_object_element is None:
        raise RuntimeError("Import chain objects were not found in import_model fixture.")

    obstacle_import_object_element = copy.deepcopy(import_object_element)
    obstacle_file_path_object_element = copy.deepcopy(file_path_object_element)
    obstacle_context_bake_object_element = copy.deepcopy(context_bake_object_element)

    _assign_import_chain(
        import_object_element=import_object_element,
        file_path_object_element=file_path_object_element,
        context_bake_object_element=context_bake_object_element,
        file_path_nickname=TARGET_FILE_PATH_NICKNAME,
        import_nickname=TARGET_IMPORT_NICKNAME,
        geometry_param_nickname=TARGET_GEOMETRY_PARAM_NICKNAME,
        vertical_offset=0,
    )

    _assign_import_chain(
        import_object_element=obstacle_import_object_element,
        file_path_object_element=obstacle_file_path_object_element,
        context_bake_object_element=obstacle_context_bake_object_element,
        file_path_nickname=OBSTACLE_FILE_PATH_NICKNAME,
        import_nickname=OBSTACLE_IMPORT_NICKNAME,
        geometry_param_nickname=OBSTACLE_GEOMETRY_PARAM_NICKNAME,
        vertical_offset=VERTICAL_LAYOUT_OFFSET,
    )

    object_chunks_element.append(obstacle_import_object_element)
    object_chunks_element.append(obstacle_file_path_object_element)
    object_chunks_element.append(obstacle_context_bake_object_element)

    object_count_item = definition_objects_element.find('./items/item[@name="ObjectCount"]')
    if object_count_item is None:
        raise RuntimeError("ObjectCount item was not found.")
    refresh_definition_object_chunk_metadata(definition_objects_element)
    refresh_gha_libraries_count(definition_element)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    element_tree.indent(root_element, space="  ")
    element_tree.ElementTree(root_element).write(
        OUTPUT_PATH,
        encoding="utf-8",
        xml_declaration=True,
    )
    return OUTPUT_PATH


def _assign_import_chain(
    import_object_element: element_tree.Element,
    file_path_object_element: element_tree.Element,
    context_bake_object_element: element_tree.Element,
    file_path_nickname: str,
    import_nickname: str,
    geometry_param_nickname: str,
    vertical_offset: int,
) -> dict[str, str]:
    file_path_instance_guid = str(uuid.uuid4())
    import_instance_guid = str(uuid.uuid4())
    import_file_input_guid = str(uuid.uuid4())
    import_geometry_output_guid = str(uuid.uuid4())
    context_bake_instance_guid = str(uuid.uuid4())
    context_bake_content_input_guid = str(uuid.uuid4())

    _set_container_nickname(file_path_object_element, file_path_nickname)
    _set_container_item_text(file_path_object_element, "InstanceGuid", file_path_instance_guid)
    _offset_bounds(file_path_object_element, vertical_offset)

    _set_container_nickname(import_object_element, import_nickname)
    _set_container_item_text(import_object_element, "InstanceGuid", import_instance_guid)
    _set_param_item_text(import_object_element, "File", "InstanceGuid", import_file_input_guid)
    _set_param_item_text(import_object_element, "File", "Source", file_path_instance_guid)
    _set_param_item_text(import_object_element, "Layer", "InstanceGuid", str(uuid.uuid4()))
    _set_param_item_text(import_object_element, "Name", "InstanceGuid", str(uuid.uuid4()))
    _set_param_item_text(import_object_element, "Geometry", "InstanceGuid", import_geometry_output_guid)
    _offset_bounds(import_object_element, vertical_offset)

    _set_container_item_text(context_bake_object_element, "InstanceGuid", context_bake_instance_guid)
    _set_param_item_text(
        context_bake_object_element,
        CONTEXT_BAKE_CONTENT_PARAM_NICKNAME,
        "InstanceGuid",
        context_bake_content_input_guid,
    )
    _set_param_item_text(
        context_bake_object_element,
        CONTEXT_BAKE_CONTENT_PARAM_NICKNAME,
        "Source",
        import_geometry_output_guid,
    )
    _set_param_item_text(
        context_bake_object_element,
        CONTEXT_BAKE_CONTENT_PARAM_NICKNAME,
        "Name",
        geometry_param_nickname,
    )
    _set_param_item_text(
        context_bake_object_element,
        geometry_param_nickname,
        "NickName",
        geometry_param_nickname,
        match_item_name="Name",
    )
    _offset_bounds(context_bake_object_element, vertical_offset)

    return {
        "file_path_instance_guid": file_path_instance_guid,
        "import_instance_guid": import_instance_guid,
        "import_geometry_output_guid": import_geometry_output_guid,
        "context_bake_instance_guid": context_bake_instance_guid,
    }


def _find_child_chunk(parent_element: element_tree.Element, chunk_name: str) -> element_tree.Element | None:
    chunks_element = parent_element.find("chunks")
    if chunks_element is None:
        return None

    for child_element in chunks_element.findall("chunk"):
        if child_element.get("name") == chunk_name:
            return child_element
    return None


def _find_object_chunk_by_component_name(
    object_chunks_element: element_tree.Element,
    component_name: str,
) -> element_tree.Element | None:
    for object_element in object_chunks_element.findall("chunk"):
        name_item = object_element.find('./items/item[@name="Name"]')
        if name_item is not None and name_item.text == component_name:
            return object_element
    return None


def _set_container_nickname(object_element: element_tree.Element, nickname: str) -> None:
    container_element = object_element.find('./chunks/chunk[@name="Container"]')
    if container_element is None:
        raise RuntimeError("Container chunk was not found.")
    _set_item_text(container_element, "NickName", nickname)


def _set_container_item_text(
    object_element: element_tree.Element,
    item_name: str,
    item_text: str,
) -> None:
    container_element = object_element.find('./chunks/chunk[@name="Container"]')
    if container_element is None:
        raise RuntimeError("Container chunk was not found.")
    _set_item_text(container_element, item_name, item_text)


def _set_item_text(
    parent_element: element_tree.Element,
    item_name: str,
    item_text: str,
) -> None:
    item_element = parent_element.find(f'./items/item[@name="{item_name}"]')
    if item_element is None:
        raise RuntimeError(f"Item {item_name!r} was not found.")
    item_element.text = item_text


def _set_param_item_text(
    object_element: element_tree.Element,
    parameter_lookup_value: str,
    item_name: str,
    item_text: str,
    match_item_name: str = "NickName",
) -> None:
    container_element = object_element.find('./chunks/chunk[@name="Container"]')
    if container_element is None:
        raise RuntimeError("Container chunk was not found.")

    container_chunks_element = container_element.find("chunks")
    if container_chunks_element is None:
        raise RuntimeError("Container chunks element was not found.")

    for parameter_chunk in container_chunks_element.findall("chunk"):
        chunk_name = parameter_chunk.get("name")
        if chunk_name not in {"param_input", "param_output"}:
            continue
        lookup_item = parameter_chunk.find(f'./items/item[@name="{match_item_name}"]')
        if lookup_item is None or lookup_item.text != parameter_lookup_value:
            continue
        item_element = parameter_chunk.find(f'./items/item[@name="{item_name}"]')
        if item_element is None:
            raise RuntimeError(
                f"Parameter {parameter_lookup_value!r} is missing item {item_name!r}."
            )
        item_element.text = item_text
        return

    raise RuntimeError(f"Parameter {parameter_lookup_value!r} was not found.")


def _offset_bounds(object_element: element_tree.Element, vertical_offset: int) -> None:
    if vertical_offset == 0:
        return

    container_element = object_element.find('./chunks/chunk[@name="Container"]')
    if container_element is None:
        return

    for bounds_element in container_element.iter("item"):
        if bounds_element.get("name") != "Bounds":
            continue
        y_element = bounds_element.find("Y")
        if y_element is not None and y_element.text is not None:
            y_element.text = str(int(float(y_element.text)) + vertical_offset)


def _remove_logger_library(definition_element: element_tree.Element) -> None:
    gha_libraries_element = _find_child_chunk(definition_element, "GHALibraries")
    if gha_libraries_element is None:
        return

    library_chunks_element = gha_libraries_element.find("chunks")
    if library_chunks_element is None:
        return

    for library_element in list(library_chunks_element.findall("chunk")):
        library_name_item = library_element.find('./items/item[@name="Name"]')
        if library_name_item is not None and library_name_item.text == LOGGER_LIBRARY_NAME:
            library_chunks_element.remove(library_element)

    refresh_gha_libraries_count(definition_element)


def _remove_logger_manager_object(definition_element: element_tree.Element) -> None:
    definition_objects_element = _find_child_chunk(definition_element, "DefinitionObjects")
    if definition_objects_element is None:
        return

    object_chunks_element = definition_objects_element.find("chunks")
    if object_chunks_element is None:
        return

    for object_element in list(object_chunks_element.findall("chunk")):
        name_item = object_element.find('./items/item[@name="Name"]')
        if name_item is not None and name_item.text == LOGGER_MANAGER_COMPONENT_NAME:
            object_chunks_element.remove(object_element)

    refresh_definition_object_chunk_metadata(definition_objects_element)


def _remove_archive_thumbnail(root_element: element_tree.Element) -> None:
    archive_chunks_element = root_element.find("chunks")
    if archive_chunks_element is None:
        return

    for child_element in list(archive_chunks_element.findall("chunk")):
        if child_element.get("name") == "Thumbnail":
            archive_chunks_element.remove(child_element)


def _update_definition_name(definition_element: element_tree.Element, document_name: str) -> None:
    definition_properties_element = _find_child_chunk(definition_element, "DefinitionProperties")
    if definition_properties_element is None:
        raise RuntimeError("DefinitionProperties chunk was not found.")
    name_item = definition_properties_element.find('./items/item[@name="Name"]')
    if name_item is None:
        raise RuntimeError("DefinitionProperties Name item was not found.")
    name_item.text = document_name


if __name__ == "__main__":
    fixture_path = create_import_two_models_fixture()
    print(fixture_path)
