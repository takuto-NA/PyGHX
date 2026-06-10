"""Edit C# Script graph structure: contextual inputs, script params, and wiring."""

from __future__ import annotations

import xml.etree.ElementTree as element_tree
from pathlib import Path

from pyghx.ghx_edit import (
    GhxEditError,
    append_definition_object,
    deep_copy_element,
    find_child_chunk_element,
    find_definition_objects_element,
    find_item_text,
    find_object_element_by_component_name,
    find_object_element_by_instance_guid,
    generate_unique_instance_guid,
    iter_object_elements,
    parse_ghx_root_element,
    reindex_named_chunks,
    remove_definition_object_by_instance_guid,
    set_item_text,
    update_items_count,
    write_ghx_root_element,
)
from pyghx.script_component import (
    C_SHARP_SCRIPT_COMPONENT_NAME,
    ScriptComponentError,
    encode_script_source_text,
    get_script_source_text,
)
from pyghx.script_edit import CONTEXTUAL_INPUT_COMPONENT_NAME
from pyghx.script_source import (
    ScriptSourceError,
    parse_run_script_signature,
    synchronize_run_script_input_variables,
)

SCRIPT_INPUT_PARAMETER_TYPE_GUID = "08908df5-fa14-4982-9ab2-1aa0927566aa"
GET_NUMBER_VERTICAL_OFFSET = 97.0


class ScriptGraphEditError(Exception):
    """Raised when C# Script graph structure cannot be edited safely."""


def add_csharp_number_input(
    source_path: Path | str,
    contextual_nickname: str,
    variable_name: str,
    instance_guid: str | None = None,
) -> Path:
    """Add one Get Number input wired to a new C# Script InputParam."""
    path = Path(source_path)
    root_element = parse_ghx_root_element(path)
    script_object_element = _find_script_object_element(root_element, instance_guid)
    parameter_data_element = _find_parameter_data_element(script_object_element)
    existing_input_param_elements = _list_input_param_elements(parameter_data_element)

    if _find_input_param_by_variable_name(parameter_data_element, variable_name) is not None:
        raise ScriptGraphEditError(
            f"C# Script input variable already exists: {variable_name!r}."
        )
    if _contextual_nickname_exists(root_element, contextual_nickname):
        raise ScriptGraphEditError(
            f"Contextual input nickname already exists: {contextual_nickname!r}."
        )

    template_get_number_object = _find_get_number_template_object(root_element)
    template_input_param_element = existing_input_param_elements[-1]

    new_get_number_instance_guid = generate_unique_instance_guid(root_element)
    new_input_param_instance_guid = generate_unique_instance_guid(root_element)

    new_get_number_object = _clone_get_number_object(
        template_get_number_object,
        contextual_nickname=contextual_nickname,
        instance_guid=new_get_number_instance_guid,
    )
    append_definition_object(root_element, new_get_number_object)

    new_input_param_element = _clone_input_param_element(
        template_input_param_element,
        variable_name=variable_name,
        instance_guid=new_input_param_instance_guid,
        source_instance_guid=new_get_number_instance_guid,
        input_index=len(existing_input_param_elements),
    )
    parameter_chunks_element = parameter_data_element.find("chunks")
    if parameter_chunks_element is None:
        raise ScriptGraphEditError("ParameterData chunks element was not found.")
    parameter_chunks_element.append(new_input_param_element)

    _update_parameter_data_input_metadata(parameter_data_element)
    _synchronize_script_source_inputs(path, root_element, script_object_element, instance_guid)
    write_ghx_root_element(root_element, path)
    return path


