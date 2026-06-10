"""Create csharp_step_scale.ghx: STEP import + Get Number multiplier through C# Script."""

from __future__ import annotations

import copy
import sys
import uuid
from pathlib import Path

SCRIPTS_DIRECTORY = Path(__file__).resolve().parent
if str(SCRIPTS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIRECTORY))

from ghx_fixture_utils import (
    CSHARP_SCRIPT_DEFAULT_OUTPUT_NICKNAME,
    clone_get_number_object,
    configure_csharp_script_input,
    embed_csharp_script_source,
    load_csharp_addition_fixture_context,
    load_ghx_root_element,
    prepare_import_model_fixture_context,
    read_param_instance_guid,
    set_container_item_text,
    set_script_output_guids,
    wire_context_bake_to_script_output,
    write_fixture_root_element,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
IMPORT_MODEL_SOURCE_PATH = REPOSITORY_ROOT / "tests" / "fixtures" / "import_model.ghx"
CSHARP_ADDITION_SOURCE_PATH = REPOSITORY_ROOT / "tests" / "fixtures" / "csharp_addition.ghx"
CSHARP_SCRIPT_SOURCE_PATH = REPOSITORY_ROOT / "scripts" / "demo_csharp_step_scale.cs"
OUTPUT_PATH = REPOSITORY_ROOT / "tests" / "fixtures" / "csharp_step_scale.ghx"
DOCUMENT_NAME = "csharp_step_scale.ghx"
MULTIPLIER_INPUT_NICKNAME = "Multiplier"
CSHARP_GEOMETRY_INPUT_NICKNAME = "geometry"
CSHARP_MULTIPLIER_INPUT_NICKNAME = "multiplier"
CONTEXT_BAKE_OUTPUT_PARAM_NICKNAME = "ScaledGeometryPieceCount"


def create_csharp_step_scale_fixture(output_path: Path | None = None) -> Path:
    destination_path = output_path or OUTPUT_PATH
    import_root_element = load_ghx_root_element(IMPORT_MODEL_SOURCE_PATH)
    csharp_root_element = load_ghx_root_element(CSHARP_ADDITION_SOURCE_PATH)

    fixture_context = prepare_import_model_fixture_context(import_root_element, DOCUMENT_NAME)
    csharp_template_context = load_csharp_addition_fixture_context(csharp_root_element)

    csharp_script_copy_element = copy.deepcopy(csharp_template_context.csharp_script_object_element)
    multiplier_copy_element, multiplier_instance_guid = clone_get_number_object(
        csharp_template_context.get_number_object_element,
        MULTIPLIER_INPUT_NICKNAME,
    )

    import_geometry_output_guid = read_param_instance_guid(
        fixture_context.import_object_element,
        "Geometry",
    )
    script_instance_guid = str(uuid.uuid4())
    script_geometry_input_guid = str(uuid.uuid4())
    script_multiplier_input_guid = str(uuid.uuid4())
    script_output_guid = str(uuid.uuid4())
    script_standard_output_guid = str(uuid.uuid4())

    set_container_item_text(csharp_script_copy_element, "InstanceGuid", script_instance_guid)
    configure_csharp_script_input(
        csharp_script_object_element=csharp_script_copy_element,
        input_param_index=0,
        input_name=CSHARP_GEOMETRY_INPUT_NICKNAME,
        input_instance_guid=script_geometry_input_guid,
        source_instance_guid=import_geometry_output_guid,
    )
    configure_csharp_script_input(
        csharp_script_object_element=csharp_script_copy_element,
        input_param_index=1,
        input_name=CSHARP_MULTIPLIER_INPUT_NICKNAME,
        input_instance_guid=script_multiplier_input_guid,
        source_instance_guid=multiplier_instance_guid,
    )
    set_script_output_guids(
        csharp_script_object_element=csharp_script_copy_element,
        script_output_instance_guid=script_output_guid,
        script_standard_output_instance_guid=script_standard_output_guid,
        script_output_nickname=CSHARP_SCRIPT_DEFAULT_OUTPUT_NICKNAME,
    )
    embed_csharp_script_source(csharp_script_copy_element, CSHARP_SCRIPT_SOURCE_PATH)
    wire_context_bake_to_script_output(
        fixture_context.context_bake_object_element,
        script_output_instance_guid=script_output_guid,
        context_bake_output_param_nickname=CONTEXT_BAKE_OUTPUT_PARAM_NICKNAME,
    )

    fixture_context.object_chunks_element.append(multiplier_copy_element)
    fixture_context.object_chunks_element.append(csharp_script_copy_element)
    return write_fixture_root_element(fixture_context, destination_path)


if __name__ == "__main__":
    fixture_path = create_csharp_step_scale_fixture()
    print(fixture_path)
