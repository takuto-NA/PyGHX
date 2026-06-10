"""Unit tests for C# Script GHX editing."""

from __future__ import annotations

import shutil

from pyghx.inspect import inspect_document
from pyghx.script_component import extract_script_components
from pyghx.script_edit import (
    read_script_source_text,
    rename_contextual_input_nickname,
    set_script_source_text,
)
from pyghx.loader import load_ghx_document
from tests.helpers import CSHARP_ADDITION_FIXTURE_PATH


def test_set_script_source_round_trip_preserves_structure(tmp_path) -> None:
    output_path = tmp_path / "edited_csharp_addition.ghx"
    shutil.copy(CSHARP_ADDITION_FIXTURE_PATH, output_path)

    replacement_source_text = read_script_source_text(output_path).replace(
        "firstNumber + secondNumber",
        "firstNumber * secondNumber",
    )
    set_script_source_text(output_path, replacement_source_text)

    reloaded_source_text = read_script_source_text(output_path)
    assert "firstNumber * secondNumber" in reloaded_source_text

    original_document = load_ghx_document(CSHARP_ADDITION_FIXTURE_PATH)
    edited_document = load_ghx_document(output_path)
    assert edited_document.object_count == original_document.object_count
    assert len(extract_script_components(edited_document)) == 1

    edited_summary = inspect_document(output_path)
    assert edited_summary["compute_contract"]["inputs"] == inspect_document(
        CSHARP_ADDITION_FIXTURE_PATH
    )["compute_contract"]["inputs"]


def test_rename_contextual_input_nickname_updates_inspect_contract(tmp_path) -> None:
    output_path = tmp_path / "renamed_inputs.ghx"
    shutil.copy(CSHARP_ADDITION_FIXTURE_PATH, output_path)

    rename_contextual_input_nickname(
        output_path,
        instance_guid="6ff49b4e-be51-4113-a28d-f99ca930859d",
        nickname="Left",
    )

    summary = inspect_document(output_path)
    input_nicknames = {
        contextual_input["nickname"] for contextual_input in summary["contextual_inputs"]
    }
    assert "Left" in input_nicknames
    assert "X" not in input_nicknames
