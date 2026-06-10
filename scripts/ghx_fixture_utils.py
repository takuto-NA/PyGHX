"""Shared XML helpers for generating RhinoCompute-ready GHX test fixtures."""

from __future__ import annotations

import copy
import uuid
import xml.etree.ElementTree as element_tree
from dataclasses import dataclass
from pathlib import Path

from pyghx.ghx_integrity import (
    refresh_definition_object_chunk_metadata,
    refresh_gha_libraries_count,
)
from pyghx.script_component import encode_script_source_text

LOGGER_MANAGER_COMPONENT_NAME = "LoggerManager"
LOGGER_LIBRARY_NAME = "Logger"
CSHARP_SCRIPT_COMPONENT_NAME = "C# Script"
GET_NUMBER_COMPONENT_NAME = "Get Number"
IMPORT_3DM_COMPONENT_NAME = "Import 3DM"
CONTEXT_BAKE_COMPONENT_NAME = "Context Bake"
GET_FILE_PATH_COMPONENT_NAME = "Get File Path"
CONTEXT_BAKE_CONTENT_PARAM_NICKNAME = "Content"
CSHARP_SCRIPT_STANDARD_OUTPUT_NICKNAME = "out"
CSHARP_SCRIPT_DEFAULT_OUTPUT_NICKNAME = "a"


class GhxFixtureError(Exception):
    """Raised when a fixture generator cannot safely mutate GHX XML."""


@dataclass(frozen=True)
class ImportModelFixtureContext:
    """Prepared import_model.ghx root and commonly used object elements."""

    root_element: element_tree.Element
    definition_element: element_tree.Element
    definition_objects_element: element_tree.Element
    object_chunks_element: element_tree.Element
    import_object_element: element_tree.Element
    context_bake_object_element: element_tree.Element


@dataclass(frozen=True)
class CSharpAdditionFixtureContext:
    """Prepared csharp_addition.ghx object elements used as templates."""

    csharp_script_object_element: element_tree.Element
    get_number_object_element: element_tree.Element


def load_ghx_root_element(source_path: Path) -> element_tree.Element:
    """Load one GHX file and return its root element."""
    return element_tree.parse(source_path).getroot()


def prepare_import_model_fixture_context(
    import_model_root_element: element_tree.Element,
    document_name: str,
) -> ImportModelFixtureContext:
    """Remove logger/thumbnail noise and return import_model object handles."""
    definition_element = find_child_chunk(import_model_root_element, "Definition")
    if definition_element is None:
        raise GhxFixtureError("Definition chunk was not found in import_model fixture.")

    remove_archive_thumbnail(import_model_root_element)
    remove_logger_library(definition_element)
    remove_logger_manager_object(definition_element)
    update_definition_name(definition_element, document_name)

    definition_objects_element = find_child_chunk(definition_element, "DefinitionObjects")
    if definition_objects_element is None:
        raise GhxFixtureError("DefinitionObjects chunk was not found.")

    object_chunks_element = definition_objects_element.find("chunks")
    if object_chunks_element is None:
        raise GhxFixtureError("DefinitionObjects chunks element was not found.")

    import_object_element = find_object_chunk_by_component_name(
        object_chunks_element,
        IMPORT_3DM_COMPONENT_NAME,
    )
    context_bake_object_element = find_object_chunk_by_component_name(
        object_chunks_element,
        CONTEXT_BAKE_COMPONENT_NAME,
    )
    if import_object_element is None or context_bake_object_element is None:
        raise GhxFixtureError("Import chain objects were not found in import_model fixture.")

    return ImportModelFixtureContext(
        root_element=import_model_root_element,
        definition_element=definition_element,
        definition_objects_element=definition_objects_element,
        object_chunks_element=object_chunks_element,
        import_object_element=import_object_element,
        context_bake_object_element=context_bake_object_element,
    )


def load_csharp_addition_fixture_context(
    csharp_addition_root_element: element_tree.Element,
) -> CSharpAdditionFixtureContext:
    """Return C# Script and Get Number template objects from csharp_addition.ghx."""
    definition_element = find_child_chunk(csharp_addition_root_element, "Definition")
    if definition_element is None:
        raise GhxFixtureError("Definition chunk was not found in csharp_addition fixture.")

    definition_objects_element = find_child_chunk(definition_element, "DefinitionObjects")
    if definition_objects_element is None:
        raise GhxFixtureError("DefinitionObjects chunk was not found in csharp_addition.")

    object_chunks_element = definition_objects_element.find("chunks")
    if object_chunks_element is None:
        raise GhxFixtureError("DefinitionObjects chunks element was not found in csharp_addition.")

    csharp_script_object_element = find_object_chunk_by_component_name(
        object_chunks_element,
        CSHARP_SCRIPT_COMPONENT_NAME,
    )
    get_number_object_element = find_object_chunk_by_component_name(
        object_chunks_element,
        GET_NUMBER_COMPONENT_NAME,
    )
    if csharp_script_object_element is None or get_number_object_element is None:
        raise GhxFixtureError("C# Script or Get Number was not found in csharp_addition fixture.")

    return CSharpAdditionFixtureContext(
        csharp_script_object_element=csharp_script_object_element,
        get_number_object_element=get_number_object_element,
    )


