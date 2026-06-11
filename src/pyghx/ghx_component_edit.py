"""GHX component cloning and Context Bake wiring helpers."""

from __future__ import annotations

import copy
import xml.etree.ElementTree as element_tree
from importlib import resources
from pathlib import Path

from pyghx.constants import CONTEXT_BAKE_COMPONENT_NAME
from pyghx.ghx_edit import (
    GhxEditError,
    append_definition_object,
    deep_copy_element,
    find_definition_objects_element,
    find_item_text,
    find_object_element_by_instance_guid,
    generate_unique_instance_guid,
    iter_object_elements,
    offset_object_bounds_y,
    parse_ghx_root_element,
    read_object_param_instance_guid,
    reindex_named_chunks,
    set_item_text,
    set_object_param_item_text,
    update_items_count,
    write_ghx_root_element,
)
from pyghx.script_component import C_SHARP_SCRIPT_COMPONENT_NAME, encode_script_source_text

ADDITION_COMPUTE_TEMPLATE_NAME = "addition_compute.ghx"
CONTEXT_BAKE_COMPONENT_TYPE_GUID = "ae2531b4-bab2-4bb1-b5bf-f2143d10c132"
C_SHARP_SCRIPT_COMPONENT_TYPE_GUID = "b6ba1144-02d6-4a2d-b53c-ec62e290eeb7"
SCRIPT_INPUT_PARAMETER_TYPE_GUID = "08908df5-fa14-4982-9ab2-1aa0927566aa"
SCRIPT_STANDARD_OUTPUT_TYPE_GUID = "3ede854e-c753-40eb-84cb-b48008f14fd4"
SCRIPT_GENERIC_OUTPUT_TYPE_GUID = "08908df5-fa14-4982-9ab2-1aa0927566aa"
SCRIPT_NUMBER_LIST_TYPE_HINT_ID = "19ff81a2-dc4f-4035-8de9-26224c561321"
SCRIPT_GENERIC_TYPE_HINT_ID = "6a184b65-baa3-42d1-a548-3915b401de53"
SCRIPT_PARAM_ACCESS_ITEM = 0
SCRIPT_PARAM_ACCESS_LIST = 1
SCRIPT_PARAM_ACCESS_TREE = 2
CONTEXT_BAKE_CONTENT_PARAM_NICKNAME = "Content"


class GhxComponentEditError(Exception):
    """Raised when GHX component edits cannot be applied safely."""


def clone_object_by_instance_guid(
    root_element: element_tree.Element,
    source_instance_guid: str,
    *,
    vertical_offset: int = 0,
) -> tuple[element_tree.Element, str]:
    """Clone one Object chunk and return the clone with a fresh Container InstanceGuid."""
    source_object_element = find_object_element_by_instance_guid(root_element, source_instance_guid)
    if source_object_element is None:
        raise GhxComponentEditError(
            f"Object was not found for InstanceGuid {source_instance_guid!r}."
        )

    cloned_object_element = deep_copy_element(source_object_element)
    new_instance_guid = _assign_fresh_guids_to_object_element(
        root_element,
        cloned_object_element,
    )
    offset_object_bounds_y(cloned_object_element, vertical_offset)
    append_definition_object(root_element, cloned_object_element)
    return cloned_object_element, new_instance_guid


