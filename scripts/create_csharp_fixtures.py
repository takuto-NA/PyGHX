"""Create csharp_addition.ghx and csharp_addition_raw.ghx fixtures from csghx.ghx."""

from __future__ import annotations

import base64
import copy
import xml.etree.ElementTree as element_tree
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = REPOSITORY_ROOT / "csghx.ghx"
FIXTURES_DIRECTORY = REPOSITORY_ROOT / "tests" / "fixtures"
FIXED_OUTPUT_PATH = FIXTURES_DIRECTORY / "csharp_addition.ghx"
RAW_OUTPUT_PATH = FIXTURES_DIRECTORY / "csharp_addition_raw.ghx"
LOGGER_MANAGER_COMPONENT_NAME = "LoggerManager"
LOGGER_LIBRARY_NAME = "Logger"
FIXED_DOCUMENT_NAME = "csharp_addition.ghx"
RAW_DOCUMENT_NAME = "csharp_addition_raw.ghx"
TEMPLATE_SCRIPT_BASE64_SUFFIX = "YSA9IG51bGw7"

NULL_TEMPLATE_SCRIPT_SOURCE = """\
// Grasshopper Script Instance
#region Usings
using System;
using System.Linq;
using System.Collections;
using System.Collections.Generic;
using System.Drawing;

using Rhino;
using Rhino.Geometry;

using Grasshopper;
using Grasshopper.Kernel;
using Grasshopper.Kernel.Data;
using Grasshopper.Kernel.Types;
#endregion

public class Script_Instance : GH_ScriptInstance
{
    #region Notes
    /* 
      Members:
        RhinoDoc RhinoDocument
        GH_Document GrasshopperDocument
        IGH_Component Component
        int Iteration

      Methods (Virtual & overridable):
        Print(string text)
        Print(string format, params object[] args)
        Reflect(object obj)
        Reflect(object obj, string method_name)
    */
    #endregion

    private void RunScript(object x, object y, ref object a)
    {
        // Write your logic here
        a = null;
    }
}
"""


def create_csharp_fixtures() -> tuple[Path, Path]:
    """Write fixed and raw C# Script GHX fixtures."""
    if not SOURCE_PATH.is_file():
        raise RuntimeError(f"Source GHX was not found: {SOURCE_PATH}")

    fixed_root_element = element_tree.parse(SOURCE_PATH).getroot()
    _sanitize_for_compute_fixture(fixed_root_element, FIXED_DOCUMENT_NAME)
    FIXTURES_DIRECTORY.mkdir(parents=True, exist_ok=True)
    _write_ghx(fixed_root_element, FIXED_OUTPUT_PATH)

    raw_root_element = copy.deepcopy(fixed_root_element)
    _convert_fixed_fixture_to_raw(raw_root_element, RAW_DOCUMENT_NAME)
    _write_ghx(raw_root_element, RAW_OUTPUT_PATH)
    return FIXED_OUTPUT_PATH, RAW_OUTPUT_PATH


def _sanitize_for_compute_fixture(root_element: element_tree.Element, document_name: str) -> None:
    definition_element = _find_child_chunk(root_element, "Definition")
    if definition_element is None:
        raise RuntimeError("Definition chunk was not found.")

    _remove_archive_thumbnail(root_element)
    _remove_logger_library(definition_element)
    _remove_logger_manager_object(definition_element)
    _update_definition_name(definition_element, document_name)
    _refresh_chunk_counts(root_element)


def _convert_fixed_fixture_to_raw(root_element: element_tree.Element, document_name: str) -> None:
    definition_element = _find_child_chunk(root_element, "Definition")
    if definition_element is None:
        raise RuntimeError("Definition chunk was not found.")

    definition_objects_element = _find_child_chunk(definition_element, "DefinitionObjects")
    if definition_objects_element is None:
        raise RuntimeError("DefinitionObjects chunk was not found.")

    object_chunks_element = definition_objects_element.find("chunks")
    if object_chunks_element is None:
        raise RuntimeError("DefinitionObjects chunks element was not found.")

    _set_contextual_input_nickname(object_chunks_element, "6ff49b4e-be51-4113-a28d-f99ca930859d", "Get Number")
    _set_contextual_input_nickname(object_chunks_element, "19e82177-c780-4c7e-995c-4da6b1579038", "Get Number")
    _set_script_text_to_null_template(object_chunks_element)
    _insert_raw_context_bake_object(definition_objects_element, object_chunks_element)
    _update_definition_name(definition_element, document_name)
    _refresh_chunk_counts(root_element)