def write_fixture_root_element(
    fixture_context: ImportModelFixtureContext,
    output_path: Path,
) -> Path:
    """Refresh metadata and write one prepared fixture root element."""
    refresh_definition_object_chunk_metadata(fixture_context.definition_objects_element)
    refresh_gha_libraries_count(fixture_context.definition_element)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    element_tree.indent(fixture_context.root_element, space="  ")
    element_tree.ElementTree(fixture_context.root_element).write(
        output_path,
        encoding="utf-8",
        xml_declaration=True,
    )
    return output_path


def read_param_instance_guid(object_element: element_tree.Element, parameter_nickname: str) -> str:
    """Return one param_input/param_output InstanceGuid by NickName."""
    container_element = object_element.find('./chunks/chunk[@name="Container"]')
    if container_element is None:
        raise GhxFixtureError("Container chunk was not found.")

    container_chunks_element = container_element.find("chunks")
    if container_chunks_element is None:
        raise GhxFixtureError("Container chunks element was not found.")

    for parameter_chunk in container_chunks_element.findall("chunk"):
        chunk_name = parameter_chunk.get("name")
        if chunk_name not in {"param_input", "param_output"}:
            continue
        nickname_item = parameter_chunk.find('./items/item[@name="NickName"]')
        if nickname_item is None or nickname_item.text != parameter_nickname:
            continue
        instance_guid_item = parameter_chunk.find('./items/item[@name="InstanceGuid"]')
        if instance_guid_item is None or not instance_guid_item.text:
            raise GhxFixtureError(f"Parameter {parameter_nickname!r} is missing InstanceGuid.")
        return instance_guid_item.text

    raise GhxFixtureError(f"Parameter {parameter_nickname!r} was not found.")


def wire_context_bake_to_script_output(
    context_bake_object_element: element_tree.Element,
    script_output_instance_guid: str,
    context_bake_output_param_nickname: str,
) -> None:
    """Wire Context Bake Content to one C# Script output and rename the param."""
    context_bake_content_input_guid = str(uuid.uuid4())
    set_param_item_text(
        context_bake_object_element,
        CONTEXT_BAKE_CONTENT_PARAM_NICKNAME,
        "Source",
        script_output_instance_guid,
    )
    set_param_item_text(
        context_bake_object_element,
        CONTEXT_BAKE_CONTENT_PARAM_NICKNAME,
        "InstanceGuid",
        context_bake_content_input_guid,
    )
    set_param_item_text(
        context_bake_object_element,
        CONTEXT_BAKE_CONTENT_PARAM_NICKNAME,
        "Name",
        context_bake_output_param_nickname,
        match_item_name="NickName",
    )
    set_param_item_text(
        context_bake_object_element,
        context_bake_output_param_nickname,
        "NickName",
        context_bake_output_param_nickname,
        match_item_name="Name",
    )


def embed_csharp_script_source(
    csharp_script_object_element: element_tree.Element,
    csharp_script_source_path: Path,
) -> None:
    """Embed one C# source file into a C# Script object."""
    script_source_text = csharp_script_source_path.read_text(encoding="utf-8")
    script_text_item = csharp_script_object_element.find(
        './chunks/chunk[@name="Container"]/chunks/chunk[@name="Script"]/items/item[@name="Text"]'
    )
    if script_text_item is None:
        raise GhxFixtureError("C# Script Text item was not found.")
    script_text_item.text = encode_script_source_text(script_source_text)


