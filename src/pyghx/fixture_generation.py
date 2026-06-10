"""Generate RhinoCompute-ready GHX test fixtures from template documents."""

from __future__ import annotations

import copy
import uuid
import xml.etree.ElementTree as element_tree
from dataclasses import dataclass
from pathlib import Path

from pyghx.ghx_edit import (
    GhxEditError,
    find_child_chunk_element,
    find_object_element_in_object_chunks,
    offset_object_bounds_y,
    parse_ghx_root_element,
    read_object_param_instance_guid,
    set_chunk_item_text,
    set_object_container_item_text,
    set_object_container_nickname,
    set_object_param_item_text,
)
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
DEFAULT_IMPORT_MODEL_FIXTURE_RELATIVE_PATH = Path("tests") / "fixtures" / "import_model.ghx"
DEFAULT_CSHARP_ADDITION_FIXTURE_RELATIVE_PATH = Path("tests") / "fixtures" / "csharp_addition.ghx"
DEFAULT_CSHARP_GEOMETRY_COUNTING_SNIPPET_RELATIVE_PATH = (
    Path("scripts") / "snippets" / "csharp_geometry_piece_counting.cs"
)
DEFAULT_VERTICAL_LAYOUT_OFFSET = 120


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


@dataclass(frozen=True)
class CSharpScriptInputDefinition:
    """One C# Script input wiring definition for fixture generation."""

    input_name: str
    source_kind: str
    get_number_nickname: str | None = None


SCRIPT_INPUT_SOURCE_IMPORT_GEOMETRY = "import_geometry_output"
SCRIPT_INPUT_SOURCE_GET_NUMBER = "get_number"

CSHARP_STEP_IMPORT_RESPONSIBILITY_LINES = (
    "Grasshopper C# Script: count geometry pieces imported from STEP via Import 3DM.",
    "Responsibility: accept imported geometry and output a numeric piece count for Context Bake.",
)
CSHARP_STEP_IMPORT_RUN_SCRIPT_METHOD_BODY = (
    "    private void RunScript(object geometry, ref object a)\n"
    "    {\n"
    "        a = CountGeometryPieces(geometry);\n"
    "    }"
)
CSHARP_STEP_SCALE_RESPONSIBILITY_LINES = (
    "Grasshopper C# Script: scale imported STEP geometry piece count by a contextual multiplier.",
    "Responsibility: combine Import 3DM geometry with Get Number multiplier for Context Bake output.",
)
CSHARP_STEP_SCALE_RUN_SCRIPT_METHOD_BODY = (
    "    private void RunScript(object geometry, object multiplier, ref object a)\n"
    "    {\n"
    "        int geometryPieceCount = CountGeometryPieces(geometry);\n"
    "        double multiplierValue = Convert.ToDouble(multiplier);\n"
    "        a = geometryPieceCount * multiplierValue;\n"
    "    }"
)
DEFAULT_CSHARP_STEP_IMPORT_DEMO_SCRIPT_RELATIVE_PATH = (
    Path("scripts") / "demo_csharp_step_import.cs"
)
DEFAULT_CSHARP_STEP_SCALE_DEMO_SCRIPT_RELATIVE_PATH = (
    Path("scripts") / "demo_csharp_step_scale.cs"
)


@dataclass(frozen=True)
class GetNumberObjectDefinition:
    """One Get Number clone definition for fixture generation."""

    nickname: str


@dataclass(frozen=True)
class CSharpStepFixtureDefinition:
    """Configuration for one C# Script + STEP import fixture."""

    document_name: str
    context_bake_output_param_nickname: str
    script_inputs: tuple[CSharpScriptInputDefinition, ...]
    get_number_objects: tuple[GetNumberObjectDefinition, ...] = ()
    run_script_method_body: str = ""
    responsibility_comment_lines: tuple[str, ...] = ()


@dataclass(frozen=True)
class ImportChainDefinition:
    """Configuration for one Import 3DM chain in a multi-model fixture."""

    file_path_nickname: str
    import_nickname: str
    geometry_param_nickname: str
    vertical_offset: int = 0


