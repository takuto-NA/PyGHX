"""Contract tests for inspect summaries."""

from __future__ import annotations

from pyghx.inspect import inspect_document
from tests.helpers import ADDITION_FIXTURE_PATH, UNKNOWN_STRUCTURE_FIXTURE_PATH, VARIATION_FIXTURE_PATH

EXPECTED_TOP_LEVEL_KEYS = {
    "schema_version",
    "source_path",
    "document_metadata",
    "object_count",
    "objects",
    "connections",
    "contextual_inputs",
    "context_bake_outputs",
    "unknown_elements",
    "diagnostics",
}


def test_inspect_summary_contract_keys() -> None:
    summary = inspect_document(ADDITION_FIXTURE_PATH)
    assert set(summary.keys()) == EXPECTED_TOP_LEVEL_KEYS
    assert summary["schema_version"] == "1"


def test_addition_contextual_inputs() -> None:
    summary = inspect_document(ADDITION_FIXTURE_PATH)
    nicknames = {entry["nickname"] for entry in summary["contextual_inputs"]}
    kinds = {entry["kind"] for entry in summary["contextual_inputs"]}
    assert nicknames == {"X", "Y"}
    assert kinds == {"number"}


def test_addition_context_bake_connection() -> None:
    summary = inspect_document(ADDITION_FIXTURE_PATH)
    assert len(summary["context_bake_outputs"]) == 1
    context_bake_output = summary["context_bake_outputs"][0]
    assert "Addition" in context_bake_output["source_component_names"]


def test_variation_contextual_input_kinds() -> None:
    summary = inspect_document(VARIATION_FIXTURE_PATH)
    kinds = {entry["kind"] for entry in summary["contextual_inputs"]}
    assert kinds == {
        "number",
        "line",
        "boolean",
        "point",
        "string",
        "file_path",
    }


def test_variation_multiple_context_bake_outputs() -> None:
    summary = inspect_document(VARIATION_FIXTURE_PATH)
    assert len(summary["context_bake_outputs"]) == 6
    assert all(output["source_instance_guids"] for output in summary["context_bake_outputs"])


def test_unknown_structure_reports_unknown_elements() -> None:
    summary = inspect_document(UNKNOWN_STRUCTURE_FIXTURE_PATH)
    assert summary["unknown_elements"]
    assert summary["unknown_elements"][0]["component_name"] == "Mystery Widget"
