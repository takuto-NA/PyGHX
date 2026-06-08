"""Contract tests for inspect summaries."""

from __future__ import annotations

from pyghx.inspect import build_summary, inspect_document
from pyghx.loader import load_ghx_document
from tests.helpers import ADDITION_FIXTURE_PATH, UNKNOWN_STRUCTURE_FIXTURE_PATH, VARIATION_FIXTURE_PATH

EXPECTED_COMPACT_TOP_LEVEL_KEYS = {
    "schema_version",
    "source_path",
    "summary_text",
    "document_metadata",
    "object_count",
    "compute_contract",
    "connections",
    "contextual_inputs",
    "context_bake_outputs",
    "unknown_elements",
    "diagnostics",
}


def test_inspect_summary_contract_keys() -> None:
    summary = inspect_document(ADDITION_FIXTURE_PATH)
    assert set(summary.keys()) == EXPECTED_COMPACT_TOP_LEVEL_KEYS
    assert summary["schema_version"] == "2"
    assert "objects" not in summary


def test_inspect_full_summary_includes_objects() -> None:
    summary = inspect_document(ADDITION_FIXTURE_PATH, include_objects=True)
    assert "objects" in summary
    assert len(summary["objects"]) == summary["object_count"]


def test_addition_summary_text_and_compute_contract() -> None:
    summary = inspect_document(ADDITION_FIXTURE_PATH)
    assert "X" in summary["summary_text"]
    assert "Y" in summary["summary_text"]
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
    assert summary["compute_contract"]["outputs"][0]["compute_param_name"] == "Content"
    assert summary["compute_contract"]["outputs"][0]["source_component_name"] == "Addition"


def test_addition_contextual_inputs() -> None:
    summary = inspect_document(ADDITION_FIXTURE_PATH)
    nicknames = {entry["nickname"] for entry in summary["contextual_inputs"]}
    kinds = {entry["kind"] for entry in summary["contextual_inputs"]}
    assert nicknames == {"X", "Y"}
    assert kinds == {"number"}
    assert all(entry["supported_for_compute"] for entry in summary["contextual_inputs"])


def test_addition_context_bake_connection() -> None:
    summary = inspect_document(ADDITION_FIXTURE_PATH)
    assert len(summary["context_bake_outputs"]) == 1
    context_bake_output = summary["context_bake_outputs"][0]
    assert context_bake_output["label"] == "addition"
    assert context_bake_output["source_component_name"] == "Addition"
    assert context_bake_output["compute_param_name"] == "Content"


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
    supported_inputs = [
        entry for entry in summary["contextual_inputs"] if entry["supported_for_compute"]
    ]
    assert {entry["nickname"] for entry in supported_inputs} == {
        "X",
        "Y",
        "Get Point",
        "Get String",
        "Get File Path",
    }


def test_variation_multiple_context_bake_outputs_have_unique_labels() -> None:
    summary = inspect_document(VARIATION_FIXTURE_PATH)
    assert len(summary["context_bake_outputs"]) == 6
    labels = [output["label"] for output in summary["context_bake_outputs"]]
    assert len(labels) == len(set(labels))
    assert labels == [
        "addition",
        "get_line",
        "get_boolean",
        "get_point",
        "get_string",
        "get_file_path",
    ]


def test_unknown_structure_reports_unknown_elements() -> None:
    summary = inspect_document(UNKNOWN_STRUCTURE_FIXTURE_PATH)
    assert summary["unknown_elements"]
    assert summary["unknown_elements"][0]["component_name"] == "Mystery Widget"


def test_build_summary_include_objects_flag() -> None:
    document = load_ghx_document(ADDITION_FIXTURE_PATH)
    compact_summary = build_summary(document, include_objects=False)
    full_summary = build_summary(document, include_objects=True)
    assert "objects" not in compact_summary
    assert "objects" in full_summary
