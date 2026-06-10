"""Regression tests for C# Script input wiring validation and inspect resolution."""

from __future__ import annotations

import shutil
import uuid
import xml.etree.ElementTree as element_tree

import pytest

from pyghx.compute import ComputeInputValue, evaluate_document
from pyghx.inspect import inspect_document
from pyghx.loader import build_instance_guid_owner_map, load_ghx_document
from pyghx.script_component import extract_script_components
from pyghx.script_validate import (
    SCRIPT_INPUT_ERROR_CODE_CSHARP_SELF_REFERENCE,
    SCRIPT_INPUT_ERROR_CODE_UNKNOWN_SOURCE,
    ScriptInputSourceResolution,
    build_script_validation_diagnostics,
    classify_script_input_source_diagnostic,
    resolve_script_input_source,
)
from pyghx.validate import validate_document
from tests.helpers import (
    CSHARP_ADDITION_FIXTURE_PATH,
    CSHARP_STEP_IMPORT_FIXTURE_PATH,
    CSHARP_STEP_SCALE_FIXTURE_PATH,
    IMPORT_MODEL_FIXTURE_PATH,
)

UNREACHABLE_COMPUTE_URL = "http://localhost:1/"

SCRIPT_WIRING_ERROR_CODES = {
    SCRIPT_INPUT_ERROR_CODE_UNKNOWN_SOURCE,
    SCRIPT_INPUT_ERROR_CODE_CSHARP_SELF_REFERENCE,
    "script_input_not_wired",
}


def _script_wiring_error_codes(diagnostics: list[dict[str, str]]) -> set[str]:
    return {
        diagnostic["code"]
        for diagnostic in diagnostics
        if diagnostic["level"] == "error" and diagnostic["code"] in SCRIPT_WIRING_ERROR_CODES
    }


def test_csharp_step_import_accepts_import_3dm_output_param_wiring() -> None:
    validation_result = validate_document(CSHARP_STEP_IMPORT_FIXTURE_PATH)
    assert validation_result.valid is True
    assert _script_wiring_error_codes(list(validation_result.diagnostics)) == set()


def test_csharp_addition_accepts_get_number_component_wiring() -> None:
    validation_result = validate_document(CSHARP_ADDITION_FIXTURE_PATH)
    assert validation_result.valid is True
    assert _script_wiring_error_codes(list(validation_result.diagnostics)) == set()


@pytest.mark.parametrize(
    "fixture_path",
    [
        CSHARP_ADDITION_FIXTURE_PATH,
        CSHARP_STEP_IMPORT_FIXTURE_PATH,
        CSHARP_STEP_SCALE_FIXTURE_PATH,
        IMPORT_MODEL_FIXTURE_PATH,
    ],
)
def test_public_script_fixtures_have_no_script_wiring_false_positives(fixture_path) -> None:
    diagnostics = build_script_validation_diagnostics(str(fixture_path))
    assert _script_wiring_error_codes(diagnostics) == set()


def test_resolve_script_input_source_accepts_import_3dm_geometry_output_param() -> None:
    document = load_ghx_document(CSHARP_STEP_IMPORT_FIXTURE_PATH)
    guid_owner_map = build_instance_guid_owner_map(document.objects)
    script_summary = next(iter(extract_script_components(document)))
    geometry_input = next(script_input for script_input in script_summary.inputs if script_input.name == "geometry")
    import_geometry_output_guid = geometry_input.source_instance_guids[0]

    source_resolution = resolve_script_input_source(
        source_instance_guid=import_geometry_output_guid,
        guid_owner_map=guid_owner_map,
    )
    assert source_resolution == ScriptInputSourceResolution.VALID
    assert guid_owner_map[import_geometry_output_guid].component_name == "Import 3DM"


def test_resolve_script_input_source_accepts_get_number_component_instance() -> None:
    document = load_ghx_document(CSHARP_ADDITION_FIXTURE_PATH)
    guid_owner_map = build_instance_guid_owner_map(document.objects)
    get_number_instance_guid = "6ff49b4e-be51-4113-a28d-f99ca930859d"

    source_resolution = resolve_script_input_source(
        source_instance_guid=get_number_instance_guid,
        guid_owner_map=guid_owner_map,
    )
    assert source_resolution == ScriptInputSourceResolution.VALID
    assert guid_owner_map[get_number_instance_guid].component_name == "Get Number"


def test_classify_script_input_source_rejects_unknown_guid() -> None:
    document = load_ghx_document(CSHARP_STEP_IMPORT_FIXTURE_PATH)
    guid_owner_map = build_instance_guid_owner_map(document.objects)
    unknown_source_guid = str(uuid.uuid4())

    wiring_diagnostic = classify_script_input_source_diagnostic(
        script_label="C# Script",
        script_input_name="geometry",
        source_instance_guid=unknown_source_guid,
        guid_owner_map=guid_owner_map,
    )
    assert wiring_diagnostic is not None
    assert wiring_diagnostic["code"] == SCRIPT_INPUT_ERROR_CODE_UNKNOWN_SOURCE


