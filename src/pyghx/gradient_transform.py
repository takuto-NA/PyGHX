"""Transform seven-degree-of-freedom penalty GHX files to emit penalty and Gradient in one solve."""

from __future__ import annotations

import shutil
import xml.etree.ElementTree as element_tree
from dataclasses import dataclass
from pathlib import Path

from pyghx.ghx_edit import set_item_text

from pyghx.ghx_component_edit import (
    SCRIPT_GENERIC_TYPE_HINT_ID,
    SCRIPT_NUMBER_LIST_TYPE_HINT_ID,
    SCRIPT_PARAM_ACCESS_ITEM,
    SCRIPT_PARAM_ACCESS_LIST,
    append_context_bake_object,
    append_csharp_script_object,
    find_context_bake_by_compute_param_name,
    find_get_number_instance_guid,
    find_vector_xyz_for_get_number_sources,
    load_ghx_root_from_path,
    read_component_output_param_guid,
    read_script_output_param_guid,
    wire_context_bake_to_output_param,
    wire_component_container_source,
    wire_object_param_source,
    write_ghx_document,
)

FINITE_DIFFERENCE_CASE_BUILDER_TITLE = "FiniteDifferenceCases"
PENALTY_GRADIENT_AGGREGATOR_TITLE = "PenaltyGradientAggregator"
CONTEXTUAL_INPUT_NICKNAMES = ("X", "Y", "Z", "RX", "RY", "RZ", "RS")
POSITION_GET_NUMBER_NICKNAMES = ("X", "Y", "Z")
ROTATION_GET_NUMBER_NICKNAMES = ("RX", "RY", "RZ")
VECTOR_XYZ_AXIS_NICKNAMES = ("X component", "Y component", "Z component")
PENALTY_COMPUTE_PARAM_NAME = "penalty"
GRADIENT_COMPUTE_PARAM_NAME = "Gradient"
STREAM_FILTER_OUTPUT_PARAM_NAME = "Stream"


class GradientTransformError(Exception):
    """Raised when a GHX file cannot be transformed for in-graph gradients."""


@dataclass(frozen=True)
class GradientTransformResult:
    """Paths and identifiers produced by one gradient transform."""

    source_path: Path
    output_path: Path
    case_builder_instance_guid: str
    aggregator_instance_guid: str


