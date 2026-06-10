"""Validation tests for C# Script GHX files."""

from __future__ import annotations

import shutil
import xml.etree.ElementTree as element_tree

from pyghx.script_edit import read_script_source_text, set_script_source_text
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


def test_run_script_signature_mismatch_is_reported(tmp_path) -> None:
    output_path = tmp_path / "signature_mismatch.ghx"
    shutil.copy(CSHARP_ADDITION_FIXTURE_PATH, output_path)
    set_script_source_text(
        output_path,
        read_script_source_text(output_path).replace(
            "RunScript(object x, object y, ref object a)",
            "RunScript(object x, object y, object z, ref object a)",
        ),
    )

    validation_result = validate_document(output_path)
    assert validation_result.valid is False
    assert any(
        diagnostic["code"] == "run_script_signature_mismatch"
        for diagnostic in validation_result.diagnostics
    )


def test_script_input_missing_contextual_source_is_reported(tmp_path) -> None:
    output_path = tmp_path / "invalid_contextual_source.ghx"
    shutil.copy(CSHARP_ADDITION_FIXTURE_PATH, output_path)

    root_element = element_tree.parse(output_path).getroot()
    first_input_param_element = root_element.find('.//chunk[@name="InputParam"]')
    assert first_input_param_element is not None
    source_item = first_input_param_element.find('./items/item[@name="Source"]')
    assert source_item is not None
    csharp_script_instance_guid = "ab5f4b4a-e3b5-4249-8d53-0d1439cf904e"
    source_item.text = csharp_script_instance_guid
    element_tree.ElementTree(root_element).write(output_path, encoding="utf-8")

    validation_result = validate_document(output_path)
    assert validation_result.valid is False
    assert any(
        diagnostic["code"] == "script_input_missing_contextual_source"
        for diagnostic in validation_result.diagnostics
    )


def test_script_parameter_duplicate_name_is_reported(tmp_path) -> None:
    output_path = tmp_path / "duplicate_script_input_name.ghx"
    shutil.copy(CSHARP_ADDITION_FIXTURE_PATH, output_path)

    root_element = element_tree.parse(output_path).getroot()
    second_input_param_element = root_element.findall('.//chunk[@name="InputParam"]')[1]
    name_item = second_input_param_element.find('./items/item[@name="Name"]')
    nickname_item = second_input_param_element.find('./items/item[@name="NickName"]')
    assert name_item is not None
    assert nickname_item is not None
    name_item.text = "x"
    nickname_item.text = "x"
    element_tree.ElementTree(root_element).write(output_path, encoding="utf-8")

    validation_result = validate_document(output_path)
    assert validation_result.valid is False
    assert any(
        diagnostic["code"] == "script_parameter_duplicate_name"
        for diagnostic in validation_result.diagnostics
    )


def test_script_input_not_wired_is_reported(tmp_path) -> None:
    output_path = tmp_path / "unwired_input.ghx"
    shutil.copy(CSHARP_ADDITION_FIXTURE_PATH, output_path)

    root_element = element_tree.parse(output_path).getroot()
    first_input_param_element = root_element.find('.//chunk[@name="InputParam"]')
    assert first_input_param_element is not None
    input_items_element = first_input_param_element.find("items")
    assert input_items_element is not None
    for item_element in list(input_items_element.findall("item")):
        if item_element.get("name") == "Source":
            input_items_element.remove(item_element)
    source_count_item = input_items_element.find('./item[@name="SourceCount"]')
    assert source_count_item is not None
    source_count_item.text = "0"
    element_tree.ElementTree(root_element).write(output_path, encoding="utf-8")

    validation_result = validate_document(output_path)
    assert validation_result.valid is False
    assert any(
        diagnostic["code"] == "script_input_not_wired"
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