def append_csharp_script_object(
    root_element: element_tree.Element,
    *,
    script_source_text: str,
    script_title: str,
    input_parameter_specs: list[dict[str, str | bool]],
    output_parameter_specs: list[dict[str, str | bool]],
    vertical_offset: int = 0,
) -> tuple[element_tree.Element, str]:
    """Append one C# Script object with explicit ParameterData wiring."""
    template_object_element = _find_first_csharp_script_object_element(root_element)
    cloned_object_element = deep_copy_element(template_object_element)
    new_instance_guid = _assign_fresh_guids_to_object_element(
        root_element,
        cloned_object_element,
    )

    container_element = cloned_object_element.find('./chunks/chunk[@name="Container"]')
    if container_element is None:
        raise GhxComponentEditError("C# Script Container chunk was not found.")

    set_item_text(container_element.find("items"), "NickName", script_title)
    script_text_item = container_element.find(
        './chunks/chunk[@name="Script"]/items/item[@name="Text"]'
    )
    if script_text_item is None:
        raise GhxComponentEditError("C# Script Text item was not found.")
    script_text_item.text = encode_script_source_text(script_source_text)

    script_title_item = container_element.find(
        './chunks/chunk[@name="Script"]/items/item[@name="Title"]'
    )
    if script_title_item is not None:
        script_title_item.text = script_title

    parameter_data_element = container_element.find('./chunks/chunk[@name="ParameterData"]')
    if parameter_data_element is None:
        raise GhxComponentEditError("C# Script ParameterData chunk was not found.")

    _replace_script_parameter_data(
        parameter_data_element,
        input_parameter_specs=input_parameter_specs,
        output_parameter_specs=output_parameter_specs,
        root_element=root_element,
    )

    component_guid_item = cloned_object_element.find('./items/item[@name="GUID"]')
    if component_guid_item is not None:
        component_guid_item.text = C_SHARP_SCRIPT_COMPONENT_TYPE_GUID

    offset_object_bounds_y(cloned_object_element, vertical_offset)
    append_definition_object(root_element, cloned_object_element)
    return cloned_object_element, new_instance_guid


def append_context_bake_object(
    root_element: element_tree.Element,
    *,
    source_output_param_guid: str,
    compute_param_name: str,
    vertical_offset: int = 0,
) -> tuple[element_tree.Element, str]:
    """Append one Context Bake object wired to a source output parameter."""
    context_bake_object_element = _load_context_bake_template_object_element()
    new_instance_guid = _assign_fresh_guids_to_object_element(
        root_element,
        context_bake_object_element,
    )
    wire_context_bake_to_output_param(
        context_bake_object_element,
        source_output_param_guid=source_output_param_guid,
        compute_param_name=compute_param_name,
        root_element=root_element,
    )
    offset_object_bounds_y(context_bake_object_element, vertical_offset)
    append_definition_object(root_element, context_bake_object_element)
    return context_bake_object_element, new_instance_guid


def wire_context_bake_to_output_param(
    context_bake_object_element: element_tree.Element,
    *,
    source_output_param_guid: str,
    compute_param_name: str,
    root_element: element_tree.Element | None = None,
) -> None:
    """Wire one Context Bake Content input to a source output parameter."""
    guid_root_element = root_element if root_element is not None else context_bake_object_element
    content_param_guid = generate_unique_instance_guid(guid_root_element)
    _set_context_bake_content_param_item_text(
        context_bake_object_element,
        item_name="Source",
        item_text=source_output_param_guid,
    )
    _set_context_bake_content_param_item_text(
        context_bake_object_element,
        item_name="InstanceGuid",
        item_text=content_param_guid,
    )
    _set_context_bake_content_param_item_text(
        context_bake_object_element,
        item_name="NickName",
        item_text=compute_param_name,
    )


def wire_component_container_source(
    object_element: element_tree.Element,
    *,
    source_param_guid: str,
) -> None:
    """Point one component-level Container Source item at another parameter InstanceGuid."""
    container_element = object_element.find('./chunks/chunk[@name="Container"]')
    if container_element is None:
        raise GhxComponentEditError("Container chunk was not found.")
    container_items_element = container_element.find("items")
    if container_items_element is None:
        raise GhxComponentEditError("Container items element was not found.")
    set_item_text(container_items_element, "Source", source_param_guid, item_index="0")
    set_item_text(container_items_element, "SourceCount", "1")


def wire_object_param_source(
    object_element: element_tree.Element,
    *,
    parameter_nickname: str,
    source_param_guid: str,
) -> None:
    """Point one param_input Source item at another parameter InstanceGuid."""
    set_object_param_item_text(
        object_element,
        parameter_nickname,
        "Source",
        source_param_guid,
        match_item_name="NickName",
    )
    set_object_param_item_text(
        object_element,
        parameter_nickname,
        "SourceCount",
        "1",
        match_item_name="NickName",
    )


