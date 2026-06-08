"""Tests for validation behavior."""

from __future__ import annotations

from pyghx.validate import validate_document
from tests.helpers import (
    ADDITION_FIXTURE_PATH,
    MALFORMED_FIXTURE_PATH,
    UNKNOWN_STRUCTURE_FIXTURE_PATH,
    VARIATION_FIXTURE_PATH,
)


def test_validate_addition_fixture() -> None:
    validation_result = validate_document(ADDITION_FIXTURE_PATH)
    assert validation_result.valid is True


def test_validate_variation_fixture() -> None:
    validation_result = validate_document(VARIATION_FIXTURE_PATH)
    assert validation_result.valid is True


def test_validate_malformed_fixture() -> None:
    validation_result = validate_document(MALFORMED_FIXTURE_PATH)
    assert validation_result.valid is False
    assert any(diagnostic["code"] == "xml_parse_error" for diagnostic in validation_result.diagnostics)


def test_validate_unknown_structure_fixture() -> None:
    validation_result = validate_document(UNKNOWN_STRUCTURE_FIXTURE_PATH)
    assert validation_result.valid is True
    assert any(diagnostic["code"] == "unknown_component" for diagnostic in validation_result.diagnostics)
