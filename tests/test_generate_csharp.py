"""Tests for C# Script GHX generation."""

from __future__ import annotations

from pyghx.generate import (
    generate_csharp_addition_document,
    load_default_csharp_script_source,
    write_default_csharp_script_source,
)
from pyghx.inspect import inspect_document
from pyghx.validate import validate_document
from tests.helpers import CSHARP_ADDITION_FIXTURE_PATH


def test_generate_csharp_addition_matches_fixture_contract(tmp_path) -> None:
    output_path = tmp_path / "generated_csharp_addition.ghx"
    generate_csharp_addition_document(output_path)

    generated_summary = inspect_document(output_path)
    fixture_summary = inspect_document(CSHARP_ADDITION_FIXTURE_PATH)

    assert generated_summary["compute_contract"] == fixture_summary["compute_contract"]
    assert len(generated_summary["script_components"]) == 1
    validation_result = validate_document(output_path)
    assert validation_result.valid is True


def test_load_default_csharp_script_source_contains_run_script_signature() -> None:
    source_text = load_default_csharp_script_source()
    assert "RunScript(object x, object y, ref object a)" in source_text
    assert "a = null;" in source_text
    assert "GH_ScriptInstance" in source_text


def test_write_default_csharp_script_source_writes_template_file(tmp_path) -> None:
    output_path = tmp_path / "default_script.cs"
    write_default_csharp_script_source(output_path)
    written_source_text = output_path.read_text(encoding="utf-8")
    assert written_source_text == load_default_csharp_script_source()
