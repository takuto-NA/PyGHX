"""Unit tests for C# Script component parsing and encoding."""

from __future__ import annotations

from pyghx.script_component import (
    decode_script_source_text,
    encode_script_source_text,
    extract_script_components,
)
from pyghx.loader import load_ghx_document
from tests.helpers import CSHARP_ADDITION_FIXTURE_PATH


def test_script_source_round_trip_encoding() -> None:
    source_text = "private void RunScript(object x, object y, ref object a) { a = 5; }"
    encoded_source_text = encode_script_source_text(source_text)
    assert decode_script_source_text(encoded_source_text) == source_text


def test_csharp_addition_fixture_extracts_script_component() -> None:
    document = load_ghx_document(CSHARP_ADDITION_FIXTURE_PATH)
    script_summaries = extract_script_components(document)
    assert len(script_summaries) == 1

    script_summary = script_summaries[0]
    assert script_summary.nickname == "C# Script"
    assert script_summary.language_taxon == "*.*.csharp"
    assert script_summary.decoded_source_text is not None
    assert "RunScript(object x, object y, ref object a)" in script_summary.decoded_source_text
    assert "firstNumber + secondNumber" in script_summary.decoded_source_text

    input_nicknames = {script_input.nickname for script_input in script_summary.inputs}
    output_nicknames = {script_output.nickname for script_output in script_summary.outputs}
    assert input_nicknames == {"x", "y"}
    assert output_nicknames == {"out", "a"}
    assert script_summary.context_bake_reachable_output_nicknames == ("a",)

    script_input_x = script_summary.inputs[0]
    assert script_input_x.source_count == 1
    assert script_input_x.chunk_index == 0
    assert script_input_x.source_instance_guids == ("6ff49b4e-be51-4113-a28d-f99ca930859d",)