def set_script_output_guids(
    csharp_script_object_element: element_tree.Element,
    script_output_instance_guid: str,
    script_standard_output_instance_guid: str,
    script_output_nickname: str = CSHARP_SCRIPT_DEFAULT_OUTPUT_NICKNAME,
) -> None:
    """Assign fresh InstanceGuid values to C# Script output parameters."""
    parameter_data_element = find_csharp_script_parameter_data_element(csharp_script_object_element)
    parameter_data_chunks_element = parameter_data_element.find("chunks")
    if parameter_data_chunks_element is None:
        raise GhxFixtureError("C# Script ParameterData chunks element was not found.")

    for output_param_element in parameter_data_chunks_element.findall('chunk[@name="OutputParam"]'):
        nickname_item = output_param_element.find('./items/item[@name="NickName"]')
        if nickname_item is None:
            continue
        if nickname_item.text == script_output_nickname:
            set_item_text(output_param_element, "InstanceGuid", script_output_instance_guid)
        if nickname_item.text == CSHARP_SCRIPT_STANDARD_OUTPUT_NICKNAME:
            set_item_text(output_param_element, "InstanceGuid", script_standard_output_instance_guid)


def configure_csharp_script_input(
    csharp_script_object_element: element_tree.Element,
    input_param_index: int,
    input_name: str,
    input_instance_guid: str,
    source_instance_guid: str,
) -> None:
    """Configure one C# Script InputParam name, GUID, and source wiring."""
    input_param_element = find_csharp_script_input_param_element(
        csharp_script_object_element,
        input_param_index,
    )
    set_item_text(input_param_element, "InstanceGuid", input_instance_guid)
    set_item_text(input_param_element, "Name", input_name)
    set_item_text(input_param_element, "NickName", input_name)
    set_item_text(input_param_element, "Source", source_instance_guid)
    set_item_text(input_param_element, "SourceCount", "1")


def set_csharp_script_input_count(
    csharp_script_object_element: element_tree.Element,
    input_count: int,
) -> None:
    """Set C# Script InputCount and remove extra InputParam / InputId entries."""
    parameter_data_element = find_csharp_script_parameter_data_element(csharp_script_object_element)
    parameter_data_items_element = parameter_data_element.find("items")
    if parameter_data_items_element is None:
        raise GhxFixtureError("C# Script ParameterData items element was not found.")

    input_count_item = parameter_data_items_element.find('./item[@name="InputCount"]')
    if input_count_item is None:
        raise GhxFixtureError("C# Script InputCount item was not found.")
    input_count_item.text = str(input_count)

    for input_id_item in list(parameter_data_items_element.findall('item[@name="InputId"]')):
        input_id_index = input_id_item.get("index")
        if input_id_index is None or int(input_id_index) >= input_count:
            parameter_data_items_element.remove(input_id_item)

    parameter_data_chunks_element = parameter_data_element.find("chunks")
    if parameter_data_chunks_element is None:
        raise GhxFixtureError("C# Script ParameterData chunks element was not found.")

    for input_param_element in list(parameter_data_chunks_element.findall('chunk[@name="InputParam"]')):
        input_param_index = input_param_element.get("index")
        if input_param_index is None or int(input_param_index) >= input_count:
            parameter_data_chunks_element.remove(input_param_element)


def clone_get_number_object(
    template_get_number_object_element: element_tree.Element,
    nickname: str,
) -> tuple[element_tree.Element, str]:
    """Deep-copy one Get Number object with a fresh InstanceGuid and nickname."""
    get_number_copy_element = copy.deepcopy(template_get_number_object_element)
    get_number_instance_guid = str(uuid.uuid4())
    set_container_nickname(get_number_copy_element, nickname)
    set_container_item_text(get_number_copy_element, "InstanceGuid", get_number_instance_guid)
    return get_number_copy_element, get_number_instance_guid


def find_child_chunk(parent_element: element_tree.Element, chunk_name: str) -> element_tree.Element | None:
    """Return the first child chunk with the given name."""
    chunks_element = parent_element.find("chunks")
    if chunks_element is None:
        return None

    for child_element in chunks_element.findall("chunk"):
        if child_element.get("name") == chunk_name:
            return child_element
    return None


def find_object_chunk_by_component_name(
    object_chunks_element: element_tree.Element,
    component_name: str,
) -> element_tree.Element | None:
    """Return the first Object chunk whose Name item matches component_name."""
    for object_element in object_chunks_element.findall("chunk"):
        name_item = object_element.find('./items/item[@name="Name"]')
        if name_item is not None and name_item.text == component_name:
            return object_element
    return None


def set_container_nickname(object_element: element_tree.Element, nickname: str) -> None:
    """Set Container NickName on one Object chunk."""
    container_element = object_element.find('./chunks/chunk[@name="Container"]')
    if container_element is None:
        raise GhxFixtureError("Container chunk was not found.")
    set_item_text(container_element, "NickName", nickname)