def remove_csharp_input(
    source_path: Path | str,
    variable_name: str,
    instance_guid: str | None = None,
) -> Path:
    """Remove one C# Script input and its wired Get Number component."""
    path = Path(source_path)
    root_element = parse_ghx_root_element(path)
    script_object_element = _find_script_object_element(root_element, instance_guid)
    parameter_data_element = _find_parameter_data_element(script_object_element)
    input_param_element = _find_input_param_by_variable_name(
        parameter_data_element,
        variable_name,
    )
    if input_param_element is None:
        raise ScriptGraphEditError(f"C# Script input variable was not found: {variable_name!r}.")

    source_instance_guid = _read_input_param_source_instance_guid(input_param_element)
    if source_instance_guid is None:
        raise ScriptGraphEditError(
            f"C# Script input {variable_name!r} is not wired to a contextual source."
        )

    parameter_chunks_element = parameter_data_element.find("chunks")
    if parameter_chunks_element is None:
        raise ScriptGraphEditError("ParameterData chunks element was not found.")
    parameter_chunks_element.remove(input_param_element)
    remove_definition_object_by_instance_guid(root_element, source_instance_guid)

    _update_parameter_data_input_metadata(parameter_data_element)
    _synchronize_script_source_inputs(path, root_element, script_object_element, instance_guid)
    write_ghx_root_element(root_element, path)
    return path


def rename_csharp_input(
    source_path: Path | str,
    contextual_nickname: str,
    new_contextual_nickname: str,
    new_variable_name: str,
    instance_guid: str | None = None,
) -> Path:
    """Rename one wired Get Number nickname and its C# Script input variable."""
    path = Path(source_path)
    root_element = parse_ghx_root_element(path)
    script_object_element = _find_script_object_element(root_element, instance_guid)
    parameter_data_element = _find_parameter_data_element(script_object_element)

    get_number_object_element = _find_get_number_object_by_nickname(
        root_element,
        contextual_nickname,
    )
    if get_number_object_element is None:
        raise ScriptGraphEditError(
            f"Get Number contextual input was not found: {contextual_nickname!r}."
        )

    input_param_element = _find_input_param_by_source_nickname(
        parameter_data_element,
        get_number_object_element,
    )
    if input_param_element is None:
        raise ScriptGraphEditError(
            f"C# Script input wired to {contextual_nickname!r} was not found."
        )

    if (
        new_contextual_nickname != contextual_nickname
        and _contextual_nickname_exists(root_element, new_contextual_nickname)
    ):
        raise ScriptGraphEditError(
            f"Contextual input nickname already exists: {new_contextual_nickname!r}."
        )

    current_variable_name = find_item_text(
        input_param_element.find("items"),
        "Name",
    )
    if (
        current_variable_name is not None
        and new_variable_name != current_variable_name
        and _find_input_param_by_variable_name(parameter_data_element, new_variable_name) is not None
    ):
        raise ScriptGraphEditError(
            f"C# Script input variable already exists: {new_variable_name!r}."
        )

    get_number_container = get_number_object_element.find('./chunks/chunk[@name="Container"]')
    if get_number_container is None:
        raise ScriptGraphEditError("Get Number Container chunk was not found.")
    set_item_text(
        get_number_container.find("items"),
        "NickName",
        new_contextual_nickname,
    )

    input_items_element = input_param_element.find("items")
    if input_items_element is None:
        raise ScriptGraphEditError("InputParam items element was not found.")
    set_item_text(input_items_element, "Name", new_variable_name)
    set_item_text(input_items_element, "NickName", new_variable_name)

    _synchronize_script_source_inputs(path, root_element, script_object_element, instance_guid)
    write_ghx_root_element(root_element, path)
    return path


def _find_script_object_element(
    root_element: element_tree.Element,
    instance_guid: str | None,
) -> element_tree.Element:
    if instance_guid is not None:
        script_object_element = find_object_element_by_instance_guid(root_element, instance_guid)
        if script_object_element is None:
            raise ScriptGraphEditError(f"C# Script component was not found: {instance_guid!r}.")
        return script_object_element

    script_object_element = find_object_element_by_component_name(
        root_element,
        C_SHARP_SCRIPT_COMPONENT_NAME,
    )
    if script_object_element is None:
        raise ScriptGraphEditError("No C# Script components were found.")

    script_object_elements = [
        object_element
        for object_element in iter_object_elements(root_element)
        if find_item_text(object_element.find("items"), "Name") == C_SHARP_SCRIPT_COMPONENT_NAME
    ]
    if len(script_object_elements) != 1:
        raise ScriptGraphEditError(
            "Multiple C# Script components were found; instance_guid is required."
        )
    return script_object_elements[0]


