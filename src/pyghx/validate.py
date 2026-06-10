"""Validate GHX documents and report structured diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pyghx.ghx_integrity import build_ghx_integrity_diagnostics
from pyghx.inspect import inspect_document_safe
from pyghx.loader import GhxLoadError, load_ghx_document
from pyghx.script_validate import build_script_validation_diagnostics


@dataclass(frozen=True)
class ValidationResult:
    """Structured validation outcome."""

    valid: bool
    diagnostics: tuple[dict[str, str], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "diagnostics": list(self.diagnostics),
        }


def validate_document(source_path: Path | str) -> ValidationResult:
    """Validate a GHX file and return structured diagnostics."""
    path = Path(source_path)
    diagnostics: list[dict[str, str]] = []

    try:
        document = load_ghx_document(path)
    except GhxLoadError as load_error:
        diagnostics.append(
            {
                "level": "error",
                "code": "xml_parse_error",
                "message": str(load_error),
            }
        )
        return ValidationResult(valid=False, diagnostics=tuple(diagnostics))

    if document.archive.name != "Root":
        diagnostics.append(
            {
                "level": "error",
                "code": "unexpected_archive_name",
                "message": f"Expected archive name Root, found {document.archive.name!r}.",
            }
        )

    definition_chunk_names = {chunk.name for chunk in document.archive.chunks}
    if "Definition" not in definition_chunk_names:
        diagnostics.append(
            {
                "level": "error",
                "code": "missing_definition_chunk",
                "message": "Archive is missing a Definition chunk.",
            }
        )

    summary = inspect_document_safe(path)
    diagnostics.extend(summary.get("diagnostics", []))
    diagnostics.extend(build_ghx_integrity_diagnostics(path))
    diagnostics.extend(build_script_validation_diagnostics(path))

    for unknown_element in summary.get("unknown_elements", []):
        diagnostics.append(
            {
                "level": "info",
                "code": "unknown_component",
                "message": f"Unknown component: {unknown_element.get('component_name')}",
            }
        )

    has_error = any(diagnostic["level"] == "error" for diagnostic in diagnostics)
    return ValidationResult(valid=not has_error, diagnostics=tuple(diagnostics))
