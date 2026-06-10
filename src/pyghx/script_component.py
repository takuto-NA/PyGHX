"""Parse and encode Grasshopper C# Script component data from GHX XML."""

from __future__ import annotations

import base64
import xml.etree.ElementTree as element_tree
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pyghx.constants import CONTEXT_BAKE_COMPONENT_NAME
from pyghx.loader import (
    GhxDefinitionObject,
    GhxDocument,
    build_instance_guid_owner_map,
    load_ghx_document,
)

C_SHARP_SCRIPT_COMPONENT_NAME = "C# Script"
STANDARD_OUTPUT_PARAM_NAME = "out"


class ScriptComponentError(Exception):
    """Raised when C# Script component data cannot be parsed or encoded."""


@dataclass(frozen=True)
class ScriptParameterSummary:
    """One C# Script input or output parameter."""

    name: str
    nickname: str
    instance_guid: str | None
    optional: bool | None
    type_hint_id: str | None
    script_param_access: int | None
    source_instance_guids: tuple[str, ...]
    is_standard_output: bool


@dataclass(frozen=True)
class ScriptComponentSummary:
    """Structured summary of one C# Script component."""

    index: int
    component_guid: str | None
    instance_guid: str | None
    nickname: str | None
    language_taxon: str | None
    language_version: str | None
    encoded_source_text: str | None
    decoded_source_text: str | None
    inputs: tuple[ScriptParameterSummary, ...]
    outputs: tuple[ScriptParameterSummary, ...]
    context_bake_reachable_output_nicknames: tuple[str, ...]


def extract_script_components(document: GhxDocument) -> list[ScriptComponentSummary]:
    """Extract all C# Script components from a loaded GHX document."""
    root_element = _load_root_element(document)
    guid_owner_map = build_instance_guid_owner_map(document.objects)
    context_bake_source_guids = _collect_context_bake_source_guids(document.objects)

    script_summaries: list[ScriptComponentSummary] = []
    for definition_object in document.objects:
        if definition_object.component_name != C_SHARP_SCRIPT_COMPONENT_NAME:
            continue
        object_element = _find_object_element_for_instance_guid(
            root_element,
            definition_object.instance_guid,
        )
        if object_element is None:
            continue
        script_summaries.append(
            _parse_script_component_element(
                object_element=object_element,
                definition_object=definition_object,
                guid_owner_map=guid_owner_map,
                context_bake_source_guids=context_bake_source_guids,
            )
        )
    return script_summaries


def build_script_component_inspect_entries(document: GhxDocument) -> list[dict[str, Any]]:
    """Build JSON-serializable script component entries for inspect summaries."""
    inspect_entries: list[dict[str, Any]] = []
    for script_summary in extract_script_components(document):
        inspect_entries.append(
            {
                "index": script_summary.index,
                "component_guid": script_summary.component_guid,
                "instance_guid": script_summary.instance_guid,
                "nickname": script_summary.nickname,
                "language_taxon": script_summary.language_taxon,
                "language_version": script_summary.language_version,
                "source_text": script_summary.decoded_source_text,
                "inputs": [
                    _script_parameter_to_dict(script_parameter)
                    for script_parameter in script_summary.inputs
                ],
                "outputs": [
                    _script_parameter_to_dict(script_parameter)
                    for script_parameter in script_summary.outputs
                ],
                "context_bake_reachable_output_nicknames": list(
                    script_summary.context_bake_reachable_output_nicknames
                ),
            }
        )
    return inspect_entries


def decode_script_source_text(encoded_source_text: str) -> str:
    """Decode base64-encoded C# Script source text."""
    try:
        decoded_bytes = base64.b64decode(encoded_source_text, validate=True)
    except (ValueError, base64.binascii.Error) as decode_error:
        raise ScriptComponentError("Script source text is not valid base64.") from decode_error
    return decoded_bytes.decode("utf-8")


def encode_script_source_text(source_text: str) -> str:
    """Encode C# Script source text as base64 for GHX storage."""
    return base64.b64encode(source_text.encode("utf-8")).decode("ascii")