def _find_parameter_data_element(script_object_element: element_tree.Element) -> element_tree.Element:
    container_element = script_object_element.find('./chunks/chunk[@name="Container"]')
    if container_element is None:
        raise ScriptGraphEditError("C# Script Container chunk was not found.")
    parameter_data_element = find_child_chunk_element(container_element, "ParameterData")
    if parameter_data_element is None:
        raise ScriptGraphEditError("C# Script ParameterData chunk was not found.")
    return parameter_data_element


def _list_input_param_elements(
    parameter_data_element: element_tree.Element,
) -> list[element_tree.Element]:
    parameter_chunks_element = parameter_data_element.find("chunks")
    if parameter_chunks_element is None:
        return []
    return reindex_named_chunks(parameter_chunks_element, "InputParam")


def _find_input_param_by_variable_name(
    parameter_data_element: element_tree.Element,
    variable_name: str,
) -> element_tree.Element | None:
    for input_param_element in _list_input_param_elements(parameter_data_element):
        parameter_name = find_item_text(input_param_element.find("items"), "Name")
        if parameter_name == variable_name:
            return input_param_element
    return None


def _find_input_param_by_source_nickname(
    parameter_data_element: element_tree.Element,
    get_number_object_element: element_tree.Element,
) -> element_tree.Element | None:
    get_number_container = get_number_object_element.find('./chunks/chunk[@name="Container"]')
    if get_number_container is None:
        return None
    get_number_instance_guid = find_item_text(get_number_container.find("items"), "InstanceGuid")
    if get_number_instance_guid is None:
        return None

    for input_param_element in _list_input_param_elements(parameter_data_element):
        source_instance_guid = _read_input_param_source_instance_guid(input_param_element)
        if source_instance_guid == get_number_instance_guid:
            return input_param_element
    return None


def _read_input_param_source_instance_guid(
    input_param_element: element_tree.Element,
) -> str | None:
    return find_item_text(input_param_element.find("items"), "Source")


def _find_get_number_template_object(root_element: element_tree.Element) -> element_tree.Element:
    for object_element in iter_object_elements(root_element):
        object_name = find_item_text(object_element.find("items"), "Name")
        if object_name == CONTEXTUAL_INPUT_COMPONENT_NAME:
            return object_element
    raise ScriptGraphEditError("No Get Number template object was found in the GHX file.")


def _find_get_number_object_by_nickname(
    root_element: element_tree.Element,
    contextual_nickname: str,
) -> element_tree.Element | None:
    for object_element in iter_object_elements(root_element):
        if find_item_text(object_element.find("items"), "Name") != CONTEXTUAL_INPUT_COMPONENT_NAME:
            continue
        container_element = object_element.find('./chunks/chunk[@name="Container"]')
        if container_element is None:
            continue
        nickname = find_item_text(container_element.find("items"), "NickName")
        if nickname == contextual_nickname:
            return object_element
    return None


def _contextual_nickname_exists(
    root_element: element_tree.Element,
    contextual_nickname: str,
) -> bool:
    return _find_get_number_object_by_nickname(root_element, contextual_nickname) is not None


def _clone_get_number_object(
    template_object_element: element_tree.Element,
    contextual_nickname: str,
    instance_guid: str,
) -> element_tree.Element:
    cloned_object_element = deep_copy_element(template_object_element)
    cloned_object_element.set("index", "0")

    container_element = cloned_object_element.find('./chunks/chunk[@name="Container"]')
    if container_element is None:
        raise ScriptGraphEditError("Get Number Container chunk was not found.")

    container_items_element = container_element.find("items")
    if container_items_element is None:
        raise ScriptGraphEditError("Get Number items element was not found.")

    set_item_text(container_items_element, "InstanceGuid", instance_guid)
    set_item_text(container_items_element, "NickName", contextual_nickname)
    _offset_attributes_bounds(container_element, y_offset=GET_NUMBER_VERTICAL_OFFSET)
    return cloned_object_element