def read_script_output_param_guid(
    script_object_element: element_tree.Element,
    output_variable_name: str,
) -> str:
    """Return one C# Script OutputParam InstanceGuid by variable name."""
    parameter_data_element = script_object_element.find(
        './chunks/chunk[@name="Container"]/chunks/chunk[@name="ParameterData"]'
    )
    if parameter_data_element is None:
        raise GhxComponentEditError("C# Script ParameterData chunk was not found.")

    parameter_chunks_element = parameter_data_element.find("chunks")
    if parameter_chunks_element is None:
        raise GhxComponentEditError("C# Script ParameterData chunks element was not found.")

    for output_param_element in parameter_chunks_element.findall('chunk[@name="OutputParam"]'):
        output_name = find_item_text(output_param_element.find("items"), "Name")
        if output_name != output_variable_name:
            continue
        output_param_guid = find_item_text(output_param_element.find("items"), "InstanceGuid")
        if output_param_guid is None:
            raise GhxComponentEditError(
                f"C# Script output {output_variable_name!r} is missing InstanceGuid."
            )
        return output_param_guid

    raise GhxComponentEditError(
        f"C# Script output variable was not found: {output_variable_name!r}."
    )


def read_component_output_param_guid(
    object_element: element_tree.Element,
    output_parameter_name: str,
) -> str:
    """Return one native component OutputParam InstanceGuid by parameter name."""
    container_element = object_element.find('./chunks/chunk[@name="Container"]')
    if container_element is None:
        raise GhxComponentEditError("Container chunk was not found.")

    parameter_data_element = container_element.find('./chunks/chunk[@name="ParameterData"]')
    if parameter_data_element is not None:
        for output_param_element in parameter_data_element.findall('./chunks/chunk[@name="OutputParam"]'):
            output_name = find_item_text(output_param_element.find("items"), "Name")
            if output_name != output_parameter_name:
                continue
            output_param_guid = find_item_text(output_param_element.find("items"), "InstanceGuid")
            if output_param_guid is None:
                raise GhxComponentEditError(
                    f"Output parameter {output_parameter_name!r} is missing InstanceGuid."
                )
            return output_param_guid

    for parameter_chunk in container_element.findall('./chunks/chunk'):
        if parameter_chunk.get("name") != "param_output":
            continue
        output_name = find_item_text(parameter_chunk.find("items"), "Name")
        if output_name != output_parameter_name:
            continue
        output_param_guid = find_item_text(parameter_chunk.find("items"), "InstanceGuid")
        if output_param_guid is None:
            raise GhxComponentEditError(
                f"Output parameter {output_parameter_name!r} is missing InstanceGuid."
            )
        return output_param_guid

    raise GhxComponentEditError(
        f"Output parameter was not found: {output_parameter_name!r}."
    )


def read_script_input_param_guid(
    script_object_element: element_tree.Element,
    input_variable_name: str,
) -> str:
    """Return one C# Script InputParam InstanceGuid by variable name."""
    parameter_data_element = script_object_element.find(
        './chunks/chunk[@name="Container"]/chunks/chunk[@name="ParameterData"]'
    )
    if parameter_data_element is None:
        raise GhxComponentEditError("C# Script ParameterData chunk was not found.")

    parameter_chunks_element = parameter_data_element.find("chunks")
    if parameter_chunks_element is None:
        raise GhxComponentEditError("C# Script ParameterData chunks element was not found.")

    for input_param_element in parameter_chunks_element.findall('chunk[@name="InputParam"]'):
        input_name = find_item_text(input_param_element.find("items"), "Name")
        if input_name != input_variable_name:
            continue
        input_param_guid = find_item_text(input_param_element.find("items"), "InstanceGuid")
        if input_param_guid is None:
            raise GhxComponentEditError(
                f"C# Script input {input_variable_name!r} is missing InstanceGuid."
            )
        return input_param_guid

    raise GhxComponentEditError(
        f"C# Script input variable was not found: {input_variable_name!r}."
    )


def find_get_number_instance_guid(
    root_element: element_tree.Element,
    contextual_nickname: str,
) -> str:
    """Return one Get Number Container InstanceGuid by nickname."""
    for object_element in iter_object_elements(root_element):
        object_name = find_item_text(object_element.find("items"), "Name")
        if object_name != "Get Number":
            continue
        container_element = object_element.find('./chunks/chunk[@name="Container"]')
        if container_element is None:
            continue
        nickname = find_item_text(container_element.find("items"), "NickName")
        if nickname != contextual_nickname:
            continue
        instance_guid = find_item_text(container_element.find("items"), "InstanceGuid")
        if instance_guid is None:
            raise GhxComponentEditError(
                f"Get Number {contextual_nickname!r} is missing InstanceGuid."
            )
        return instance_guid

    raise GhxComponentEditError(
        f"Get Number contextual input was not found: {contextual_nickname!r}."
    )


