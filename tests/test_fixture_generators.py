"""End-to-end tests for C# STEP fixture generator scripts."""

from __future__ import annotations

import sys
from pathlib import Path

from pyghx.inspect import inspect_document
from pyghx.validate import validate_document

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIRECTORY = REPOSITORY_ROOT / "scripts"
if str(SCRIPTS_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIRECTORY))

from create_csharp_step_import_fixture import create_csharp_step_import_fixture
from create_csharp_step_scale_fixture import create_csharp_step_scale_fixture


def test_create_csharp_step_import_fixture_generates_valid_compute_contract(tmp_path: Path) -> None:
    generated_fixture_path = create_csharp_step_import_fixture(
        output_path=tmp_path / "csharp_step_import.ghx",
    )

    validation_result = validate_document(generated_fixture_path)
    assert validation_result.valid is True

    summary = inspect_document(generated_fixture_path)
    assert summary["object_count"] == 4
    assert summary["compute_contract"]["inputs"] == [
        {
            "nickname": "Get File Path",
            "compute_param_name": "Get File Path",
            "kind": "file_path",
            "optional": False,
            "supported": True,
        }
    ]
    assert summary["compute_contract"]["outputs"][0]["compute_param_name"] == "GeometryPieceCount"
    script_input_names = {
        script_input["name"] for script_input in summary["script_components"][0]["inputs"]
    }
    assert script_input_names == {"geometry"}


def test_create_csharp_step_scale_fixture_generates_valid_compute_contract(tmp_path: Path) -> None:
    generated_fixture_path = create_csharp_step_scale_fixture(
        output_path=tmp_path / "csharp_step_scale.ghx",
    )

    validation_result = validate_document(generated_fixture_path)
    assert validation_result.valid is True

    summary = inspect_document(generated_fixture_path)
    assert summary["object_count"] == 5
    input_nicknames = {
        contextual_input["nickname"] for contextual_input in summary["contextual_inputs"]
    }
    assert input_nicknames == {"Get File Path", "Multiplier"}
    assert summary["compute_contract"]["outputs"][0]["compute_param_name"] == "ScaledGeometryPieceCount"
    script_input_names = {
        script_input["name"] for script_input in summary["script_components"][0]["inputs"]
    }
    assert script_input_names == {"geometry", "multiplier"}

    import_to_script_connections = [
        connection
        for connection in summary["connections"]
        if connection["target_component_name"] == "C# Script"
        and connection["source_component_name"] == "Import 3DM"
    ]
    multiplier_to_script_connections = [
        connection
        for connection in summary["connections"]
        if connection["target_component_name"] == "C# Script"
        and connection["source_component_name"] == "Get Number"
    ]
    assert len(import_to_script_connections) == 1
    assert len(multiplier_to_script_connections) == 1