@dataclass(frozen=True)
class ImportTwoModelsFixtureDefinition:
    """Configuration for import_two_models.ghx generation."""

    document_name: str
    primary_chain: ImportChainDefinition
    secondary_chain: ImportChainDefinition


def load_ghx_root_element(source_path: Path) -> element_tree.Element:
    """Load one GHX file and return its root element."""
    return parse_ghx_root_element(source_path)


def prepare_import_model_fixture_context(
    import_model_root_element: element_tree.Element,
    document_name: str,
) -> ImportModelFixtureContext:
    """Remove logger/thumbnail noise and return import_model object handles."""
    definition_element = find_child_chunk_element(import_model_root_element, "Definition")
    if definition_element is None:
        raise GhxFixtureError("Definition chunk was not found in import_model fixture.")

    remove_archive_thumbnail(import_model_root_element)
    remove_logger_library(definition_element)
    remove_logger_manager_object(definition_element)
    update_definition_name(definition_element, document_name)

    definition_objects_element = find_child_chunk_element(definition_element, "DefinitionObjects")
    if definition_objects_element is None:
        raise GhxFixtureError("DefinitionObjects chunk was not found.")

    object_chunks_element = definition_objects_element.find("chunks")
    if object_chunks_element is None:
        raise GhxFixtureError("DefinitionObjects chunks element was not found.")

    import_object_element = find_object_element_in_object_chunks(
        object_chunks_element,
        IMPORT_3DM_COMPONENT_NAME,
    )
    context_bake_object_element = find_object_element_in_object_chunks(
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
    definition_element = find_child_chunk_element(csharp_addition_root_element, "Definition")
    if definition_element is None:
        raise GhxFixtureError("Definition chunk was not found in csharp_addition fixture.")

    definition_objects_element = find_child_chunk_element(definition_element, "DefinitionObjects")
    if definition_objects_element is None:
        raise GhxFixtureError("DefinitionObjects chunk was not found in csharp_addition.")

    object_chunks_element = definition_objects_element.find("chunks")
    if object_chunks_element is None:
        raise GhxFixtureError("DefinitionObjects chunks element was not found in csharp_addition.")

    csharp_script_object_element = find_object_element_in_object_chunks(
        object_chunks_element,
        CSHARP_SCRIPT_COMPONENT_NAME,
    )
    get_number_object_element = find_object_element_in_object_chunks(
        object_chunks_element,
        GET_NUMBER_COMPONENT_NAME,
    )
    if csharp_script_object_element is None or get_number_object_element is None:
        raise GhxFixtureError("C# Script or Get Number was not found in csharp_addition fixture.")

    return CSharpAdditionFixtureContext(
        csharp_script_object_element=csharp_script_object_element,
        get_number_object_element=get_number_object_element,
    )


def write_definition_fixture_root_element(
    root_element: element_tree.Element,
    definition_element: element_tree.Element,
    definition_objects_element: element_tree.Element,
    output_path: Path,
) -> Path:
    """Refresh metadata and write one prepared definition root element."""
    refresh_definition_object_chunk_metadata(definition_objects_element)
    refresh_gha_libraries_count(definition_element)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    element_tree.indent(root_element, space="  ")
    element_tree.ElementTree(root_element).write(
        output_path,
        encoding="utf-8",
        xml_declaration=True,
    )
    return output_path


def write_fixture_root_element(
    fixture_context: ImportModelFixtureContext,
    output_path: Path,
) -> Path:
    """Refresh metadata and write one prepared fixture root element."""
    return write_definition_fixture_root_element(
        root_element=fixture_context.root_element,
        definition_element=fixture_context.definition_element,
        definition_objects_element=fixture_context.definition_objects_element,
        output_path=output_path,
    )


def read_param_instance_guid(object_element: element_tree.Element, parameter_nickname: str) -> str:
    """Return one param_input/param_output InstanceGuid by NickName."""
    try:
        return read_object_param_instance_guid(object_element, parameter_nickname)
    except GhxEditError as edit_error:
        raise GhxFixtureError(str(edit_error)) from edit_error


def wire_context_bake_to_script_output(
    context_bake_object_element: element_tree.Element,
    script_output_instance_guid: str,
    context_bake_output_param_nickname: str,
) -> None:
    """Wire Context Bake Content to one C# Script output and rename the param."""
    context_bake_content_input_guid = str(uuid.uuid4())
    set_object_param_item_text(
        context_bake_object_element,
        CONTEXT_BAKE_CONTENT_PARAM_NICKNAME,
        "Source",
        script_output_instance_guid,
    )
    set_object_param_item_text(
        context_bake_object_element,
        CONTEXT_BAKE_CONTENT_PARAM_NICKNAME,
        "InstanceGuid",
        context_bake_content_input_guid,
    )
    set_object_param_item_text(
        context_bake_object_element,
        CONTEXT_BAKE_CONTENT_PARAM_NICKNAME,
        "Name",
        context_bake_output_param_nickname,
        match_item_name="NickName",
    )
    set_object_param_item_text(
        context_bake_object_element,
        context_bake_output_param_nickname,
        "NickName",
        context_bake_output_param_nickname,
        match_item_name="Name",
    )


def embed_csharp_script_source_text(
    csharp_script_object_element: element_tree.Element,
    script_source_text: str,
) -> None:
    """Embed one C# source string into a C# Script object."""
    script_text_item = csharp_script_object_element.find(
        './chunks/chunk[@name="Container"]/chunks/chunk[@name="Script"]/items/item[@name="Text"]'
    )
    if script_text_item is None:
        raise GhxFixtureError("C# Script Text item was not found.")
    script_text_item.text = encode_script_source_text(script_source_text)


def embed_csharp_script_source(
    csharp_script_object_element: element_tree.Element,
    csharp_script_source_path: Path,
) -> None:
    """Embed one C# source file into a C# Script object."""
    script_source_text = csharp_script_source_path.read_text(encoding="utf-8")
    embed_csharp_script_source_text(csharp_script_object_element, script_source_text)


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
            set_chunk_item_text(output_param_element, "InstanceGuid", script_output_instance_guid)
        if nickname_item.text == CSHARP_SCRIPT_STANDARD_OUTPUT_NICKNAME:
            set_chunk_item_text(
                output_param_element,
                "InstanceGuid",
                script_standard_output_instance_guid,
            )


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
    set_chunk_item_text(input_param_element, "InstanceGuid", input_instance_guid)
    set_chunk_item_text(input_param_element, "Name", input_name)
    set_chunk_item_text(input_param_element, "NickName", input_name)
    set_chunk_item_text(input_param_element, "Source", source_instance_guid)
    set_chunk_item_text(input_param_element, "SourceCount", "1")


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
    set_object_container_nickname(get_number_copy_element, nickname)
    set_object_container_item_text(get_number_copy_element, "InstanceGuid", get_number_instance_guid)
    return get_number_copy_element, get_number_instance_guid


def compose_csharp_step_script(
    responsibility_comment_lines: tuple[str, ...],
    run_script_method_body: str,
    geometry_counting_snippet_path: Path,
) -> str:
    """Compose one full Grasshopper C# Script source from shared counting helpers."""
    geometry_counting_snippet_text = geometry_counting_snippet_path.read_text(encoding="utf-8")
    responsibility_comment_block = "".join(
        f"// {comment_line}\n" for comment_line in responsibility_comment_lines
    )
    return (
        f"{responsibility_comment_block}"
        "#region Usings\n"
        "using System;\n"
        "using System.Collections;\n"
        "using System.Collections.Generic;\n"
        "using System.Drawing;\n\n"
        "using Rhino;\n"
        "using Rhino.Geometry;\n\n"
        "using Grasshopper;\n"
        "using Grasshopper.Kernel;\n"
        "using Grasshopper.Kernel.Data;\n"
        "using Grasshopper.Kernel.Types;\n"
        "#endregion\n\n"
        "public class Script_Instance : GH_ScriptInstance\n"
        "{\n"
        f"{run_script_method_body}\n\n"
        f"{geometry_counting_snippet_text}\n"
        "}\n"
    )


def create_csharp_step_fixture(
    fixture_definition: CSharpStepFixtureDefinition,
    output_path: Path,
    repository_root: Path,
    import_model_source_path: Path | None = None,
    csharp_addition_source_path: Path | None = None,
    geometry_counting_snippet_path: Path | None = None,
) -> Path:
    """Generate one C# Script + STEP import fixture from template documents."""
    resolved_import_model_source_path = import_model_source_path or (
        repository_root / DEFAULT_IMPORT_MODEL_FIXTURE_RELATIVE_PATH
    )
    resolved_csharp_addition_source_path = csharp_addition_source_path or (
        repository_root / DEFAULT_CSHARP_ADDITION_FIXTURE_RELATIVE_PATH
    )
    resolved_geometry_counting_snippet_path = geometry_counting_snippet_path or (
        repository_root / DEFAULT_CSHARP_GEOMETRY_COUNTING_SNIPPET_RELATIVE_PATH
    )

    import_root_element = load_ghx_root_element(resolved_import_model_source_path)
    csharp_root_element = load_ghx_root_element(resolved_csharp_addition_source_path)

    fixture_context = prepare_import_model_fixture_context(
        import_root_element,
        fixture_definition.document_name,
    )
    csharp_template_context = load_csharp_addition_fixture_context(csharp_root_element)

    csharp_script_copy_element = copy.deepcopy(csharp_template_context.csharp_script_object_element)
    import_geometry_output_guid = read_param_instance_guid(
        fixture_context.import_object_element,
        "Geometry",
    )

    get_number_copy_elements: list[element_tree.Element] = []
    get_number_instance_guids_by_nickname: dict[str, str] = {}
    for get_number_definition in fixture_definition.get_number_objects:
        get_number_copy_element, get_number_instance_guid = clone_get_number_object(
            csharp_template_context.get_number_object_element,
            get_number_definition.nickname,
        )
        get_number_copy_elements.append(get_number_copy_element)
        get_number_instance_guids_by_nickname[get_number_definition.nickname] = get_number_instance_guid

    script_instance_guid = str(uuid.uuid4())
    script_output_guid = str(uuid.uuid4())
    script_standard_output_guid = str(uuid.uuid4())

    set_object_container_item_text(csharp_script_copy_element, "InstanceGuid", script_instance_guid)
    set_csharp_script_input_count(
        csharp_script_copy_element,
        input_count=len(fixture_definition.script_inputs),
    )

    for input_param_index, script_input_definition in enumerate(fixture_definition.script_inputs):
        resolved_source_instance_guid = _resolve_script_input_source_instance_guid(
            script_input_definition=script_input_definition,
            import_geometry_output_guid=import_geometry_output_guid,
            get_number_instance_guids_by_nickname=get_number_instance_guids_by_nickname,
        )
        configure_csharp_script_input(
            csharp_script_object_element=csharp_script_copy_element,
            input_param_index=input_param_index,
            input_name=script_input_definition.input_name,
            input_instance_guid=str(uuid.uuid4()),
            source_instance_guid=resolved_source_instance_guid,
        )

    set_script_output_guids(
        csharp_script_object_element=csharp_script_copy_element,
        script_output_instance_guid=script_output_guid,
        script_standard_output_instance_guid=script_standard_output_guid,
        script_output_nickname=CSHARP_SCRIPT_DEFAULT_OUTPUT_NICKNAME,
    )

    composed_script_source_text = compose_csharp_step_script(
        responsibility_comment_lines=fixture_definition.responsibility_comment_lines,
        run_script_method_body=fixture_definition.run_script_method_body,
        geometry_counting_snippet_path=resolved_geometry_counting_snippet_path,
    )
    embed_csharp_script_source_text(csharp_script_copy_element, composed_script_source_text)

    wire_context_bake_to_script_output(
        fixture_context.context_bake_object_element,
        script_output_instance_guid=script_output_guid,
        context_bake_output_param_nickname=fixture_definition.context_bake_output_param_nickname,
    )

    for get_number_copy_element in get_number_copy_elements:
        fixture_context.object_chunks_element.append(get_number_copy_element)
    fixture_context.object_chunks_element.append(csharp_script_copy_element)
    return write_fixture_root_element(fixture_context, output_path)


def create_import_two_models_fixture(
    fixture_definition: ImportTwoModelsFixtureDefinition,
    output_path: Path,
    import_model_source_path: Path,
) -> Path:
    """Generate import_two_models.ghx with two Import 3DM chains."""
    root_element = load_ghx_root_element(import_model_source_path)
    definition_element = find_child_chunk_element(root_element, "Definition")
    if definition_element is None:
        raise GhxFixtureError("Definition chunk was not found in import_model fixture.")

    remove_archive_thumbnail(root_element)
    remove_logger_library(definition_element)
    remove_logger_manager_object(definition_element)
    update_definition_name(definition_element, fixture_definition.document_name)

    definition_objects_element = find_child_chunk_element(definition_element, "DefinitionObjects")
    if definition_objects_element is None:
        raise GhxFixtureError("DefinitionObjects chunk was not found.")

    object_chunks_element = definition_objects_element.find("chunks")
    if object_chunks_element is None:
        raise GhxFixtureError("DefinitionObjects chunks element was not found.")

    import_object_element = find_object_element_in_object_chunks(
        object_chunks_element,
        IMPORT_3DM_COMPONENT_NAME,
    )
    file_path_object_element = find_object_element_in_object_chunks(
        object_chunks_element,
        GET_FILE_PATH_COMPONENT_NAME,
    )
    context_bake_object_element = find_object_element_in_object_chunks(
        object_chunks_element,
        CONTEXT_BAKE_COMPONENT_NAME,
    )
    if (
        import_object_element is None
        or file_path_object_element is None
        or context_bake_object_element is None
    ):
        raise GhxFixtureError("Import chain objects were not found in import_model fixture.")

    secondary_import_object_element = copy.deepcopy(import_object_element)
    secondary_file_path_object_element = copy.deepcopy(file_path_object_element)
    secondary_context_bake_object_element = copy.deepcopy(context_bake_object_element)

    assign_import_chain(
        import_object_element=import_object_element,
        file_path_object_element=file_path_object_element,
        context_bake_object_element=context_bake_object_element,
        chain_definition=fixture_definition.primary_chain,
    )
    assign_import_chain(
        import_object_element=secondary_import_object_element,
        file_path_object_element=secondary_file_path_object_element,
        context_bake_object_element=secondary_context_bake_object_element,
        chain_definition=fixture_definition.secondary_chain,
    )

    object_chunks_element.append(secondary_import_object_element)
    object_chunks_element.append(secondary_file_path_object_element)
    object_chunks_element.append(secondary_context_bake_object_element)

    return write_definition_fixture_root_element(
        root_element=root_element,
        definition_element=definition_element,
        definition_objects_element=definition_objects_element,
        output_path=output_path,
    )


def assign_import_chain(
    import_object_element: element_tree.Element,
    file_path_object_element: element_tree.Element,
    context_bake_object_element: element_tree.Element,
    chain_definition: ImportChainDefinition,
) -> None:
    """Assign nicknames, GUIDs, and wiring for one Import 3DM chain."""
    file_path_instance_guid = str(uuid.uuid4())
    import_instance_guid = str(uuid.uuid4())
    import_file_input_guid = str(uuid.uuid4())
    import_geometry_output_guid = str(uuid.uuid4())
    context_bake_instance_guid = str(uuid.uuid4())
    context_bake_content_input_guid = str(uuid.uuid4())

    set_object_container_nickname(file_path_object_element, chain_definition.file_path_nickname)
    set_object_container_item_text(file_path_object_element, "InstanceGuid", file_path_instance_guid)
    offset_object_bounds_y(file_path_object_element, chain_definition.vertical_offset)

    set_object_container_nickname(import_object_element, chain_definition.import_nickname)
    set_object_container_item_text(import_object_element, "InstanceGuid", import_instance_guid)
    set_object_param_item_text(import_object_element, "File", "InstanceGuid", import_file_input_guid)
    set_object_param_item_text(import_object_element, "File", "Source", file_path_instance_guid)
    set_object_param_item_text(import_object_element, "Layer", "InstanceGuid", str(uuid.uuid4()))
    set_object_param_item_text(import_object_element, "Name", "InstanceGuid", str(uuid.uuid4()))
    set_object_param_item_text(
        import_object_element,
        "Geometry",
        "InstanceGuid",
        import_geometry_output_guid,
    )
    offset_object_bounds_y(import_object_element, chain_definition.vertical_offset)

    set_object_container_item_text(context_bake_object_element, "InstanceGuid", context_bake_instance_guid)
    set_object_param_item_text(
        context_bake_object_element,
        CONTEXT_BAKE_CONTENT_PARAM_NICKNAME,
        "InstanceGuid",
        context_bake_content_input_guid,
    )
    set_object_param_item_text(
        context_bake_object_element,
        CONTEXT_BAKE_CONTENT_PARAM_NICKNAME,
        "Source",
        import_geometry_output_guid,
    )
    set_object_param_item_text(
        context_bake_object_element,
        CONTEXT_BAKE_CONTENT_PARAM_NICKNAME,
        "Name",
        chain_definition.geometry_param_nickname,
    )
    set_object_param_item_text(
        context_bake_object_element,
        chain_definition.geometry_param_nickname,
        "NickName",
        chain_definition.geometry_param_nickname,
        match_item_name="Name",
    )
    offset_object_bounds_y(context_bake_object_element, chain_definition.vertical_offset)


def remove_logger_library(definition_element: element_tree.Element) -> None:
    """Remove Logger GHALibrary entries from one Definition chunk."""
    gha_libraries_element = find_child_chunk_element(definition_element, "GHALibraries")
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
    definition_objects_element = find_child_chunk_element(definition_element, "DefinitionObjects")
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
    definition_properties_element = find_child_chunk_element(definition_element, "DefinitionProperties")
    if definition_properties_element is None:
        raise GhxFixtureError("DefinitionProperties chunk was not found.")
    name_item = definition_properties_element.find('./items/item[@name="Name"]')
    if name_item is None:
        raise GhxFixtureError("DefinitionProperties Name item was not found.")
    name_item.text = document_name


def create_csharp_step_import_fixture(
    output_path: Path,
    repository_root: Path,
) -> Path:
    """Generate csharp_step_import.ghx from import_model and csharp_addition templates."""
    return create_csharp_step_fixture(
        fixture_definition=CSharpStepFixtureDefinition(
            document_name="csharp_step_import.ghx",
            context_bake_output_param_nickname="GeometryPieceCount",
            script_inputs=(
                CSharpScriptInputDefinition(
                    input_name="geometry",
                    source_kind=SCRIPT_INPUT_SOURCE_IMPORT_GEOMETRY,
                ),
            ),
            run_script_method_body=CSHARP_STEP_IMPORT_RUN_SCRIPT_METHOD_BODY,
            responsibility_comment_lines=CSHARP_STEP_IMPORT_RESPONSIBILITY_LINES,
        ),
        output_path=output_path,
        repository_root=repository_root,
    )


def create_csharp_step_scale_fixture(
    output_path: Path,
    repository_root: Path,
) -> Path:
    """Generate csharp_step_scale.ghx with Import 3DM geometry and Get Number multiplier."""
    return create_csharp_step_fixture(
        fixture_definition=CSharpStepFixtureDefinition(
            document_name="csharp_step_scale.ghx",
            context_bake_output_param_nickname="ScaledGeometryPieceCount",
            script_inputs=(
                CSharpScriptInputDefinition(
                    input_name="geometry",
                    source_kind=SCRIPT_INPUT_SOURCE_IMPORT_GEOMETRY,
                ),
                CSharpScriptInputDefinition(
                    input_name="multiplier",
                    source_kind=SCRIPT_INPUT_SOURCE_GET_NUMBER,
                    get_number_nickname="Multiplier",
                ),
            ),
            get_number_objects=(GetNumberObjectDefinition(nickname="Multiplier"),),
            run_script_method_body=CSHARP_STEP_SCALE_RUN_SCRIPT_METHOD_BODY,
            responsibility_comment_lines=CSHARP_STEP_SCALE_RESPONSIBILITY_LINES,
        ),
        output_path=output_path,
        repository_root=repository_root,
    )


def write_csharp_step_demo_script_files(repository_root: Path) -> tuple[Path, Path]:
    """Write demo C# Script sources that match the composed fixture script bodies."""
    geometry_counting_snippet_path = (
        repository_root / DEFAULT_CSHARP_GEOMETRY_COUNTING_SNIPPET_RELATIVE_PATH
    )
    import_demo_script_path = repository_root / DEFAULT_CSHARP_STEP_IMPORT_DEMO_SCRIPT_RELATIVE_PATH
    scale_demo_script_path = repository_root / DEFAULT_CSHARP_STEP_SCALE_DEMO_SCRIPT_RELATIVE_PATH

    import_demo_script_path.write_text(
        compose_csharp_step_script(
            responsibility_comment_lines=CSHARP_STEP_IMPORT_RESPONSIBILITY_LINES,
            run_script_method_body=CSHARP_STEP_IMPORT_RUN_SCRIPT_METHOD_BODY,
            geometry_counting_snippet_path=geometry_counting_snippet_path,
        ),
        encoding="utf-8",
    )
    scale_demo_script_path.write_text(
        compose_csharp_step_script(
            responsibility_comment_lines=CSHARP_STEP_SCALE_RESPONSIBILITY_LINES,
            run_script_method_body=CSHARP_STEP_SCALE_RUN_SCRIPT_METHOD_BODY,
            geometry_counting_snippet_path=geometry_counting_snippet_path,
        ),
        encoding="utf-8",
    )
    return import_demo_script_path, scale_demo_script_path


def create_default_import_two_models_fixture(
    output_path: Path,
    import_model_source_path: Path,
) -> Path:
    """Generate import_two_models.ghx with Target and Obstacle import chains."""
    return create_import_two_models_fixture(
        fixture_definition=ImportTwoModelsFixtureDefinition(
            document_name="import_two_models.ghx",
            primary_chain=ImportChainDefinition(
                file_path_nickname="Target",
                import_nickname="Import Target",
                geometry_param_nickname="TargetGeometry",
                vertical_offset=0,
            ),
            secondary_chain=ImportChainDefinition(
                file_path_nickname="Obstacle",
                import_nickname="Import Obstacle",
                geometry_param_nickname="ObstacleGeometry",
                vertical_offset=DEFAULT_VERTICAL_LAYOUT_OFFSET,
            ),
        ),
        output_path=output_path,
        import_model_source_path=import_model_source_path,
    )


def _resolve_script_input_source_instance_guid(
    script_input_definition: CSharpScriptInputDefinition,
    import_geometry_output_guid: str,
    get_number_instance_guids_by_nickname: dict[str, str],
) -> str:
    if script_input_definition.source_kind == SCRIPT_INPUT_SOURCE_IMPORT_GEOMETRY:
        return import_geometry_output_guid

    if script_input_definition.source_kind == SCRIPT_INPUT_SOURCE_GET_NUMBER:
        if script_input_definition.get_number_nickname is None:
            raise GhxFixtureError(
                f"C# Script input {script_input_definition.input_name!r} requires get_number_nickname."
            )
        get_number_instance_guid = get_number_instance_guids_by_nickname.get(
            script_input_definition.get_number_nickname
        )
        if get_number_instance_guid is None:
            raise GhxFixtureError(
                f"Get Number nickname {script_input_definition.get_number_nickname!r} "
                "was not created for this fixture."
            )
        return get_number_instance_guid

    raise GhxFixtureError(
        f"Unsupported C# Script input source kind {script_input_definition.source_kind!r}."
    )


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
