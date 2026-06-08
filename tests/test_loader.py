"""Unit tests for GHX loading."""

from __future__ import annotations

import pytest

from pyghx.loader import GhxLoadError, load_ghx_document
from tests.helpers import (
    ADDITION_FIXTURE_PATH,
    MALFORMED_FIXTURE_PATH,
    UNKNOWN_STRUCTURE_FIXTURE_PATH,
    VARIATION_FIXTURE_PATH,
)


def test_load_addition_fixture() -> None:
    document = load_ghx_document(ADDITION_FIXTURE_PATH)
    assert document.document_name == "addition.ghx"
    assert document.object_count == 5


def test_load_variation_fixture() -> None:
    document = load_ghx_document(VARIATION_FIXTURE_PATH)
    assert document.document_name == "variation.ghx"
    assert document.object_count == 15


def test_malformed_fixture_raises_load_error() -> None:
    with pytest.raises(GhxLoadError):
        load_ghx_document(MALFORMED_FIXTURE_PATH)


def test_unknown_structure_fixture_reports_unknown_component() -> None:
    document = load_ghx_document(UNKNOWN_STRUCTURE_FIXTURE_PATH)
    assert "Mystery Widget" in document.unknown_component_names