def get_script_source_text(source_path: Path | str, instance_guid: str | None = None) -> str:
    """Return decoded C# Script source text from a GHX file."""
    script_summary = _resolve_script_component(source_path, instance_guid)
    if script_summary.decoded_source_text is None:
        raise ScriptComponentError("Script source text is missing or invalid.")
    return script_summary.decoded_source_text


def _resolve_script_component(
    source_path: Path | str,
    instance_guid: str | None,
) -> ScriptComponentSummary:
    document = load_ghx_document(source_path)
    script_summaries = extract_script_components(document)
    if not script_summaries:
        raise ScriptComponentError("No C# Script components were found.")

    if instance_guid is None:
        if len(script_summaries) != 1:
            raise ScriptComponentError(
                "Multiple C# Script components were found; instance_guid is required."
            )
        return script_summaries[0]

    for script_summary in script_summaries:
        if script_summary.instance_guid == instance_guid:
            return script_summary
    raise ScriptComponentError(f"C# Script component was not found: {instance_guid!r}.")


def _load_root_element(document: GhxDocument) -> element_tree.Element:
    if document.archive.source_path is None:
        raise ScriptComponentError("GHX source path is required to parse script components.")
    return element_tree.parse(document.archive.source_path).getroot()


def _find_object_element_for_instance_guid(
    root_element: element_tree.Element,
    instance_guid: str | None,
) -> element_tree.Element | None:
    if instance_guid is None:
        return None

    definition_element = _find_child_chunk_element(root_element, "Definition")
    if definition_element is None:
        return None
    definition_objects_element = _find_child_chunk_element(definition_element, "DefinitionObjects")
    if definition_objects_element is None:
        return None
    object_chunks_element = definition_objects_element.find("chunks")
    if object_chunks_element is None:
        return None

    for object_element in object_chunks_element.findall("chunk"):
        if object_element.get("name") != "Object":
            continue
        container_element = object_element.find('./chunks/chunk[@name="Container"]')
        if container_element is None:
            continue
        instance_guid_item = container_element.find('./items/item[@name="InstanceGuid"]')
        if instance_guid_item is not None and instance_guid_item.text == instance_guid:
            return object_element
    return None


def _parse_script_component_element(
    object_element: element_tree.Element,
    definition_object: GhxDefinitionObject,
    guid_owner_map: dict[str, GhxDefinitionObject],
    context_bake_source_guids: set[str],
) -> ScriptComponentSummary:
    container_element = object_element.find('./chunks/chunk[@name="Container"]')
    if container_element is None:
        raise ScriptComponentError("C# Script Container chunk was not found.")

    encoded_source_text = _find_item_text(
        container_element.find('./chunks/chunk[@name="Script"]/items'),
        "Text",
    )
    decoded_source_text = _try_decode_script_source_text(encoded_source_text)
    language_taxon, language_version = _read_language_spec(container_element)
    inputs, outputs = _parse_script_parameters(container_element, guid_owner_map)

    reachable_output_nicknames: list[str] = []
    for script_output in outputs:
        if script_output.instance_guid is None:
            continue
        if script_output.instance_guid not in context_bake_source_guids:
            continue
        reachable_output_nicknames.append(script_output.nickname)

    return ScriptComponentSummary(
        index=definition_object.index,
        component_guid=definition_object.component_guid,
        instance_guid=definition_object.instance_guid,
        nickname=definition_object.nickname,
        language_taxon=language_taxon,
        language_version=language_version,
        encoded_source_text=encoded_source_text,
        decoded_source_text=decoded_source_text,
        inputs=inputs,
        outputs=outputs,
        context_bake_reachable_output_nicknames=tuple(reachable_output_nicknames),
    )


def _try_decode_script_source_text(encoded_source_text: str | None) -> str | None:
    if not encoded_source_text:
        return None
    try:
        return decode_script_source_text(encoded_source_text)
    except ScriptComponentError:
        return None