def find_object_instance_guid_by_nickname(
    root_element: element_tree.Element,
    component_name: str,
    object_nickname: str | None,
) -> str:
    """Return one component Container InstanceGuid by component name and nickname."""
    for object_element in iter_object_elements(root_element):
        object_component_name = find_item_text(object_element.find("items"), "Name")
        if object_component_name != component_name:
            continue
        container_element = object_element.find('./chunks/chunk[@name="Container"]')
        if container_element is None:
            continue
        nickname = find_item_text(container_element.find("items"), "NickName")
        if nickname != object_nickname:
            continue
        instance_guid = find_item_text(container_element.find("items"), "InstanceGuid")
        if instance_guid is None:
            raise GhxComponentEditError(
                f"{component_name} object is missing InstanceGuid for nickname {object_nickname!r}."
            )
        return instance_guid

    raise GhxComponentEditError(
        f"{component_name} object was not found for nickname {object_nickname!r}."
    )


def find_vector_xyz_for_get_number_sources(
    root_element: element_tree.Element,
    get_number_instance_guids: tuple[str, str, str],
) -> element_tree.Element:
    """Return the Vector XYZ object wired to the given Get Number instance GUIDs."""
    for object_element in iter_object_elements(root_element):
        object_component_name = find_item_text(object_element.find("items"), "Name")
        if object_component_name != "Vector XYZ":
            continue

        container_element = object_element.find('./chunks/chunk[@name="Container"]')
        if container_element is None:
            continue

        axis_sources: list[str] = []
        for axis_nickname in ("X component", "Y component", "Z component"):
            try:
                axis_sources.append(
                    _read_param_source_guid(container_element, axis_nickname),
                )
            except GhxComponentEditError:
                axis_sources = []
                break

        if tuple(axis_sources) == get_number_instance_guids:
            return object_element

    raise GhxComponentEditError(
        "Vector XYZ object wired to the requested Get Number inputs was not found."
    )


def find_context_bake_by_compute_param_name(
    root_element: element_tree.Element,
    compute_param_name: str,
) -> element_tree.Element:
    """Return one Context Bake object whose Content input uses the given param name."""
    for object_element in iter_object_elements(root_element):
        object_component_name = find_item_text(object_element.find("items"), "Name")
        if object_component_name != CONTEXT_BAKE_COMPONENT_NAME:
            continue

        content_param_nickname = _read_param_nickname(
            object_element,
            CONTEXT_BAKE_CONTENT_PARAM_NICKNAME,
        )
        content_param_name = _read_param_name(
            object_element,
            CONTEXT_BAKE_CONTENT_PARAM_NICKNAME,
        )
        if content_param_nickname == compute_param_name or content_param_name == compute_param_name:
            return object_element

    raise GhxComponentEditError(
        f"Context Bake object was not found for compute param {compute_param_name!r}."
    )


def read_context_bake_source_output_param_guid(
    context_bake_object_element: element_tree.Element,
) -> str:
    """Return the source output parameter GUID wired into Context Bake Content."""
    container_element = context_bake_object_element.find('./chunks/chunk[@name="Container"]')
    if container_element is None:
        raise GhxComponentEditError("Context Bake Container chunk was not found.")

    for parameter_chunk in container_element.findall('./chunks/chunk'):
        if parameter_chunk.get("name") != "param_input":
            continue
        parameter_name = find_item_text(parameter_chunk.find("items"), "Name")
        if parameter_name != CONTEXT_BAKE_CONTENT_PARAM_NICKNAME:
            continue
        source_guid = find_item_text(parameter_chunk.find("items"), "Source")
        if source_guid is None:
            raise GhxComponentEditError("Context Bake Content param is missing Source wiring.")
        return source_guid

    raise GhxComponentEditError("Context Bake Content param_input was not found.")


def write_ghx_document(root_element: element_tree.Element, output_path: Path) -> Path:
    """Write one GHX root element to disk."""
    write_ghx_root_element(root_element, output_path)
    return output_path


def load_ghx_root_from_path(source_path: Path | str) -> element_tree.Element:
    """Parse one GHX file and return its root element."""
    return parse_ghx_root_element(source_path)


