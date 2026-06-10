"""Helpers for operational tests over KNOWN_COMPONENT_NAMES."""

from __future__ import annotations

import os
from pathlib import Path

from pyghx.constants import KNOWN_COMPONENT_NAMES
from pyghx.loader import GhxDefinitionObject, GhxDocument, load_ghx_document
from tests.helpers import (
    ADDITION_FIXTURE_PATH,
    BREP_POINTS_FIXTURE_PATH,
    CSHARP_ADDITION_FIXTURE_PATH,
    CSHARP_STEP_IMPORT_FIXTURE_PATH,
    CSHARP_STEP_SCALE_FIXTURE_PATH,
    IMPORT_MODEL_FIXTURE_PATH,
    IMPORT_TWO_MODELS_FIXTURE_PATH,
    VARIATION_FIXTURE_PATH,
)

PUBLIC_FIXTURE_PATHS = (
    ADDITION_FIXTURE_PATH,
    BREP_POINTS_FIXTURE_PATH,
    CSHARP_ADDITION_FIXTURE_PATH,
    CSHARP_STEP_IMPORT_FIXTURE_PATH,
    CSHARP_STEP_SCALE_FIXTURE_PATH,
    IMPORT_MODEL_FIXTURE_PATH,
    IMPORT_TWO_MODELS_FIXTURE_PATH,
    VARIATION_FIXTURE_PATH,
)


def reference_ghx_path() -> Path | None:
    """Return the optional private reference GHX path from the environment."""
    raw_path = os.environ.get("PYGHX_REFERENCE_GHX")
    if not raw_path:
        return None

    path = Path(raw_path)
    if not path.is_file():
        return None

    return path


def load_component_instances(
    fixture_path: Path,
    component_name: str,
) -> tuple[GhxDocument, tuple[GhxDefinitionObject, ...]]:
    """Load a fixture and return matching component instances."""
    document = load_ghx_document(fixture_path)
    instances = tuple(
        definition_object
        for definition_object in document.objects
        if definition_object.component_name == component_name
    )
    return document, instances


def find_fixture_path_for_component(component_name: str) -> Path | None:
    """Return the first public fixture path that contains the component."""
    for fixture_path in PUBLIC_FIXTURE_PATHS:
        _, instances = load_component_instances(fixture_path, component_name)
        if instances:
            return fixture_path
    return None


def public_known_component_names() -> frozenset[str]:
    """Return KNOWN component names that appear in public fixtures."""
    found_component_names: set[str] = set()
    for fixture_path in PUBLIC_FIXTURE_PATHS:
        document = load_ghx_document(fixture_path)
        for definition_object in document.objects:
            if definition_object.component_name in KNOWN_COMPONENT_NAMES:
                found_component_names.add(definition_object.component_name)
    return frozenset(found_component_names)


def reference_known_component_names() -> frozenset[str]:
    """Return KNOWN component names present in the private reference GHX."""
    reference_path = reference_ghx_path()
    if reference_path is None:
        return frozenset()

    document = load_ghx_document(reference_path)
    return frozenset(
        definition_object.component_name
        for definition_object in document.objects
        if definition_object.component_name in KNOWN_COMPONENT_NAMES
    )


def all_covered_known_component_names() -> frozenset[str]:
    """Return KNOWN component names covered by public and/or private fixtures."""
    return public_known_component_names() | reference_known_component_names()


def reference_only_known_component_names() -> frozenset[str]:
    """Return KNOWN component names that appear only in the private reference GHX."""
    return reference_known_component_names() - public_known_component_names()


def uncovered_known_component_names() -> frozenset[str]:
    """Return KNOWN component names missing from all available fixtures."""
    return KNOWN_COMPONENT_NAMES - all_covered_known_component_names()