def test_classify_script_input_source_rejects_csharp_script_self_wire() -> None:
    document = load_ghx_document(CSHARP_ADDITION_FIXTURE_PATH)
    guid_owner_map = build_instance_guid_owner_map(document.objects)
    csharp_script_instance_guid = "ab5f4b4a-e3b5-4249-8d53-0d1439cf904e"

    wiring_diagnostic = classify_script_input_source_diagnostic(
        script_label="C# Script",
        script_input_name="x",
        source_instance_guid=csharp_script_instance_guid,
        guid_owner_map=guid_owner_map,
    )
    assert wiring_diagnostic is not None
    assert wiring_diagnostic["code"] == SCRIPT_INPUT_ERROR_CODE_CSHARP_SELF_REFERENCE


def _find_script_input_param_by_nickname(
    root_element: element_tree.Element,
    parameter_nickname: str,
) -> element_tree.Element:
    for input_param_element in root_element.iter("chunk"):
        if input_param_element.get("name") != "InputParam":
            continue
        nickname_item = input_param_element.find('./items/item[@name="NickName"]')
        if nickname_item is not None and nickname_item.text == parameter_nickname:
            return input_param_element
    raise AssertionError(f"InputParam {parameter_nickname!r} was not found.")


def test_mutated_import_3dm_to_script_wiring_with_unknown_guid_fails_validate(tmp_path) -> None:
    output_path = tmp_path / "broken_import_to_script_wiring.ghx"
    shutil.copy(CSHARP_STEP_IMPORT_FIXTURE_PATH, output_path)

    root_element = element_tree.parse(output_path).getroot()
    geometry_input_param_element = _find_script_input_param_by_nickname(root_element, "geometry")
    source_item = geometry_input_param_element.find('./items/item[@name="Source"]')
    assert source_item is not None
    source_item.text = str(uuid.uuid4())
    element_tree.ElementTree(root_element).write(output_path, encoding="utf-8")

    validation_result = validate_document(output_path)
    assert validation_result.valid is False
    assert SCRIPT_INPUT_ERROR_CODE_UNKNOWN_SOURCE in _script_wiring_error_codes(
        list(validation_result.diagnostics)
    )


def test_mutated_import_3dm_to_script_wiring_with_unknown_guid_fails_compute_preflight(
    tmp_path,
) -> None:
    output_path = tmp_path / "broken_import_to_script_wiring.ghx"
    shutil.copy(CSHARP_STEP_IMPORT_FIXTURE_PATH, output_path)

    root_element = element_tree.parse(output_path).getroot()
    geometry_input_param_element = _find_script_input_param_by_nickname(root_element, "geometry")
    source_item = geometry_input_param_element.find('./items/item[@name="Source"]')
    assert source_item is not None
    source_item.text = str(uuid.uuid4())
    element_tree.ElementTree(root_element).write(output_path, encoding="utf-8")

    compute_result = evaluate_document(
        output_path,
        input_values=[
            ComputeInputValue(
                nickname="Get File Path",
                value=r"C:\models\example.stp",
                kind="file_path",
            )
        ],
        compute_url=UNREACHABLE_COMPUTE_URL,
    )
    assert compute_result.success is False
    diagnostic_codes = {diagnostic["code"] for diagnostic in compute_result.diagnostics}
    assert "ghx_validation_error" in diagnostic_codes
    assert SCRIPT_INPUT_ERROR_CODE_UNKNOWN_SOURCE in diagnostic_codes
    assert "rhino_compute_unreachable" not in diagnostic_codes


def test_inspect_resolves_import_3dm_to_csharp_script_connection() -> None:
    summary = inspect_document(CSHARP_STEP_IMPORT_FIXTURE_PATH)
    import_to_script_connections = [
        connection
        for connection in summary["connections"]
        if connection["target_component_name"] == "C# Script"
        and connection["source_component_name"] == "Import 3DM"
    ]
    assert import_to_script_connections == [
        {
            "target_component_name": "C# Script",
            "target_nickname": "C# Script",
            "source_component_name": "Import 3DM",
            "source_nickname": "Import 3DM",
        }
    ]

    script_geometry_input = summary["script_components"][0]["inputs"][0]
    assert script_geometry_input["name"] == "geometry"
    assert script_geometry_input["source_count"] == 1
    assert len(script_geometry_input["source_instance_guids"]) == 1


def test_compute_preflight_allows_valid_csharp_step_import_before_rhino_compute() -> None:
    compute_result = evaluate_document(
        CSHARP_STEP_IMPORT_FIXTURE_PATH,
        input_values=[
            ComputeInputValue(
                nickname="Get File Path",
                value=r"C:\models\example.stp",
                kind="file_path",
            )
        ],
        compute_url=UNREACHABLE_COMPUTE_URL,
    )
    assert compute_result.success is False
    diagnostic_codes = {diagnostic["code"] for diagnostic in compute_result.diagnostics}
    assert "ghx_validation_error" not in diagnostic_codes
    assert "rhino_compute_unreachable" in diagnostic_codes