def _clone_input_param_element(
    template_input_param_element: element_tree.Element,
    variable_name: str,
    instance_guid: str,
    source_instance_guid: str,
    input_index: int,
) -> element_tree.Element:
    cloned_input_param_element = deep_copy_element(template_input_param_element)
    cloned_input_param_element.set("index", str(input_index))

    items_element = cloned_input_param_element.find("items")
    if items_element is None:
        raise ScriptGraphEditError("InputParam items element was not found.")

    set_item_text(items_element, "InstanceGuid", instance_guid)
    set_item_text(items_element, "Name", variable_name)
    set_item_text(items_element, "NickName", variable_name)
    set_item_text(items_element, "Source", source_instance_guid, item_index="0")
    set_item_text(items_element, "SourceCount", "1")
    return cloned_input_param_element


def _offset_attributes_bounds(container_element: element_tree.Element, y_offset: float) -> None:
    attributes_element = find_child_chunk_element(container_element, "Attributes")
    if attributes_element is None:
        return
    bounds_item = attributes_element.find('./items/item[@name="Bounds"]')
    pivot_item = attributes_element.find('./items/item[@name="Pivot"]')
    if bounds_item is not None:
        bounds_y_element = bounds_item.find("Y")
        if bounds_y_element is not None and bounds_y_element.text is not None:
            bounds_y_element.text = str(float(bounds_y_element.text) + y_offset)
    if pivot_item is not None:
        pivot_y_element = pivot_item.find("Y")
        if pivot_y_element is not None and pivot_y_element.text is not None:
            pivot_y_element.text = str(float(pivot_y_element.text) + y_offset)


def _update_parameter_data_input_metadata(parameter_data_element: element_tree.Element) -> None:
    parameter_items_element = parameter_data_element.find("items")
    if parameter_items_element is None:
        raise ScriptGraphEditError("ParameterData items element was not found.")

    input_param_elements = _list_input_param_elements(parameter_data_element)
    set_item_text(parameter_items_element, "InputCount", str(len(input_param_elements)))

    for item_element in list(parameter_items_element.findall("item")):
        if item_element.get("name") == "InputId":
            parameter_items_element.remove(item_element)

    for input_index in range(len(input_param_elements)):
        new_input_id_item = element_tree.SubElement(parameter_items_element, "item")
        new_input_id_item.set("name", "InputId")
        new_input_id_item.set("index", str(input_index))
        new_input_id_item.set("type_name", "gh_guid")
        new_input_id_item.set("type_code", "9")
        new_input_id_item.text = SCRIPT_INPUT_PARAMETER_TYPE_GUID

    update_items_count(parameter_items_element)


def _synchronize_script_source_inputs(
    source_path: Path,
    root_element: element_tree.Element,
    script_object_element: element_tree.Element,
    instance_guid: str | None,
) -> None:
    parameter_data_element = _find_parameter_data_element(script_object_element)
    input_variable_names = [
        find_item_text(input_param_element.find("items"), "Name") or ""
        for input_param_element in _list_input_param_elements(parameter_data_element)
    ]

    try:
        current_source_text = get_script_source_text(source_path, instance_guid=instance_guid)
        updated_source_text = synchronize_run_script_input_variables(
            current_source_text,
            input_variable_names,
        )
    except (ScriptComponentError, ScriptSourceError) as synchronization_error:
        raise ScriptGraphEditError(str(synchronization_error)) from synchronization_error

    script_text_item = script_object_element.find(
        './chunks/chunk[@name="Container"]/chunks/chunk[@name="Script"]/items/item[@name="Text"]'
    )
    if script_text_item is None:
        raise ScriptGraphEditError("C# Script Text item was not found.")
    script_text_item.text = encode_script_source_text(updated_source_text)


def list_script_input_variable_names(
    source_path: Path | str,
    instance_guid: str | None = None,
) -> list[str]:
    """Return C# Script input variable names in ParameterData order."""
    path = Path(source_path)
    root_element = parse_ghx_root_element(path)
    script_object_element = _find_script_object_element(root_element, instance_guid)
    parameter_data_element = _find_parameter_data_element(script_object_element)
    return [
        find_item_text(input_param_element.find("items"), "Name") or ""
        for input_param_element in _list_input_param_elements(parameter_data_element)
    ]