def _find_script_parameter_template_element(
    root_element: element_tree.Element,
    *,
    parameter_chunk_name: str,
    parameter_name: str | None = None,
    exclude_parameter_name: str | None = None,
) -> element_tree.Element | None:
    for object_element in iter_object_elements(root_element):
        object_name = find_item_text(object_element.find("items"), "Name")
        if object_name != C_SHARP_SCRIPT_COMPONENT_NAME:
            continue
        parameter_data_element = object_element.find(
            './chunks/chunk[@name="Container"]/chunks/chunk[@name="ParameterData"]'
        )
        if parameter_data_element is None:
            continue
        parameter_chunks_element = parameter_data_element.find("chunks")
        if parameter_chunks_element is None:
            continue
        for parameter_element in parameter_chunks_element.findall(
            f'chunk[@name="{parameter_chunk_name}"]'
        ):
            current_parameter_name = find_item_text(
                parameter_element.find("items"),
                "Name",
            )
            if parameter_name is not None and current_parameter_name != parameter_name:
                continue
            if (
                exclude_parameter_name is not None
                and current_parameter_name == exclude_parameter_name
            ):
                continue
            return parameter_element
    return None


def _find_first_csharp_script_object_element(
    root_element: element_tree.Element,
) -> element_tree.Element:
    for object_element in iter_object_elements(root_element):
        object_name = find_item_text(object_element.find("items"), "Name")
        if object_name == C_SHARP_SCRIPT_COMPONENT_NAME:
            return object_element
    raise GhxComponentEditError("No C# Script template object was found.")


