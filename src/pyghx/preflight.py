"""Shared preflight diagnostics for validate and compute entry points."""

from __future__ import annotations

from pathlib import Path

from pyghx.ghx_integrity import build_ghx_integrity_diagnostics
from pyghx.script_validate import build_script_validation_diagnostics

PREFLIGHT_BLOCKING_DIAGNOSTIC_LEVEL = "error"


def build_preflight_diagnostics(source_path: Path | str) -> list[dict[str, str]]:
    """Return structural and script diagnostics used before RhinoCompute execution."""
    path = Path(source_path)
    diagnostics: list[dict[str, str]] = []
    diagnostics.extend(build_ghx_integrity_diagnostics(path))
    diagnostics.extend(build_script_validation_diagnostics(str(path)))
    return diagnostics


def has_blocking_preflight_errors(diagnostics: list[dict[str, str]]) -> bool:
    """Return True when any preflight diagnostic is an error-level blocker."""
    return any(
        diagnostic["level"] == PREFLIGHT_BLOCKING_DIAGNOSTIC_LEVEL
        for diagnostic in diagnostics
    )


def blocking_preflight_diagnostics(diagnostics: list[dict[str, str]]) -> list[dict[str, str]]:
    """Return only error-level preflight diagnostics."""
    return [
        diagnostic
        for diagnostic in diagnostics
        if diagnostic["level"] == PREFLIGHT_BLOCKING_DIAGNOSTIC_LEVEL
    ]
