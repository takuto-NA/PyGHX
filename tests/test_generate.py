"""Tests for minimal GHX generation."""

from __future__ import annotations

from pathlib import Path

from pyghx.generate import generate_minimal_document
from pyghx.inspect import inspect_document
from pyghx.loader import load_ghx_document


def test_generate_minimal_document(tmp_path: Path) -> None:
    output_path = generate_minimal_document(tmp_path / "minimal.ghx")
    document = load_ghx_document(output_path)
    assert document.object_count == 0

    summary = inspect_document(output_path)
    assert summary["object_count"] == 0
    assert summary["document_metadata"]["document_name"] == "minimal.ghx"
