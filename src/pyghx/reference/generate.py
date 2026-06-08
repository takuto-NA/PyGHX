"""Generate GHX documents from extracted reference patterns."""

from __future__ import annotations

import re
from pathlib import Path

from pyghx.reference.catalog import (
    find_pattern_entry,
    load_pattern_catalog,
    resolve_catalog_path,
)

DEFINITION_NAME_PATTERN = re.compile(
    r'(<item name="Name" type_name="gh_string" type_code="10">)'
    r"[^<]*"
    r"(</item>)"
)


def generate_from_pattern(
    pattern_id: str,
    catalog_directory: Path | str,
    output_path: Path | str,
    document_name: str | None = None,
) -> Path:
    """Copy one catalog pattern GHX to the requested output path."""
    catalog_path = resolve_catalog_path(catalog_directory)
    catalog = load_pattern_catalog(catalog_path)
    pattern_entry = find_pattern_entry(catalog, pattern_id)

    catalog_root_directory = catalog_path.parent
    pattern_source_path = catalog_root_directory / pattern_entry.pattern_ghx
    if not pattern_source_path.is_file():
        raise FileNotFoundError(f"Pattern GHX not found: {pattern_source_path}")

    resolved_document_name = _resolve_document_name(Path(output_path), document_name, pattern_entry.pattern_ghx)
    template_text = pattern_source_path.read_text(encoding="utf-8")
    generated_text = _replace_definition_name(template_text, resolved_document_name)

    output_file_path = Path(output_path)
    output_file_path.parent.mkdir(parents=True, exist_ok=True)
    output_file_path.write_text(generated_text, encoding="utf-8")
    return output_file_path


def _resolve_document_name(
    output_path: Path,
    document_name: str | None,
    pattern_ghx_name: str,
) -> str:
    if document_name is not None:
        return document_name

    if output_path.suffix.lower() == ".ghx":
        return output_path.name

    return pattern_ghx_name


def _replace_definition_name(template_text: str, document_name: str) -> str:
    replacement = rf"\g<1>{document_name}\g<2>"
    updated_text, replacement_count = DEFINITION_NAME_PATTERN.subn(
        replacement,
        template_text,
        count=1,
    )
    if replacement_count != 1:
        raise RuntimeError("Could not update DefinitionProperties Name in pattern GHX.")

    return updated_text