def transform_penalty_graph_for_gradient(
    source_path: Path | str,
    output_path: Path | str,
) -> GradientTransformResult:
    """Copy one GHX file and add in-graph forward-difference gradient evaluation."""
    source_file_path = Path(source_path)
    output_file_path = Path(output_path)

    if not source_file_path.is_file():
        raise GradientTransformError(f"Source GHX file was not found: {source_file_path}")

    output_file_path.parent.mkdir(parents=True, exist_ok=True)
    if source_file_path.resolve() != output_file_path.resolve():
        shutil.copy2(source_file_path, output_file_path)

    root_element = load_ghx_root_from_path(output_file_path)
    contextual_input_guids = _resolve_contextual_input_guids(root_element)
    position_vector_object = find_vector_xyz_for_get_number_sources(
        root_element,
        tuple(contextual_input_guids[nickname] for nickname in POSITION_GET_NUMBER_NICKNAMES),
    )
    rotation_vector_object = find_vector_xyz_for_get_number_sources(
        root_element,
        tuple(contextual_input_guids[nickname] for nickname in ROTATION_GET_NUMBER_NICKNAMES),
    )
    number_object = _find_number_object_for_get_number_source(
        root_element,
        contextual_input_guids["RS"],
    )
    penalty_context_bake_object = find_context_bake_by_compute_param_name(
        root_element,
        PENALTY_COMPUTE_PARAM_NAME,
    )
    stream_filter_object = find_stream_filter_object(root_element)
    _wire_stream_filter_gate_to_scalar_zero(root_element, stream_filter_object)
    penalty_case_tree_output_param_guid = read_component_output_param_guid(
        stream_filter_object,
        STREAM_FILTER_OUTPUT_PARAM_NAME,
    )

    case_builder_source_text = _read_repository_snippet("finite_difference_cases.cs")
    aggregator_source_text = _read_repository_snippet("penalty_gradient_aggregator.cs")

    case_builder_object, case_builder_instance_guid = append_csharp_script_object(
        root_element,
        script_source_text=case_builder_source_text,
        script_title=FINITE_DIFFERENCE_CASE_BUILDER_TITLE,
        input_parameter_specs=[
            {
                "name": nickname,
                "source_guid": contextual_input_guids[nickname],
            }
            for nickname in CONTEXTUAL_INPUT_NICKNAMES
        ],
        output_parameter_specs=[
            {"name": "out", "is_standard_output": True},
            {
                "name": "positionXList",
                "type_hint_id": SCRIPT_NUMBER_LIST_TYPE_HINT_ID,
                "script_param_access": SCRIPT_PARAM_ACCESS_LIST,
            },
            {
                "name": "positionYList",
                "type_hint_id": SCRIPT_NUMBER_LIST_TYPE_HINT_ID,
                "script_param_access": SCRIPT_PARAM_ACCESS_LIST,
            },
            {
                "name": "positionZList",
                "type_hint_id": SCRIPT_NUMBER_LIST_TYPE_HINT_ID,
                "script_param_access": SCRIPT_PARAM_ACCESS_LIST,
            },
            {
                "name": "rotationXList",
                "type_hint_id": SCRIPT_NUMBER_LIST_TYPE_HINT_ID,
                "script_param_access": SCRIPT_PARAM_ACCESS_LIST,
            },
            {
                "name": "rotationYList",
                "type_hint_id": SCRIPT_NUMBER_LIST_TYPE_HINT_ID,
                "script_param_access": SCRIPT_PARAM_ACCESS_LIST,
            },
            {
                "name": "rotationZList",
                "type_hint_id": SCRIPT_NUMBER_LIST_TYPE_HINT_ID,
                "script_param_access": SCRIPT_PARAM_ACCESS_LIST,
            },
            {
                "name": "rsList",
                "type_hint_id": SCRIPT_NUMBER_LIST_TYPE_HINT_ID,
                "script_param_access": SCRIPT_PARAM_ACCESS_LIST,
            },
        ],
        vertical_offset=120,
    )

    aggregator_object, aggregator_instance_guid = append_csharp_script_object(
        root_element,
        script_source_text=aggregator_source_text,
        script_title=PENALTY_GRADIENT_AGGREGATOR_TITLE,
        input_parameter_specs=[
            {
                "name": "penaltyCase",
                "source_guid": penalty_case_tree_output_param_guid,
                "type_hint_id": SCRIPT_GENERIC_TYPE_HINT_ID,
                "script_param_access": SCRIPT_PARAM_ACCESS_ITEM,
            }
        ],
        output_parameter_specs=[
            {"name": "out", "is_standard_output": True},
            {
                "name": "penalty",
                "type_hint_id": SCRIPT_GENERIC_TYPE_HINT_ID,
            },
            {
                "name": "Gradient",
                "type_hint_id": SCRIPT_NUMBER_LIST_TYPE_HINT_ID,
                "script_param_access": SCRIPT_PARAM_ACCESS_LIST,
            },
        ],
        vertical_offset=240,
    )

    _rewire_vector_xyz_to_case_builder(
        position_vector_object,
        case_builder_object,
        axis_output_names=("positionXList", "positionYList", "positionZList"),
    )
    _rewire_vector_xyz_to_case_builder(
        rotation_vector_object,
        case_builder_object,
        axis_output_names=("rotationXList", "rotationYList", "rotationZList"),
    )
    wire_component_container_source(
        number_object,
        source_param_guid=read_script_output_param_guid(case_builder_object, "rsList"),
    )

    aggregator_penalty_output_guid = read_script_output_param_guid(
        aggregator_object,
        "penalty",
    )
    aggregator_gradient_output_guid = read_script_output_param_guid(
        aggregator_object,
        "Gradient",
    )

    wire_context_bake_to_output_param(
        penalty_context_bake_object,
        source_output_param_guid=aggregator_penalty_output_guid,
        compute_param_name=PENALTY_COMPUTE_PARAM_NAME,
        root_element=root_element,
    )
    append_context_bake_object(
        root_element,
        source_output_param_guid=aggregator_gradient_output_guid,
        compute_param_name=GRADIENT_COMPUTE_PARAM_NAME,
        vertical_offset=360,
    )

    write_ghx_document(root_element, output_file_path)
    return GradientTransformResult(
        source_path=source_file_path,
        output_path=output_file_path,
        case_builder_instance_guid=case_builder_instance_guid,
        aggregator_instance_guid=aggregator_instance_guid,
    )


def _resolve_contextual_input_guids(
    root_element: element_tree.Element,
) -> dict[str, str]:
    contextual_input_guids: dict[str, str] = {}
    for nickname in CONTEXTUAL_INPUT_NICKNAMES:
        contextual_input_guids[nickname] = find_get_number_instance_guid(
            root_element,
            nickname,
        )
    return contextual_input_guids


