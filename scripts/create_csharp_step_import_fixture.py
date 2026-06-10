"""Create csharp_step_import.ghx: STEP import through C# Script to Context Bake."""

from __future__ import annotations

import copy
import uuid
import xml.etree.ElementTree as element_tree
from pathlib import Path

from pyghx.ghx_integrity import (
    refresh_definition_object_chunk_metadata,
    refresh_gha_libraries_count,
)
from pyghx.script_component import encode_script_source_text

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
IMPORT_MODEL_SOURCE_PATH = REPOSITORY_ROOT / "tests" / "fixtures" / "import_model.ghx"
CSHARP_ADDITION_SOURCE_PATH = REPOSITORY_ROOT / "tests" / "fixtures" / "csharp_addition.ghx"
CSHARP_SCRIPT_SOURCE_PATH = REPOSITORY_ROOT / "scripts" / "demo_csharp_step_import.cs"
OUTPUT_PATH = REPOSITORY_ROOT / "tests" / "fixtures" / "csharp_step_import.ghx"
DOCUMENT_NAME = "csharp_step_import.ghx"
CONTEXT_BAKE_OUTPUT_PARAM_NICKNAME = "GeometryPieceCount"
CONTEXT_BAKE_CONTENT_PARAM_NICKNAME = "Content"
CSHARP_GEOMETRY_INPUT_NICKNAME = "geometry"
CSHARP_SCRIPT_OUTPUT_NICKNAME = "a"
LOGGER_MANAGER_COMPONENT_NAME = "LoggerManager"
LOGGER_LIBRARY_NAME = "Logger"
CSHARP_SCRIPT_COMPONENT_NAME = "C# Script"


def create_csharp_step_import_fixture() -> Path:
    import_root_element = element_tree.parse(IMPORT_MODEL_SOURCE_PATH).getroot()
    csharp_root_element = element_tree.parse(CSHARP_ADDITION_SOURCE_PATH).getroot()

    definition_element = _find_child_chunk(import_root_element, "Definition")
    if definition_element is None:
        raise RuntimeError("Definition chunk was not found in import_model fixture.")

    csharp_definition_element = _find_child_chunk(csharp_root_element, "Definition")
    if csharp_definition_element is None:
        raise RuntimeError("Definition chunk was not found in csharp_addition fixture.")

    _remove_archive_thumbnail(import_root_element)
    _remove_logger_library(definition_element)
    _remove_logger_manager_object(definition_element)
    _update_definition_name(definition_element, DOCUMENT_NAME)

    definition_objects_element = _find_child_chunk(definition_element, "DefinitionObjects")
    if definition_objects_element is None:
        raise RuntimeError("DefinitionObjects chunk was not found.")

    object_chunks_element = definition_objects_element.find("chunks")
    if object_chunks_element is None:
        raise RuntimeError("DefinitionObjects chunks element was not found.")

    csharp_object_chunks_element = _find_child_chunk(csharp_definition_element, "DefinitionObjects")
    if csharp_object_chunks_element is None:
        raise RuntimeError("DefinitionObjects chunk was not found in csharp_addition.")

    csharp_object_chunks = csharp_object_chunks_element.find("chunks")
    if csharp_object_chunks is None:
        raise RuntimeError("DefinitionObjects chunks element was not found in csharp_addition.")

    import_object_element = _find_object_chunk_by_component_name(object_chunks_element, "Import 3DM")
    context_bake_object_element = _find_object_chunk_by_component_name(object_chunks_element, "Context Bake")
    csharp_script_object_element = _find_object_chunk_by_component_name(
        csharp_object_chunks,
        CSHARP_SCRIPT_COMPONENT_NAME,
    )
    if import_object_element is None or context_bake_object_element is None:
        raise RuntimeError("Import chain objects were not found in import_model fixture.")
    if csharp_script_object_element is None:
        raise RuntimeError("C# Script object was not found in csharp_addition fixture.")

    csharp_script_copy_element = copy.deepcopy(csharp_script_object_element)
    import_geometry_output_guid = _read_param_instance_guid(import_object_element, "Geometry")
    script_instance_guid = str(uuid.uuid4())
    script_geometry_input_guid = str(uuid.uuid4())
    script_output_guid = str(uuid.uuid4())
    script_standard_output_guid = str(uuid.uuid4())
    context_bake_content_input_guid = str(uuid.uuid4())

    _set_container_item_text(csharp_script_copy_element, "InstanceGuid", script_instance_guid)
    _configure_single_geometry_input(
        csharp_script_object_element=csharp_script_copy_element,
        geometry_input_instance_guid=script_geometry_input_guid,
        import_geometry_output_guid=import_geometry_output_guid,
    )
    _set_script_output_guids(
        csharp_script_object_element=csharp_script_copy_element,
        script_output_instance_guid=script_output_guid,
        script_standard_output_instance_guid=script_standard_output_guid,
    )
    _embed_csharp_script_source(csharp_script_copy_element)

    _set_param_item_text(
        context_bake_object_element,
        CONTEXT_BAKE_CONTENT_PARAM_NICKNAME,
        "Source",
        script_output_guid,
    )
    _set_param_item_text(
        context_bake_object_element,
        CONTEXT_BAKE_CONTENT_PARAM_NICKNAME,
        "InstanceGuid",
        context_bake_content_input_guid,
    )
    _set_param_item_text(
        context_bake_object_element,
        CONTEXT_BAKE_CONTENT_PARAM_NICKNAME,
        "Name",
        CONTEXT_BAKE_OUTPUT_PARAM_NICKNAME,
        match_item_name="NickName",
    )
    _set_param_item_text(
        context_bake_object_element,
        CONTEXT_BAKE_OUTPUT_PARAM_NICKNAME,
        "NickName",
        CONTEXT_BAKE_OUTPUT_PARAM_NICKNAME,
        match_item_name="Name",
    )

    object_chunks_element.append(csharp_script_copy_element)
    refresh_definition_object_chunk_metadata(definition_objects_element)
    refresh_gha_libraries_count(definition_element)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    element_tree.indent(import_root_element, space="  ")
    element_tree.ElementTree(import_root_element).write(
        OUTPUT_PATH,
        encoding="utf-8",
        xml_declaration=True,
    )
    return OUTPUT_PATH


