"""End-to-end tests for GHX fixture generator APIs."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from pyghx.fixture_generation import (
    compose_csharp_step_script,
    create_csharp_step_import_fixture,
    create_csharp_step_scale_fixture,
    create_default_import_two_models_fixture,
    CSHARP_STEP_IMPORT_RESPONSIBILITY_LINES,
    CSHARP_STEP_IMPORT_RUN_SCRIPT_METHOD_BODY,
    CSHARP_STEP_SCALE_RESPONSIBILITY_LINES,
    CSHARP_STEP_SCALE_RUN_SCRIPT_METHOD_BODY,
    DEFAULT_CSHARP_GEOMETRY_COUNTING_SNIPPET_RELATIVE_PATH,
    DEFAULT_CSHARP_STEP_IMPORT_DEMO_SCRIPT_RELATIVE_PATH,
    DEFAULT_CSHARP_STEP_SCALE_DEMO_SCRIPT_RELATIVE_PATH,
)
from pyghx.inspect import inspect_document
from pyghx.validate import validate_document

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
IMPORT_MODEL_SOURCE_PATH = REPOSITORY_ROOT / "tests" / "fixtures" / "import_model.ghx"
GEOMETRY_COUNTING_SNIPPET_PATH = REPOSITORY_ROOT / DEFAULT_CSHARP_GEOMETRY_COUNTING_SNIPPET_RELATIVE_PATH


def test_create_csharp_step_import_fixture_generates_valid_compute_contract(tmp_path: Path) -> None:
    generated_fixture_path = create_csharp_step_import_fixture(
        output_path=tmp_path / "csharp_step_import.ghx",
        repository_root=REPOSITORY_ROOT,
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
        repository_root=REPOSITORY_ROOT,
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


def test_create_import_two_models_fixture_generates_valid_compute_contract(tmp_path: Path) -> None:
    generated_fixture_path = create_default_import_two_models_fixture(
        output_path=tmp_path / "import_two_models.ghx",
        import_model_source_path=IMPORT_MODEL_SOURCE_PATH,
    )

    validation_result = validate_document(generated_fixture_path)
    assert validation_result.valid is True

    summary = inspect_document(generated_fixture_path)
    assert summary["object_count"] == 6
    input_nicknames = {
        contextual_input["nickname"] for contextual_input in summary["contextual_inputs"]
    }
    assert input_nicknames == {"Target", "Obstacle"}
    output_param_names = {
        context_bake_output["compute_param_name"]
        for context_bake_output in summary["context_bake_outputs"]
    }
    assert output_param_names == {"TargetGeometry", "ObstacleGeometry"}


def test_csharp_step_demo_scripts_match_compose_output() -> None:
    import_demo_script_path = REPOSITORY_ROOT / DEFAULT_CSHARP_STEP_IMPORT_DEMO_SCRIPT_RELATIVE_PATH
    scale_demo_script_path = REPOSITORY_ROOT / DEFAULT_CSHARP_STEP_SCALE_DEMO_SCRIPT_RELATIVE_PATH

    expected_import_demo_script_text = compose_csharp_step_script(
        responsibility_comment_lines=CSHARP_STEP_IMPORT_RESPONSIBILITY_LINES,
        run_script_method_body=CSHARP_STEP_IMPORT_RUN_SCRIPT_METHOD_BODY,
        geometry_counting_snippet_path=GEOMETRY_COUNTING_SNIPPET_PATH,
    )
    expected_scale_demo_script_text = compose_csharp_step_script(
        responsibility_comment_lines=CSHARP_STEP_SCALE_RESPONSIBILITY_LINES,
        run_script_method_body=CSHARP_STEP_SCALE_RUN_SCRIPT_METHOD_BODY,
        geometry_counting_snippet_path=GEOMETRY_COUNTING_SNIPPET_PATH,
    )

    assert import_demo_script_path.read_text(encoding="utf-8") == expected_import_demo_script_text
    assert scale_demo_script_path.read_text(encoding="utf-8") == expected_scale_demo_script_text


def test_create_csharp_step_import_fixture_script_wrapper_generates_valid_contract(
    tmp_path: Path,
) -> None:
    generated_fixture_path = tmp_path / "wrapper_csharp_step_import.ghx"
    completed_process = subprocess.run(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "scripts" / "create_csharp_step_import_fixture.py"),
            "--output",
            str(generated_fixture_path),
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=REPOSITORY_ROOT,
    )
    assert completed_process.stdout.strip() == str(generated_fixture_path)

    validation_result = validate_document(generated_fixture_path)
    assert validation_result.valid is True

    summary = inspect_document(generated_fixture_path)
    assert summary["compute_contract"]["outputs"][0]["compute_param_name"] == "GeometryPieceCount"


def test_create_import_two_models_fixture_script_wrapper_generates_valid_contract(
    tmp_path: Path,
) -> None:
    generated_fixture_path = tmp_path / "wrapper_import_two_models.ghx"
    completed_process = subprocess.run(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "scripts" / "create_import_two_models_fixture.py"),
            "--output",
            str(generated_fixture_path),
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=REPOSITORY_ROOT,
    )
    assert completed_process.stdout.strip() == str(generated_fixture_path)

    validation_result = validate_document(generated_fixture_path)
    assert validation_result.valid is True

    summary = inspect_document(generated_fixture_path)
    input_nicknames = {
        contextual_input["nickname"] for contextual_input in summary["contextual_inputs"]
    }
    assert input_nicknames == {"Target", "Obstacle"}


def test_create_import_two_models_fixture_script_wrapper_generates_valid_contract(
    tmp_path: Path,
) -> None:
    generated_fixture_path = tmp_path / "wrapper_import_two_models.ghx"
    completed_process = subprocess.run(
        [
            sys.executable,
            str(REPOSITORY_ROOT / "scripts" / "create_import_two_models_fixture.py"),
            "--output",
            str(generated_fixture_path),
        ],
        check=True,
        capture_output=True,
        text=True,
        cwd=REPOSITORY_ROOT,
    )
    assert completed_process.stdout.strip() == str(generated_fixture_path)

    validation_result = validate_document(generated_fixture_path)
    assert validation_result.valid is True

    summary = inspect_document(generated_fixture_path)
    input_nicknames = {
        contextual_input["nickname"] for contextual_input in summary["contextual_inputs"]
    }
    assert input_nicknames == {"Target", "Obstacle"}