def _read_language_spec(container_element: element_tree.Element) -> tuple[str | None, str | None]:
    language_spec_element = container_element.find('./chunks/chunk[@name="Script"]/chunks/chunk[@name="LanguageSpec"]')
    if language_spec_element is None:
        return None, None
    language_taxon = _find_item_text(language_spec_element.find("items"), "Taxon")
    language_version = _find_item_text(language_spec_element.find("items"), "Version")
    return language_taxon, language_version


def _parse_script_parameters(
    container_element: element_tree.Element,
    guid_owner_map: dict[str, GhxDefinitionObject],
) -> tuple[tuple[ScriptParameterSummary, ...], tuple[ScriptParameterSummary, ...]]:
    parameter_data_element = container_element.find('./chunks/chunk[@name="ParameterData"]')
    if parameter_data_element is None:
        return (), ()

    parameter_chunks_element = parameter_data_element.find("chunks")
    if parameter_chunks_element is None:
        return (), ()

    input_parameters: list[ScriptParameterSummary] = []
    output_parameters: list[ScriptParameterSummary] = []
    for parameter_element in parameter_chunks_element.findall("chunk"):
        parameter_name = parameter_element.get("name")
        if parameter_name == "InputParam":
            input_parameters.append(_parse_script_parameter_element(parameter_element, guid_owner_map))
        if parameter_name == "OutputParam":
            output_parameters.append(_parse_script_parameter_element(parameter_element, guid_owner_map))
    return tuple(input_parameters), tuple(output_parameters)


def _parse_script_parameter_element(
    parameter_element: element_tree.Element,
    guid_owner_map: dict[str, GhxDefinitionObject],
) -> ScriptParameterSummary:
    items_element = parameter_element.find("items")
    parameter_name = _find_item_text(items_element, "Name") or ""
    parameter_nickname = _find_item_text(items_element, "NickName") or parameter_name
    optional_text = _find_item_text(items_element, "Optional")
    optional_value = optional_text.lower() == "true" if optional_text is not None else None
    source_guids = _collect_source_guids_from_items(items_element)
    return ScriptParameterSummary(
        name=parameter_name,
        nickname=parameter_nickname,
        instance_guid=_find_item_text(items_element, "InstanceGuid"),
        optional=optional_value,
        type_hint_id=_find_item_text(items_element, "TypeHintID"),
        script_param_access=_parse_optional_int(_find_item_text(items_element, "ScriptParamAccess")),
        source_instance_guids=source_guids,
        is_standard_output=parameter_name == STANDARD_OUTPUT_PARAM_NAME,
    )


def _collect_context_bake_source_guids(objects: tuple[GhxDefinitionObject, ...]) -> set[str]:
    context_bake_source_guids: set[str] = set()
    for definition_object in objects:
        if definition_object.component_name != CONTEXT_BAKE_COMPONENT_NAME:
            continue
        context_bake_source_guids.update(definition_object.source_guids)
    return context_bake_source_guids


def _collect_source_guids_from_items(items_element: element_tree.Element | None) -> tuple[str, ...]:
    if items_element is None:
        return ()
    source_guids: list[str] = []
    for item_element in items_element.findall("item"):
        if item_element.get("name") == "Source" and item_element.text:
            source_guids.append(item_element.text)
    return tuple(source_guids)


def _script_parameter_to_dict(script_parameter: ScriptParameterSummary) -> dict[str, Any]:
    return {
        "name": script_parameter.name,
        "nickname": script_parameter.nickname,
        "instance_guid": script_parameter.instance_guid,
        "optional": script_parameter.optional,
        "type_hint_id": script_parameter.type_hint_id,
        "script_param_access": script_parameter.script_param_access,
        "source_instance_guids": list(script_parameter.source_instance_guids),
        "is_standard_output": script_parameter.is_standard_output,
    }


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


def _find_item_text(items_element: element_tree.Element | None, item_name: str) -> str | None:
    if items_element is None:
        return None
    for item_element in items_element.findall("item"):
        if item_element.get("name") == item_name:
            return item_element.text
    return None


def _parse_optional_int(raw_value: str | None) -> int | None:
    if raw_value is None:
        return None
    return int(raw_value)
