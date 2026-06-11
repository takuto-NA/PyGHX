"""Unit tests for GHX component cloning and Context Bake wiring helpers."""

from __future__ import annotations

import shutil
import xml.etree.ElementTree as element_tree

from pyghx.ghx_component_edit import (
    append_context_bake_object,
    append_csharp_script_object,
    load_ghx_root_from_path,
    read_component_output_param_guid,
    read_context_bake_source_output_param_guid,
    read_script_output_param_guid,
    write_ghx_document,
)
from pyghx.ghx_edit import find_item_text, iter_object_elements
from pyghx.inspect import inspect_document
from pyghx.validate import validate_document
from tests.helpers import ADDITION_FIXTURE_PATH, CSHARP_ADDITION_FIXTURE_PATH

TEST_SCRIPT_SOURCE = """// Responsibility: emit one doubled value for component-edit unit tests.
public class Script_Instance : GH_ScriptInstance
{
    private void RunScript(object value, ref object doubled)
    {
        doubled = System.Convert.ToDouble(value) * 2.0;
    }
}
"""

TEST_SCRIPT_INPUT_SPECS = [{"name": "value"}]
TEST_SCRIPT_OUTPUT_SPECS = [
    {"name": "out", "is_standard_output": True},
    {"name": "doubled"},
]


def _count_definition_objects(root_element: element_tree.Element) -> int:
    object_count_item = root_element.find(
        './chunks/chunk[@name="Definition"]/chunks/chunk[@name="DefinitionObjects"]/items/item[@name="ObjectCount"]'
    )
    if object_count_item is None or not object_count_item.text:
        return len(list(iter_object_elements(root_element)))
    return int(object_count_item.text)


def _collect_instance_guids(root_element: element_tree.Element) -> set[str]:
    instance_guids: set[str] = set()
    for item_element in root_element.iter("item"):
        if item_element.get("name") != "InstanceGuid":
            continue
        if item_element.text:
            instance_guids.add(item_element.text)
    return instance_guids


def test_append_csharp_script_object_preserves_unique_guids(tmp_path) -> None:
    output_path = tmp_path / "append_script.ghx"
    shutil.copy(CSHARP_ADDITION_FIXTURE_PATH, output_path)
    root_element = load_ghx_root_from_path(output_path)
    initial_object_count = _count_definition_objects(root_element)
    initial_instance_guids = _collect_instance_guids(root_element)

    append_csharp_script_object(
        root_element,
        script_source_text=TEST_SCRIPT_SOURCE,
        script_title="Doubler",
        input_parameter_specs=TEST_SCRIPT_INPUT_SPECS,
        output_parameter_specs=TEST_SCRIPT_OUTPUT_SPECS,
    )
    write_ghx_document(root_element, output_path)

    updated_root_element = load_ghx_root_from_path(output_path)
    updated_instance_guids = _collect_instance_guids(updated_root_element)

    assert _count_definition_objects(updated_root_element) == initial_object_count + 1
    assert len(updated_instance_guids) > len(initial_instance_guids)
    assert len(updated_instance_guids) == len(set(updated_instance_guids))


def test_read_component_output_param_guid_returns_addition_result(tmp_path) -> None:
    output_path = tmp_path / "addition_copy.ghx"
    shutil.copy(ADDITION_FIXTURE_PATH, output_path)
    root_element = load_ghx_root_from_path(output_path)

    addition_object = next(
        object_element
        for object_element in iter_object_elements(root_element)
        if find_item_text(object_element.find("items"), "Name") == "Addition"
    )
    result_output_guid = read_component_output_param_guid(addition_object, "Result")

    assert result_output_guid == "f43684a1-2c35-4597-ad45-e62ef4766407"


def test_append_context_bake_object_wires_source_output_param(tmp_path) -> None:
    output_path = tmp_path / "context_bake_append.ghx"
    shutil.copy(CSHARP_ADDITION_FIXTURE_PATH, output_path)
    root_element = load_ghx_root_from_path(output_path)
    script_object = next(
        object_element
        for object_element in iter_object_elements(root_element)
        if find_item_text(object_element.find("items"), "Name") == "C# Script"
    )
    script_output_guid = read_script_output_param_guid(script_object, "a")
    initial_object_count = _count_definition_objects(root_element)

    context_bake_object, _context_bake_instance_guid = append_context_bake_object(
        root_element,
        source_output_param_guid=script_output_guid,
        compute_param_name="doubled",
    )
    write_ghx_document(root_element, output_path)

    updated_root_element = load_ghx_root_from_path(output_path)
    assert _count_definition_objects(updated_root_element) == initial_object_count + 1
    assert read_context_bake_source_output_param_guid(context_bake_object) == script_output_guid

    summary = inspect_document(output_path)
    compute_output_names = {
        output["compute_param_name"] for output in summary["compute_contract"]["outputs"]
    }
    assert "doubled" in compute_output_names
