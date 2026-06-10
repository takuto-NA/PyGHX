"""Inspect contract tests for C# Script GHX files."""

from __future__ import annotations

from pyghx.inspect import inspect_document
from tests.helpers import CSHARP_ADDITION_FIXTURE_PATH


def test_csharp_addition_inspect_includes_script_components() -> None:
    summary = inspect_document(CSHARP_ADDITION_FIXTURE_PATH)
    assert len(summary["script_components"]) == 1

    script_component = summary["script_components"][0]
    assert script_component["nickname"] == "C# Script"
    assert script_component["language_taxon"] == "*.*.csharp"
    assert "RunScript(object x, object y, ref object a)" in script_component["source_text"]
    assert script_component["context_bake_reachable_output_nicknames"] == ["a"]


def test_csharp_addition_compute_contract() -> None:
    summary = inspect_document(CSHARP_ADDITION_FIXTURE_PATH)
    input_nicknames = {
        contextual_input["nickname"] for contextual_input in summary["contextual_inputs"]
    }
    assert input_nicknames == {"X", "Y"}
    assert summary["compute_contract"]["outputs"][0]["source_component_name"] == "C# Script"
    assert summary["compute_contract"]["outputs"][0]["label"] == "c_script"