def set_container_item_text(
    object_element: element_tree.Element,
    item_name: str,
    item_text: str,
) -> None:
    """Set one Container item on an Object chunk."""
    container_element = object_element.find('./chunks/chunk[@name="Container"]')
    if container_element is None:
        raise GhxFixtureError("Container chunk was not found.")
    set_item_text(container_element, item_name, item_text)


def set_item_text(
    parent_element: element_tree.Element,
    item_name: str,
    item_text: str,
) -> None:
    """Set one named item under a parent XML element."""
    item_element = parent_element.find(f'./items/item[@name="{item_name}"]')
    if item_element is None:
        raise GhxFixtureError(f"Item {item_name!r} was not found.")
    item_element.text = item_text


def set_param_item_text(
    object_element: element_tree.Element,
    parameter_lookup_value: str,
    item_name: str,
    item_text: str,
    match_item_name: str = "NickName",
) -> None:
    """Set one item on a param_input/param_output chunk located by NickName or Name."""
    container_element = object_element.find('./chunks/chunk[@name="Container"]')
    if container_element is None:
        raise GhxFixtureError("Container chunk was not found.")

    container_chunks_element = container_element.find("chunks")
    if container_chunks_element is None:
        raise GhxFixtureError("Container chunks element was not found.")

    for parameter_chunk in container_chunks_element.findall("chunk"):
        chunk_name = parameter_chunk.get("name")
        if chunk_name not in {"param_input", "param_output"}:
            continue
        lookup_item = parameter_chunk.find(f'./items/item[@name="{match_item_name}"]')
        if lookup_item is None or lookup_item.text != parameter_lookup_value:
            continue
        item_element = parameter_chunk.find(f'./items/item[@name="{item_name}"]')
        if item_element is None:
            raise GhxFixtureError(
                f"Parameter {parameter_lookup_value!r} is missing item {item_name!r}."
            )
        item_element.text = item_text
        return

    raise GhxFixtureError(f"Parameter {parameter_lookup_value!r} was not found.")


def remove_logger_library(definition_element: element_tree.Element) -> None:
    """Remove Logger GHALibrary entries from one Definition chunk."""
    gha_libraries_element = find_child_chunk(definition_element, "GHALibraries")
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


def remove_logger_manager_object(definition_element: element_tree.Element) -> None:
    """Remove LoggerManager objects and refresh DefinitionObjects metadata."""
    definition_objects_element = find_child_chunk(definition_element, "DefinitionObjects")
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


def remove_archive_thumbnail(root_element: element_tree.Element) -> None:
    """Remove the archive Thumbnail chunk if present."""
    archive_chunks_element = root_element.find("chunks")
    if archive_chunks_element is None:
        return

    for child_element in list(archive_chunks_element.findall("chunk")):
        if child_element.get("name") == "Thumbnail":
            archive_chunks_element.remove(child_element)


def update_definition_name(definition_element: element_tree.Element, document_name: str) -> None:
    """Set DefinitionProperties > Name for one fixture document."""
    definition_properties_element = find_child_chunk(definition_element, "DefinitionProperties")
    if definition_properties_element is None:
        raise GhxFixtureError("DefinitionProperties chunk was not found.")
    name_item = definition_properties_element.find('./items/item[@name="Name"]')
    if name_item is None:
        raise GhxFixtureError("DefinitionProperties Name item was not found.")
    name_item.text = document_name


def find_csharp_script_parameter_data_element(
    csharp_script_object_element: element_tree.Element,
) -> element_tree.Element:
    """Return the C# Script ParameterData chunk."""
    parameter_data_element = csharp_script_object_element.find(
        './chunks/chunk[@name="Container"]/chunks/chunk[@name="ParameterData"]'
    )
    if parameter_data_element is None:
        raise GhxFixtureError("C# Script ParameterData chunk was not found.")
    return parameter_data_element


def find_csharp_script_input_param_element(
    csharp_script_object_element: element_tree.Element,
    input_param_index: int,
) -> element_tree.Element:
    """Return one C# Script InputParam chunk by index."""
    parameter_data_element = find_csharp_script_parameter_data_element(csharp_script_object_element)
    parameter_data_chunks_element = parameter_data_element.find("chunks")
    if parameter_data_chunks_element is None:
        raise GhxFixtureError("C# Script ParameterData chunks element was not found.")

    input_param_element = parameter_data_chunks_element.find(
        f'chunk[@name="InputParam"][@index="{input_param_index}"]'
    )
    if input_param_element is None:
        raise GhxFixtureError(f"C# Script InputParam index {input_param_index} was not found.")
    return input_param_element