def _find_number_object_for_get_number_source(
    root_element: element_tree.Element,
    get_number_instance_guid: str,
) -> element_tree.Element:
    for object_element in root_element.iter("chunk"):
        if object_element.get("name") != "Object":
            continue
        object_component_name = object_element.find('./items/item[@name="Name"]')
        if object_component_name is None or object_component_name.text != "Number":
            continue

        container_element = object_element.find('./chunks/chunk[@name="Container"]')
        if container_element is None:
            continue

        container_items_element = container_element.find("items")
        if container_items_element is None:
            continue
        source_item = container_items_element.find('./item[@name="Source"]')
        if source_item is None or not source_item.text:
            continue
        source_guid = source_item.text

        if source_guid == get_number_instance_guid:
            return object_element

    raise GradientTransformError(
        "Number component wired to the RS contextual input was not found."
    )


def _rewire_vector_xyz_to_case_builder(
    vector_xyz_object: element_tree.Element,
    case_builder_object: element_tree.Element,
    *,
    axis_output_names: tuple[str, str, str],
) -> None:
    for axis_nickname, output_name in zip(
        VECTOR_XYZ_AXIS_NICKNAMES,
        axis_output_names,
        strict=True,
    ):
        wire_object_param_source(
            vector_xyz_object,
            parameter_nickname=axis_nickname,
            source_param_guid=read_script_output_param_guid(
                case_builder_object,
                output_name,
            ),
        )


def find_stream_filter_object(
    root_element: element_tree.Element,
) -> element_tree.Element:
    for object_element in root_element.iter("chunk"):
        if object_element.get("name") != "Object":
            continue
        object_component_name = object_element.find('./items/item[@name="Name"]')
        if object_component_name is not None and object_component_name.text == "Stream Filter":
            return object_element
    raise GradientTransformError("Stream Filter component was not found.")


def _wire_stream_filter_gate_to_scalar_zero(
    root_element: element_tree.Element,
    stream_filter_object: element_tree.Element,
) -> None:
    """Keep Stream Filter gate scalar so vectorized branches do not break filtering."""
    number_slider_instance_guid = _find_number_slider_instance_guid(root_element)
    _set_number_slider_value(root_element, number_slider_instance_guid, slider_value=0.0)
    parameter_data_element = stream_filter_object.find(
        './chunks/chunk[@name="Container"]/chunks/chunk[@name="ParameterData"]'
    )
    if parameter_data_element is None:
        raise GradientTransformError("Stream Filter ParameterData chunk was not found.")

    for input_param_element in parameter_data_element.findall('./chunks/chunk[@name="InputParam"]'):
        input_name = input_param_element.find('./items/item[@name="Name"]')
        if input_name is None or input_name.text != "Gate":
            continue
        input_items_element = input_param_element.find("items")
        if input_items_element is None:
            raise GradientTransformError("Stream Filter Gate items element was not found.")
        set_item_text(
            input_items_element,
            "Source",
            number_slider_instance_guid,
            item_index="0",
        )
        set_item_text(input_items_element, "SourceCount", "1")
        return

    raise GradientTransformError("Stream Filter Gate input was not found.")


def _find_number_slider_instance_guid(
    root_element: element_tree.Element,
) -> str:
    for object_element in root_element.iter("chunk"):
        if object_element.get("name") != "Object":
            continue
        object_component_name = object_element.find('./items/item[@name="Name"]')
        if object_component_name is None or object_component_name.text != "Number Slider":
            continue
        container_element = object_element.find('./chunks/chunk[@name="Container"]')
        if container_element is None:
            continue
        instance_guid_item = container_element.find('./items/item[@name="InstanceGuid"]')
        if instance_guid_item is None or not instance_guid_item.text:
            continue
        return instance_guid_item.text

    raise GradientTransformError("Number Slider component was not found.")


def _set_number_slider_value(
    root_element: element_tree.Element,
    number_slider_instance_guid: str,
    *,
    slider_value: float,
) -> None:
    for object_element in root_element.iter("chunk"):
        if object_element.get("name") != "Object":
            continue
        container_element = object_element.find('./chunks/chunk[@name="Container"]')
        if container_element is None:
            continue
        instance_guid_item = container_element.find('./items/item[@name="InstanceGuid"]')
        if instance_guid_item is None or instance_guid_item.text != number_slider_instance_guid:
            continue
        slider_chunk = container_element.find('./chunks/chunk[@name="Slider"]')
        if slider_chunk is None:
            raise GradientTransformError("Number Slider Slider chunk was not found.")
        set_item_text(slider_chunk.find("items"), "Value", str(slider_value))
        return

    raise GradientTransformError(
        f"Number Slider object was not found: {number_slider_instance_guid!r}."
    )


def _read_repository_snippet(snippet_filename: str) -> str:
    snippet_path = Path(__file__).resolve().parents[2] / "scripts" / "snippets" / snippet_filename
    if not snippet_path.is_file():
        raise GradientTransformError(f"Snippet file was not found: {snippet_filename}")
    return snippet_path.read_text(encoding="utf-8")