def _configure_single_geometry_input(
    csharp_script_object_element: element_tree.Element,
    geometry_input_instance_guid: str,
    import_geometry_output_guid: str,
) -> None:
    parameter_data_element = csharp_script_object_element.find(
        './chunks/chunk[@name="Container"]/chunks/chunk[@name="ParameterData"]'
    )
    if parameter_data_element is None:
        raise RuntimeError("C# Script ParameterData chunk was not found.")

    parameter_data_items_element = parameter_data_element.find("items")
    if parameter_data_items_element is None:
        raise RuntimeError("C# Script ParameterData items element was not found.")

    input_count_item = parameter_data_items_element.find('./item[@name="InputCount"]')
    if input_count_item is None:
        raise RuntimeError("C# Script InputCount item was not found.")
    input_count_item.text = "1"

    for input_id_item in list(parameter_data_items_element.findall('item[@name="InputId"]')):
        if input_id_item.get("index") != "0":
            parameter_data_items_element.remove(input_id_item)

    parameter_data_chunks_element = parameter_data_element.find("chunks")
    if parameter_data_chunks_element is None:
        raise RuntimeError("C# Script ParameterData chunks element was not found.")

    for input_param_element in list(parameter_data_chunks_element.findall('chunk[@name="InputParam"]')):
        if input_param_element.get("index") != "0":
            parameter_data_chunks_element.remove(input_param_element)

    geometry_input_element = parameter_data_chunks_element.find('chunk[@name="InputParam"][@index="0"]')
    if geometry_input_element is None:
        raise RuntimeError("C# Script geometry input parameter was not found.")

    _set_item_text(geometry_input_element, "InstanceGuid", geometry_input_instance_guid)
    _set_item_text(geometry_input_element, "Name", CSHARP_GEOMETRY_INPUT_NICKNAME)
    _set_item_text(geometry_input_element, "NickName", CSHARP_GEOMETRY_INPUT_NICKNAME)
    _set_item_text(geometry_input_element, "Source", import_geometry_output_guid)
    _set_item_text(geometry_input_element, "SourceCount", "1")


def _set_script_output_guids(
    csharp_script_object_element: element_tree.Element,
    script_output_instance_guid: str,
    script_standard_output_instance_guid: str,
) -> None:
    parameter_data_element = csharp_script_object_element.find(
        './chunks/chunk[@name="Container"]/chunks/chunk[@name="ParameterData"]'
    )
    if parameter_data_element is None:
        raise RuntimeError("C# Script ParameterData chunk was not found.")

    parameter_data_chunks_element = parameter_data_element.find("chunks")
    if parameter_data_chunks_element is None:
        raise RuntimeError("C# Script ParameterData chunks element was not found.")

    for output_param_element in parameter_data_chunks_element.findall('chunk[@name="OutputParam"]'):
        nickname_item = output_param_element.find('./items/item[@name="NickName"]')
        if nickname_item is None:
            continue
        if nickname_item.text == CSHARP_SCRIPT_OUTPUT_NICKNAME:
            _set_item_text(output_param_element, "InstanceGuid", script_output_instance_guid)
        if nickname_item.text == "out":
            _set_item_text(output_param_element, "InstanceGuid", script_standard_output_instance_guid)


def _embed_csharp_script_source(csharp_script_object_element: element_tree.Element) -> None:
    script_source_text = CSHARP_SCRIPT_SOURCE_PATH.read_text(encoding="utf-8")
    script_text_item = csharp_script_object_element.find(
        './chunks/chunk[@name="Container"]/chunks/chunk[@name="Script"]/items/item[@name="Text"]'
    )
    if script_text_item is None:
        raise RuntimeError("C# Script Text item was not found.")
    script_text_item.text = encode_script_source_text(script_source_text)


def _read_param_instance_guid(object_element: element_tree.Element, parameter_nickname: str) -> str:
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
        nickname_item = parameter_chunk.find('./items/item[@name="NickName"]')
        if nickname_item is None or nickname_item.text != parameter_nickname:
            continue
        instance_guid_item = parameter_chunk.find('./items/item[@name="InstanceGuid"]')
        if instance_guid_item is None or not instance_guid_item.text:
            raise RuntimeError(f"Parameter {parameter_nickname!r} is missing InstanceGuid.")
        return instance_guid_item.text

    raise RuntimeError(f"Parameter {parameter_nickname!r} was not found.")


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
    fixture_path = create_csharp_step_import_fixture()
    print(fixture_path)
