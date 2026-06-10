"""Unit tests for C# Script RunScript signature parsing and synchronization."""

from __future__ import annotations

from pyghx.script_source import (
    parse_run_script_signature,
    synchronize_run_script_input_variables,
)


def test_parse_run_script_signature_extracts_inputs_and_outputs() -> None:
    source_text = "private void RunScript(object x, object y, ref object a) { a = 1; }"
    input_names, output_names = parse_run_script_signature(source_text)
    assert input_names == ("x", "y")
    assert output_names == ("a",)


def test_synchronize_run_script_input_variables_updates_signature() -> None:
    source_text = (
        "private void RunScript(object x, object y, ref object a)\n"
        "{\n"
        "    a = x;\n"
        "}\n"
    )
    updated_source_text = synchronize_run_script_input_variables(
        source_text,
        ["x", "y", "z"],
    )
    assert "RunScript(object x, object y, object z, ref object a)" in updated_source_text
    assert "a = x;" in updated_source_text
