"""Tests for editable C# Script graph structure."""

from __future__ import annotations

import shutil

from pyghx.generate import generate_csharp_addition_document
from pyghx.inspect import inspect_document
from pyghx.script_edit import read_script_source_text, set_script_source_text
from pyghx.script_graph_edit import (
    add_csharp_number_input,
    list_script_input_variable_names,
    remove_csharp_input,
    rename_csharp_input,
)
from pyghx.validate import validate_document
from tests.helpers import CSHARP_ADDITION_FIXTURE_PATH


def test_add_csharp_number_input_updates_inspect_contract(tmp_path) -> None:
    output_path = tmp_path / "three_input_addition.ghx"
    shutil.copy(CSHARP_ADDITION_FIXTURE_PATH, output_path)

    add_csharp_number_input(
        output_path,
        contextual_nickname="Z",
        variable_name="z",
    )

    summary = inspect_document(output_path)
    contextual_nicknames = {
        contextual_input["nickname"] for contextual_input in summary["contextual_inputs"]
    }
    script_inputs = summary["script_components"][0]["inputs"]
    script_input_names = {script_input["name"] for script_input in script_inputs}

    assert contextual_nicknames == {"X", "Y", "Z"}
    assert script_input_names == {"x", "y", "z"}
    assert list_script_input_variable_names(output_path) == ["x", "y", "z"]
    assert "RunScript(object x, object y, object z, ref object a)" in read_script_source_text(
        output_path
    )

    validation_result = validate_document(output_path)
    assert validation_result.valid is True


def test_remove_csharp_input_restores_two_input_contract(tmp_path) -> None:
    output_path = tmp_path / "removed_input_addition.ghx"
    shutil.copy(CSHARP_ADDITION_FIXTURE_PATH, output_path)
    add_csharp_number_input(output_path, contextual_nickname="Z", variable_name="z")

    remove_csharp_input(output_path, variable_name="z")

    summary = inspect_document(output_path)
    contextual_nicknames = {
        contextual_input["nickname"] for contextual_input in summary["contextual_inputs"]
    }
    script_input_names = {
        script_input["name"] for script_input in summary["script_components"][0]["inputs"]
    }

    assert contextual_nicknames == {"X", "Y"}
    assert script_input_names == {"x", "y"}
    assert validate_document(output_path).valid is True


def test_rename_csharp_input_updates_compute_contract(tmp_path) -> None:
    output_path = tmp_path / "renamed_input_addition.ghx"
    shutil.copy(CSHARP_ADDITION_FIXTURE_PATH, output_path)

    rename_csharp_input(
        output_path,
        contextual_nickname="X",
        new_contextual_nickname="Length",
        new_variable_name="length",
    )

    summary = inspect_document(output_path)
    contextual_nicknames = {
        contextual_input["nickname"] for contextual_input in summary["contextual_inputs"]
    }
    script_input_names = {
        script_input["name"] for script_input in summary["script_components"][0]["inputs"]
    }

    assert contextual_nicknames == {"Length", "Y"}
    assert script_input_names == {"length", "y"}
    assert "RunScript(object length, object y, ref object a)" in read_script_source_text(
        output_path
    )
    assert validate_document(output_path).valid is True


def test_generated_csharp_addition_accepts_added_input(tmp_path) -> None:
    output_path = tmp_path / "generated_three_input_addition.ghx"
    generate_csharp_addition_document(output_path)
    add_csharp_number_input(output_path, contextual_nickname="Z", variable_name="z")

    updated_source_text = read_script_source_text(output_path).replace(
        "firstNumber + secondNumber",
        "firstNumber + secondNumber + Convert.ToDouble(z)",
    )
    set_script_source_text(output_path, updated_source_text)

    validation_result = validate_document(output_path)
    assert validation_result.valid is True