def _replace_script_parameter_data(
    parameter_data_element: element_tree.Element,
    *,
    input_parameter_specs: list[dict[str, str | bool]],
    output_parameter_specs: list[dict[str, str | bool]],
    root_element: element_tree.Element,
) -> None:
    parameter_chunks_element = parameter_data_element.find("chunks")
    if parameter_chunks_element is None:
        raise GhxComponentEditError("ParameterData chunks element was not found.")

    for child_chunk in list(parameter_chunks_element.findall("chunk")):
        parameter_chunks_element.remove(child_chunk)

    template_input_param_element = _find_script_parameter_template_element(
        root_element,
        parameter_chunk_name="InputParam",
    )
    template_standard_output_param_element = _find_script_parameter_template_element(
        root_element,
        parameter_chunk_name="OutputParam",
        parameter_name="out",
    )
    template_generic_output_param_element = _find_script_parameter_template_element(
        root_element,
        parameter_chunk_name="OutputParam",
        exclude_parameter_name="out",
    )
    if (
        template_input_param_element is None
        or template_standard_output_param_element is None
        or template_generic_output_param_element is None
    ):
        raise GhxComponentEditError("C# Script parameter template chunks were not found.")

    for input_index, input_parameter_spec in enumerate(input_parameter_specs):
        input_param_element = deep_copy_element(template_input_param_element)
        input_param_element.set("index", str(input_index))
        input_items_element = input_param_element.find("items")
        if input_items_element is None:
            raise GhxComponentEditError("InputParam items element was not found.")

        input_param_guid = generate_unique_instance_guid(root_element)
        set_item_text(input_items_element, "InstanceGuid", input_param_guid)
        set_item_text(
            input_items_element,
            "Name",
            str(input_parameter_spec["name"]),
        )
        set_item_text(
            input_items_element,
            "NickName",
            str(input_parameter_spec["name"]),
        )
        set_item_text(
            input_items_element,
            "TypeHintID",
            str(input_parameter_spec.get("type_hint_id", SCRIPT_GENERIC_TYPE_HINT_ID)),
        )
        script_param_access = input_parameter_spec.get(
            "script_param_access",
            SCRIPT_PARAM_ACCESS_ITEM,
        )
        set_item_text(
            input_items_element,
            "ScriptParamAccess",
            str(script_param_access),
        )
        if script_param_access == SCRIPT_PARAM_ACCESS_LIST:
            set_item_text(input_items_element, "Access", "1")
        if script_param_access == SCRIPT_PARAM_ACCESS_TREE:
            set_item_text(input_items_element, "Access", "2")

        source_guid = input_parameter_spec.get("source_guid")
        if source_guid:
            set_item_text(input_items_element, "Source", str(source_guid), item_index="0")
            set_item_text(input_items_element, "SourceCount", "1")
        else:
            for source_item in list(input_items_element.findall('item[@name="Source"]')):
                input_items_element.remove(source_item)
            set_item_text(input_items_element, "SourceCount", "0")

        update_items_count(input_items_element)
        parameter_chunks_element.append(input_param_element)

    for output_index, output_parameter_spec in enumerate(output_parameter_specs):
        if output_parameter_spec.get("is_standard_output"):
            output_template_element = template_standard_output_param_element
        else:
            output_template_element = template_generic_output_param_element
        output_param_element = deep_copy_element(output_template_element)
        output_param_element.set("index", str(output_index))
        output_items_element = output_param_element.find("items")
        if output_items_element is None:
            raise GhxComponentEditError("OutputParam items element was not found.")

        output_param_guid = generate_unique_instance_guid(root_element)
        set_item_text(output_items_element, "InstanceGuid", output_param_guid)
        output_name = str(output_parameter_spec["name"])
        set_item_text(output_items_element, "Name", output_name)
        set_item_text(output_items_element, "NickName", output_name)
        if output_parameter_spec.get("is_standard_output"):
            for type_hint_item in list(output_items_element.findall('item[@name="TypeHintID"]')):
                output_items_element.remove(type_hint_item)
            for script_param_access_item in list(
                output_items_element.findall('item[@name="ScriptParamAccess"]')
            ):
                output_items_element.remove(script_param_access_item)
        else:
            set_item_text(
                output_items_element,
                "TypeHintID",
                str(output_parameter_spec.get("type_hint_id", SCRIPT_GENERIC_TYPE_HINT_ID)),
            )
            script_param_access = output_parameter_spec.get(
                "script_param_access",
                SCRIPT_PARAM_ACCESS_ITEM,
            )
            set_item_text(
                output_items_element,
                "ScriptParamAccess",
                str(script_param_access),
            )

        update_items_count(output_items_element)
        parameter_chunks_element.append(output_param_element)

    parameter_items_element = parameter_data_element.find("items")
    if parameter_items_element is None:
        raise GhxComponentEditError("ParameterData items element was not found.")

    set_item_text(
        parameter_items_element,
        "InputCount",
        str(len(input_parameter_specs)),
    )
    set_item_text(
        parameter_items_element,
        "OutputCount",
        str(len(output_parameter_specs)),
    )

    for item_element in list(parameter_items_element.findall('item[@name="InputId"]')):
        parameter_items_element.remove(item_element)
    for item_element in list(parameter_items_element.findall('item[@name="OutputId"]')):
        parameter_items_element.remove(item_element)

    for input_index in range(len(input_parameter_specs)):
        input_id_item = element_tree.SubElement(parameter_items_element, "item")
        input_id_item.set("name", "InputId")
        input_id_item.set("index", str(input_index))
        input_id_item.set("type_name", "gh_guid")
        input_id_item.set("type_code", "9")
        input_id_item.text = SCRIPT_INPUT_PARAMETER_TYPE_GUID

    for output_index, output_parameter_spec in enumerate(output_parameter_specs):
        output_id_item = element_tree.SubElement(parameter_items_element, "item")
        output_id_item.set("name", "OutputId")
        output_id_item.set("index", str(output_index))
        output_id_item.set("type_name", "gh_guid")
        output_id_item.set("type_code", "9")
        if output_parameter_spec.get("is_standard_output"):
            output_id_item.text = SCRIPT_STANDARD_OUTPUT_TYPE_GUID
        else:
            output_id_item.text = SCRIPT_GENERIC_OUTPUT_TYPE_GUID

    update_items_count(parameter_items_element)
    reindex_named_chunks(parameter_chunks_element, "InputParam")
    reindex_named_chunks(parameter_chunks_element, "OutputParam")


def _assign_fresh_guids_to_object_element(
    root_element: element_tree.Element,
    object_element: element_tree.Element,
) -> str:
    new_container_guid = generate_unique_instance_guid(root_element)
    container_element = object_element.find('./chunks/chunk[@name="Container"]')
    if container_element is None:
        raise GhxComponentEditError("Container chunk was not found.")

    set_item_text(container_element.find("items"), "InstanceGuid", new_container_guid)

    for item_element in object_element.iter("item"):
        if item_element.get("name") != "InstanceGuid":
            continue
        if (
            container_element.find('./items/item[@name="InstanceGuid"]') is item_element
        ):
            continue
        item_element.text = generate_unique_instance_guid(root_element)

    return new_container_guid


