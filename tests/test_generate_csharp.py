"""Tests for C# Script GHX generation."""

from __future__ import annotations

from pyghx.generate import generate_csharp_addition_document
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
