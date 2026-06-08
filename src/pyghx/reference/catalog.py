"""Pattern catalog schema and persistence for reference GHX extraction."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CATALOG_SCHEMA_VERSION = "1"
CATALOG_FILENAME = "catalog.json"
PRIVACY_FORBIDDEN_SUBSTRINGS = (
    "\\Users\\",
    "/Users/",
    "Downloads",
    "ダイキン",
    "資料系",
)


@dataclass(frozen=True)
class PatternCatalogEntry:
    """One extractable pattern stored in a catalog."""

    pattern_id: str
    title: str
    pattern_ghx: str
    object_count: int
    valid: bool
    rhino_compute_ready: bool
    geometry_embedded: bool
    compute_contract: dict[str, Any]
    boundary_inputs: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class PatternCatalog:
    """Catalog of patterns extracted from one reference GHX."""

    schema_version: str
    source_basename: str
    patterns: tuple[PatternCatalogEntry, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_basename": self.source_basename,
            "patterns": [
                {
                    "pattern_id": pattern.pattern_id,
                    "title": pattern.title,
                    "pattern_ghx": pattern.pattern_ghx,
                    "object_count": pattern.object_count,
                    "valid": pattern.valid,
                    "rhino_compute_ready": pattern.rhino_compute_ready,
                    "geometry_embedded": pattern.geometry_embedded,
                    "compute_contract": pattern.compute_contract,
                    "boundary_inputs": pattern.boundary_inputs,
                }
                for pattern in self.patterns
            ],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PatternCatalog:
        if payload.get("schema_version") != CATALOG_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported catalog schema version: {payload.get('schema_version')!r}."
            )
        if "source_basename" not in payload:
            raise ValueError("Catalog is missing source_basename.")

        patterns = tuple(
            PatternCatalogEntry(
                pattern_id=entry["pattern_id"],
                title=entry["title"],
                pattern_ghx=entry["pattern_ghx"],
                object_count=entry["object_count"],
                valid=entry["valid"],
                rhino_compute_ready=entry["rhino_compute_ready"],
                geometry_embedded=entry["geometry_embedded"],
                compute_contract=entry.get("compute_contract", {"inputs": [], "outputs": []}),
                boundary_inputs=list(entry.get("boundary_inputs", [])),
            )
            for entry in payload.get("patterns", [])
        )
        return cls(
            schema_version=CATALOG_SCHEMA_VERSION,
            source_basename=payload["source_basename"],
            patterns=patterns,
        )


def load_pattern_catalog(catalog_path: Path | str) -> PatternCatalog:
    """Load a pattern catalog from disk."""
    path = Path(catalog_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    catalog = PatternCatalog.from_dict(payload)
    validate_catalog_privacy(catalog.to_dict())
    return catalog


def save_pattern_catalog(catalog: PatternCatalog, catalog_path: Path | str) -> Path:
    """Write a pattern catalog to disk."""
    path = Path(catalog_path)
    payload = catalog.to_dict()
    validate_catalog_privacy(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def resolve_catalog_path(catalog_directory: Path | str) -> Path:
    """Resolve catalog.json inside a patterns output directory."""
    directory = Path(catalog_directory)
    if directory.is_file():
        return directory
    return directory / CATALOG_FILENAME


def find_pattern_entry(catalog: PatternCatalog, pattern_id: str) -> PatternCatalogEntry:
    """Look up one pattern entry by id."""
    for pattern in catalog.patterns:
        if pattern.pattern_id == pattern_id:
            return pattern
    raise KeyError(f"Pattern not found: {pattern_id}")


def validate_catalog_privacy(catalog_payload: dict[str, Any]) -> None:
    """Ensure catalog JSON does not embed absolute local paths."""
    serialized = json.dumps(catalog_payload, ensure_ascii=False)
    for forbidden_substring in PRIVACY_FORBIDDEN_SUBSTRINGS:
        if forbidden_substring in serialized:
            raise ValueError(
                f"Catalog must not contain forbidden path fragment: {forbidden_substring!r}."
            )

    for pattern in catalog_payload.get("patterns", []):
        pattern_ghx = pattern.get("pattern_ghx", "")
        if Path(pattern_ghx).is_absolute():
            raise ValueError(f"pattern_ghx must be relative, got {pattern_ghx!r}.")

    if "source_path" in catalog_payload:
        raise ValueError("Catalog must use source_basename only, not source_path.")
