"""CLI integration tests."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from pyghx.generate import generate_minimal_document
from pyghx.validate import validate_document
from tests.helpers import (
    ADDITION_FIXTURE_PATH,
    CSHARP_ADDITION_FIXTURE_PATH,
    CSHARP_ADDITION_RAW_FIXTURE_PATH,
    MALFORMED_FIXTURE_PATH,
    VARIATION_FIXTURE_PATH,
    parse_cli_json,
    run_pyghx_cli,
)


def test_cli_help() -> None:
    completed_process = run_pyghx_cli(["--help"])
    assert completed_process.returncode == 0
    assert "inspect" in completed_process.stdout


def test_cli_inspect_json_addition() -> None:
    completed_process = run_pyghx_cli(["inspect", str(ADDITION_FIXTURE_PATH), "--json"])
    assert completed_process.returncode == 0
    summary = parse_cli_json(completed_process.stdout)
    assert summary["document_metadata"]["document_name"] == "addition.ghx"
    assert summary["schema_version"] == "2"
    assert summary["compute_contract"]["outputs"][0]["label"] == "addition"
    assert "objects" not in summary


def test_cli_inspect_full_json_addition() -> None:
    completed_process = run_pyghx_cli(["inspect", str(ADDITION_FIXTURE_PATH), "--json", "--full"])
    assert completed_process.returncode == 0
    summary = parse_cli_json(completed_process.stdout)
    assert "objects" in summary


def test_cli_validate_addition() -> None:
    completed_process = run_pyghx_cli(["validate", str(ADDITION_FIXTURE_PATH)])
    assert completed_process.returncode == 0


def test_cli_validate_malformed() -> None:
    completed_process = run_pyghx_cli(["validate", str(MALFORMED_FIXTURE_PATH)])
    assert completed_process.returncode == 1


def test_cli_generate_minimal_round_trip(tmp_path: Path) -> None:
    output_path = tmp_path / "generated.ghx"
    completed_process = run_pyghx_cli(["generate-minimal", "--output", str(output_path)])
    assert completed_process.returncode == 0
    assert output_path.exists()

    validation_result = validate_document(output_path)
    assert validation_result.valid is True

    inspect_process = run_pyghx_cli(["inspect", str(output_path), "--json"])
    assert inspect_process.returncode == 0
    summary = json.loads(inspect_process.stdout)
    assert summary["object_count"] == 0


def test_cli_generate_addition_round_trip(tmp_path: Path) -> None:
    output_path = tmp_path / "generated_addition.ghx"
    generate_process = run_pyghx_cli(
        ["generate-addition", "--output", str(output_path)]
    )
    assert generate_process.returncode == 0
    assert output_path.exists()

    inspect_process = run_pyghx_cli(["inspect", str(output_path), "--json"])
    assert inspect_process.returncode == 0
    summary = parse_cli_json(inspect_process.stdout)
    assert summary["compute_contract"]["inputs"] == [
        {
            "nickname": "X",
            "compute_param_name": "X",
            "kind": "number",
            "optional": False,
            "supported": True,
        },
        {
            "nickname": "Y",
            "compute_param_name": "Y",
            "kind": "number",
            "optional": False,
            "supported": True,
        },
    ]
    assert summary["compute_contract"]["outputs"][0]["label"] == "addition"

    validate_process = run_pyghx_cli(["validate", str(output_path)])
    assert validate_process.returncode == 0


def test_cli_inspect_variation_json() -> None:
    completed_process = run_pyghx_cli(["inspect", str(VARIATION_FIXTURE_PATH), "--json"])
    assert completed_process.returncode == 0
    summary = parse_cli_json(completed_process.stdout)
    assert len(summary["context_bake_outputs"]) == 6


def test_cli_inspect_csharp_addition_json() -> None:
    completed_process = run_pyghx_cli(
        ["inspect", str(CSHARP_ADDITION_FIXTURE_PATH), "--json"]
    )
    assert completed_process.returncode == 0
    summary = parse_cli_json(completed_process.stdout)
    assert len(summary["script_components"]) == 1
    assert "RunScript(object x, object y, ref object a)" in summary["script_components"][0]["source_text"]


def test_cli_generate_csharp_addition_round_trip(tmp_path: Path) -> None:
    output_path = tmp_path / "generated_csharp_addition.ghx"
    generate_process = run_pyghx_cli(
        ["generate-csharp-addition", "--output", str(output_path)]
    )
    assert generate_process.returncode == 0
    assert output_path.exists()

    inspect_process = run_pyghx_cli(["inspect", str(output_path), "--json"])
    assert inspect_process.returncode == 0
    summary = parse_cli_json(inspect_process.stdout)
    assert summary["compute_contract"]["outputs"][0]["source_component_name"] == "C# Script"

    validate_process = run_pyghx_cli(["validate", str(output_path)])
    assert validate_process.returncode == 0


def test_cli_get_and_set_script_source_round_trip(tmp_path: Path) -> None:
    output_path = tmp_path / "edited_csharp_addition.ghx"
    shutil.copy(CSHARP_ADDITION_FIXTURE_PATH, output_path)

    get_process = run_pyghx_cli(["get-script-source", str(output_path)])
    assert get_process.returncode == 0
    original_source_text = get_process.stdout

    replacement_source_text = original_source_text.replace(
        "firstNumber + secondNumber",
        "firstNumber * secondNumber",
    )
    set_process = run_pyghx_cli(
        [
            "set-script-source",
            str(output_path),
            "--source-text",
            replacement_source_text,
        ]
    )
    assert set_process.returncode == 0

    get_updated_process = run_pyghx_cli(["get-script-source", str(output_path)])
    assert get_updated_process.returncode == 0
    assert "firstNumber * secondNumber" in get_updated_process.stdout


def test_cli_repair_raw_csharp_fixture_via_cli(tmp_path: Path) -> None:
    repaired_path = tmp_path / "repaired_csharp_addition.ghx"
    shutil.copy(CSHARP_ADDITION_RAW_FIXTURE_PATH, repaired_path)

    raw_validate_process = run_pyghx_cli(["validate", str(repaired_path), "--json"])
    assert raw_validate_process.returncode == 1
    raw_validation = parse_cli_json(raw_validate_process.stdout)
    assert any(
        diagnostic["code"] == "duplicate_compute_input_param_name"
        for diagnostic in raw_validation["diagnostics"]
    )

    repair_process = run_pyghx_cli(
        [
            "repair-contextual-inputs",
            str(repaired_path),
            "--nickname",
            "6ff49b4e-be51-4113-a28d-f99ca930859d=X",
            "--nickname",
            "19e82177-c780-4c7e-995c-4da6b1579038=Y",
        ]
    )
    assert repair_process.returncode == 0

    remove_context_bake_process = run_pyghx_cli(
        [
            "remove-context-bake",
            str(repaired_path),
            "c5bbe4a9-4b2c-4253-9a8c-03da1002ae74",
        ]
    )
    assert remove_context_bake_process.returncode == 0

    fixed_source_path = tmp_path / "fixed_script.cs"
    fixed_source_process = run_pyghx_cli(
        ["get-script-source", str(CSHARP_ADDITION_FIXTURE_PATH)]
    )
    assert fixed_source_process.returncode == 0
    fixed_source_path.write_text(fixed_source_process.stdout, encoding="utf-8")

    set_script_process = run_pyghx_cli(
        [
            "set-script-source",
            str(repaired_path),
            "--source-file",
            str(fixed_source_path),
        ]
    )
    assert set_script_process.returncode == 0

    repaired_validate_process = run_pyghx_cli(["validate", str(repaired_path)])
    assert repaired_validate_process.returncode == 0


def test_cli_add_csharp_number_input_reports_duplicate_variable_name(tmp_path: Path) -> None:
    output_path = tmp_path / "duplicate_variable_name.ghx"
    shutil.copy(CSHARP_ADDITION_FIXTURE_PATH, output_path)

    duplicate_add_process = run_pyghx_cli(
        [
            "add-csharp-number-input",
            str(output_path),
            "--name",
            "Z",
            "--variable-name",
            "x",
        ]
    )
    assert duplicate_add_process.returncode == 1
    assert "already exists" in duplicate_add_process.stderr


def test_cli_add_csharp_number_input_round_trip(tmp_path: Path) -> None:
    output_path = tmp_path / "cli_three_input_addition.ghx"
    shutil.copy(CSHARP_ADDITION_FIXTURE_PATH, output_path)

    add_process = run_pyghx_cli(
        [
            "add-csharp-number-input",
            str(output_path),
            "--name",
            "Z",
            "--variable-name",
            "z",
        ]
    )
    assert add_process.returncode == 0

    inspect_process = run_pyghx_cli(["inspect", str(output_path), "--json"])
    assert inspect_process.returncode == 0
    summary = parse_cli_json(inspect_process.stdout)
    contextual_nicknames = {
        contextual_input["nickname"] for contextual_input in summary["contextual_inputs"]
    }
    assert contextual_nicknames == {"X", "Y", "Z"}

    validate_process = run_pyghx_cli(["validate", str(output_path)])
    assert validate_process.returncode == 0


def test_cli_rename_and_remove_csharp_input_round_trip(tmp_path: Path) -> None:
    output_path = tmp_path / "cli_renamed_input_addition.ghx"
    shutil.copy(CSHARP_ADDITION_FIXTURE_PATH, output_path)

    rename_process = run_pyghx_cli(
        [
            "rename-csharp-input",
            str(output_path),
            "--name",
            "X",
            "--new-name",
            "Length",
            "--variable-name",
            "length",
        ]
    )
    assert rename_process.returncode == 0

    inspect_process = run_pyghx_cli(["inspect", str(output_path), "--json"])
    assert inspect_process.returncode == 0
    summary = parse_cli_json(inspect_process.stdout)
    contextual_nicknames = {
        contextual_input["nickname"] for contextual_input in summary["contextual_inputs"]
    }
    assert contextual_nicknames == {"Length", "Y"}

    add_process = run_pyghx_cli(
        [
            "add-csharp-number-input",
            str(output_path),
            "--name",
            "Z",
            "--variable-name",
            "z",
        ]
    )
    assert add_process.returncode == 0

    remove_process = run_pyghx_cli(
        [
            "remove-csharp-input",
            str(output_path),
            "--variable-name",
            "z",
        ]
    )
    assert remove_process.returncode == 0

    validate_process = run_pyghx_cli(["validate", str(output_path)])
    assert validate_process.returncode == 0
