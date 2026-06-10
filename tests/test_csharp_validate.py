"""Validation tests for C# Script GHX files."""

from __future__ import annotations

import shutil
import xml.etree.ElementTree as element_tree

from pyghx.script_edit import set_script_source_text
from pyghx.validate import validate_document
from tests.helpers import CSHARP_ADDITION_FIXTURE_PATH, CSHARP_ADDITION_RAW_FIXTURE_PATH


def test_csharp_addition_fixture_validates() -> None:
    validation_result = validate_document(CSHARP_ADDITION_FIXTURE_PATH)
    assert validation_result.valid is True
    assert not any(
        diagnostic["code"] == "duplicate_compute_input_param_name"
        for diagnostic in validation_result.diagnostics
    )


def test_raw_csharp_fixture_reports_duplicate_compute_param_names() -> None:
    validation_result = validate_document(CSHARP_ADDITION_RAW_FIXTURE_PATH)
    assert validation_result.valid is False
    diagnostic_codes = {diagnostic["code"] for diagnostic in validation_result.diagnostics}
    assert "duplicate_compute_input_param_name" in diagnostic_codes
    assert "duplicate_compute_output_param_name" in diagnostic_codes


def test_invalid_script_source_encoding_is_reported(tmp_path) -> None:
    output_path = tmp_path / "invalid_script_encoding.ghx"
    shutil.copy(CSHARP_ADDITION_FIXTURE_PATH, output_path)

    root_element = element_tree.parse(output_path).getroot()
    script_text_item = root_element.find(
        './/chunk[@name="Script"]/items/item[@name="Text"]'
    )
    assert script_text_item is not None
    script_text_item.text = "not-valid-base64!!!"
    element_tree.ElementTree(root_element).write(output_path, encoding="utf-8")

    validation_result = validate_document(output_path)
    assert validation_result.valid is False
    assert any(
        diagnostic["code"] == "invalid_script_source_encoding"
        for diagnostic in validation_result.diagnostics
    )


def test_empty_script_source_text_is_reported(tmp_path) -> None:
    output_path = tmp_path / "empty_script_source.ghx"
    shutil.copy(CSHARP_ADDITION_FIXTURE_PATH, output_path)
    set_script_source_text(output_path, "   ")

    validation_result = validate_document(output_path)
    assert validation_result.valid is False
    assert any(
        diagnostic["code"] == "empty_script_source_text"
        for diagnostic in validation_result.diagnostics
    )


def test_missing_run_script_signature_is_reported_as_warning(tmp_path) -> None:
    output_path = tmp_path / "missing_run_script_signature.ghx"
    shutil.copy(CSHARP_ADDITION_FIXTURE_PATH, output_path)
    set_script_source_text(output_path, "public class Script_Instance { }")

    validation_result = validate_document(output_path)
    assert any(
        diagnostic["code"] == "missing_run_script_signature"
        and diagnostic["level"] == "warning"
        for diagnostic in validation_result.diagnostics
    )