def _set_contextual_input_nickname(
    object_chunks_element: element_tree.Element,
    instance_guid: str,
    nickname: str,
) -> None:
    for object_element in object_chunks_element.findall("chunk"):
        container_element = object_element.find('./chunks/chunk[@name="Container"]')
        if container_element is None:
            continue
        instance_guid_item = container_element.find('./items/item[@name="InstanceGuid"]')
        if instance_guid_item is None or instance_guid_item.text != instance_guid:
            continue
        nickname_item = container_element.find('./items/item[@name="NickName"]')
        if nickname_item is None:
            raise RuntimeError(f"NickName item was not found for {instance_guid}.")
        nickname_item.text = nickname
        return
    raise RuntimeError(f"Contextual input object was not found: {instance_guid}.")


def _set_script_text_to_null_template(object_chunks_element: element_tree.Element) -> None:
    encoded_script_text = base64.b64encode(NULL_TEMPLATE_SCRIPT_SOURCE.encode("utf-8")).decode("ascii")
    for object_element in object_chunks_element.findall("chunk"):
        object_name_item = object_element.find('./items/item[@name="Name"]')
        if object_name_item is None or object_name_item.text != "C# Script":
            continue
        script_text_item = object_element.find(
            './/chunk[@name="Script"]/items/item[@name="Text"]'
        )
        if script_text_item is None:
            raise RuntimeError("C# Script Text item was not found.")
        script_text_item.text = encoded_script_text
        return
    raise RuntimeError("C# Script object was not found.")


def _insert_raw_context_bake_object(
    definition_objects_element: element_tree.Element,
    object_chunks_element: element_tree.Element,
) -> None:
    existing_context_bake_element = None
    for object_element in object_chunks_element.findall("chunk"):
        object_name_item = object_element.find('./items/item[@name="Name"]')
        if object_name_item is not None and object_name_item.text == "Context Bake":
            existing_context_bake_element = object_element
            break
    if existing_context_bake_element is None:
        raise RuntimeError("Context Bake object was not found in fixed fixture.")

    duplicate_context_bake_element = copy.deepcopy(existing_context_bake_element)
    duplicate_context_bake_element.set(
        "index",
        str(len(object_chunks_element.findall("chunk"))),
    )
    container_element = duplicate_context_bake_element.find('./chunks/chunk[@name="Container"]')
    if container_element is None:
        raise RuntimeError("Duplicate Context Bake is missing Container chunk.")

    instance_guid_item = container_element.find('./items/item[@name="InstanceGuid"]')
    if instance_guid_item is not None:
        instance_guid_item.text = "c5bbe4a9-4b2c-4253-9a8c-03da1002ae74"

    content_param_element = container_element.find('./chunks/chunk[@name="param_input"]')
    if content_param_element is None:
        raise RuntimeError("Duplicate Context Bake is missing Content param_input.")

    content_instance_item = content_param_element.find('./items/item[@name="InstanceGuid"]')
    if content_instance_item is not None:
        content_instance_item.text = "0740bd51-dacd-47d8-9699-7bda3814652c"

    source_item = content_param_element.find('./items/item[@name="Source"]')
    if source_item is not None:
        source_item.text = "4e576b7e-bb1d-4fff-86dc-bd76c01b484c"

    object_chunks_element.insert(4, duplicate_context_bake_element)
    for object_index, object_element in enumerate(object_chunks_element.findall("chunk")):
        object_element.set("index", str(object_index))

    object_count_item = definition_objects_element.find('./items/item[@name="ObjectCount"]')
    if object_count_item is None:
        raise RuntimeError("ObjectCount item was not found.")
    object_count_item.text = str(len(object_chunks_element.findall("chunk")))


def _write_ghx(root_element: element_tree.Element, output_path: Path) -> None:
    element_tree.indent(root_element, space="  ")
    element_tree.ElementTree(root_element).write(
        output_path,
        encoding="utf-8",
        xml_declaration=True,
    )


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
    fixed_path, raw_path = create_csharp_fixtures()
    print(fixed_path)
    print(raw_path)