def _load_context_bake_template_object_element() -> element_tree.Element:
    template_path = resources.files("pyghx.templates") / ADDITION_COMPUTE_TEMPLATE_NAME
    root_element = element_tree.parse(str(template_path)).getroot()
    definition_element = root_element.find('./chunks/chunk[@name="Definition"]')
    if definition_element is None:
        raise GhxComponentEditError("Definition chunk was not found in Context Bake template.")

    definition_objects_element = definition_element.find(
        './chunks/chunk[@name="DefinitionObjects"]'
    )
    if definition_objects_element is None:
        raise GhxComponentEditError("DefinitionObjects chunk was not found in template.")

    object_chunks_element = definition_objects_element.find("chunks")
    if object_chunks_element is None:
        raise GhxComponentEditError("DefinitionObjects chunks element was not found.")

    for object_element in object_chunks_element.findall("chunk"):
        object_name = find_item_text(object_element.find("items"), "Name")
        if object_name == CONTEXT_BAKE_COMPONENT_NAME:
            cloned_object_element = copy.deepcopy(object_element)
            component_guid_item = cloned_object_element.find('./items/item[@name="GUID"]')
            if component_guid_item is not None:
                component_guid_item.text = CONTEXT_BAKE_COMPONENT_TYPE_GUID
            return cloned_object_element

    raise GhxComponentEditError("Context Bake template object was not found.")


def _read_param_source_guid(
    container_element: element_tree.Element,
    parameter_nickname: str,
) -> str:
    for parameter_chunk in container_element.findall('./chunks/chunk'):
        if parameter_chunk.get("name") != "param_input":
            continue
        nickname = find_item_text(parameter_chunk.find("items"), "NickName")
        if nickname != parameter_nickname:
            continue
        source_guid = find_item_text(parameter_chunk.find("items"), "Source")
        if source_guid is None:
            raise GhxComponentEditError(
                f"Parameter {parameter_nickname!r} is missing Source wiring."
            )
        return source_guid

    raise GhxComponentEditError(f"Parameter {parameter_nickname!r} was not found.")


def _read_param_nickname(
    object_element: element_tree.Element,
    parameter_lookup_name: str,
) -> str | None:
    container_element = object_element.find('./chunks/chunk[@name="Container"]')
    if container_element is None:
        return None
    for parameter_chunk in container_element.findall('./chunks/chunk'):
        if parameter_chunk.get("name") != "param_input":
            continue
        parameter_name = find_item_text(parameter_chunk.find("items"), "Name")
        parameter_nickname = find_item_text(parameter_chunk.find("items"), "NickName")
        if parameter_lookup_name not in {parameter_name, parameter_nickname}:
            continue
        return parameter_nickname
    return None


def _set_context_bake_content_param_item_text(
    context_bake_object_element: element_tree.Element,
    *,
    item_name: str,
    item_text: str,
) -> None:
    container_element = context_bake_object_element.find('./chunks/chunk[@name="Container"]')
    if container_element is None:
        raise GhxComponentEditError("Context Bake Container chunk was not found.")

    for parameter_chunk in container_element.findall('./chunks/chunk'):
        if parameter_chunk.get("name") != "param_input":
            continue
        parameter_name = find_item_text(parameter_chunk.find("items"), "Name")
        if parameter_name != CONTEXT_BAKE_CONTENT_PARAM_NICKNAME:
            continue
        set_item_text(parameter_chunk.find("items"), item_name, item_text)
        return

    raise GhxComponentEditError("Context Bake Content param_input was not found.")


def _read_param_name(
    object_element: element_tree.Element,
    parameter_nickname: str,
) -> str | None:
    container_element = object_element.find('./chunks/chunk[@name="Container"]')
    if container_element is None:
        return None
    for parameter_chunk in container_element.findall('./chunks/chunk'):
        if parameter_chunk.get("name") != "param_input":
            continue
        nickname = find_item_text(parameter_chunk.find("items"), "NickName")
        if nickname != parameter_nickname:
            continue
        return find_item_text(parameter_chunk.find("items"), "Name")
    return None
