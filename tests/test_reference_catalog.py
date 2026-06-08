"""Contract tests for reference pattern catalogs."""

from __future__ import annotations

import pytest

from pyghx.reference.catalog import (
    CATALOG_SCHEMA_VERSION,
    PatternCatalog,
    PatternCatalogEntry,
    validate_catalog_privacy,
)


def test_catalog_schema_round_trip() -> None:
    catalog = PatternCatalog(
        schema_version=CATALOG_SCHEMA_VERSION,
        source_basename="addition.ghx",
        patterns=(
            PatternCatalogEntry(
                pattern_id="addition_binary",
                title="Addition pattern",
                pattern_ghx="addition_binary.ghx",
                object_count=4,
                valid=True,
                rhino_compute_ready=True,
                geometry_embedded=False,
                compute_contract={"inputs": [], "outputs": []},
            ),
        ),
    )
    restored_catalog = PatternCatalog.from_dict(catalog.to_dict())
    assert restored_catalog.source_basename == "addition.ghx"
    assert restored_catalog.patterns[0].pattern_id == "addition_binary"


def test_catalog_contains_no_absolute_paths() -> None:
    catalog_payload = {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "source_basename": "addition.ghx",
        "patterns": [
            {
                "pattern_id": "addition_binary",
                "title": "Addition pattern",
                "pattern_ghx": "addition_binary.ghx",
                "object_count": 4,
                "valid": True,
                "rhino_compute_ready": True,
                "geometry_embedded": False,
                "compute_contract": {"inputs": [], "outputs": []},
                "boundary_inputs": [],
            }
        ],
    }
    validate_catalog_privacy(catalog_payload)


def test_catalog_rejects_forbidden_path_fragments() -> None:
    catalog_payload = {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "source_basename": "cab_be_assembled2.ghx",
        "patterns": [],
        "note": "C:\\Users\\owner\\Downloads\\資料系\\ダイキン",
    }
    with pytest.raises(ValueError):
        validate_catalog_privacy(catalog_payload)


def test_catalog_rejects_source_path_field() -> None:
    catalog_payload = {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "source_basename": "addition.ghx",
        "source_path": "C:\\secret\\addition.ghx",
        "patterns": [],
    }
    with pytest.raises(ValueError):
        validate_catalog_privacy(catalog_payload)
