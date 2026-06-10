"""Generate GHX documents from templates and minimal definitions."""

from __future__ import annotations

import re
from importlib import resources
from pathlib import Path

ADDITION_COMPUTE_TEMPLATE_NAME = "addition_compute.ghx"
CSHARP_ADDITION_COMPUTE_TEMPLATE_NAME = "csharp_addition_compute.ghx"
DEFAULT_CSHARP_SCRIPT_TEMPLATE_NAME = "default_csharp_script.cs"
DEFAULT_ADDITION_DOCUMENT_NAME = "addition_compute.ghx"
DEFAULT_CSHARP_ADDITION_DOCUMENT_NAME = "csharp_addition_compute.ghx"
DEFINITION_NAME_PATTERN = re.compile(
    r'(<item name="Name" type_name="gh_string" type_code="10">)'
    r"[^<]*"
    r"(</item>)"
)

MINIMAL_GHX_TEMPLATE = """<?xml version="1.0" encoding="utf-8" standalone="yes"?>
<Archive name="Root">
  <items count="1">
    <item name="ArchiveVersion" type_name="gh_version" type_code="80">
      <Major>0</Major>
      <Minor>2</Minor>
      <Revision>2</Revision>
    </item>
  </items>
  <chunks count="1">
    <chunk name="Definition">
      <items count="1">
        <item name="plugin_version" type_name="gh_version" type_code="80">
          <Major>1</Major>
          <Minor>0</Minor>
          <Revision>8</Revision>
        </item>
      </items>
      <chunks count="3">
        <chunk name="DocumentHeader">
          <items count="1">
            <item name="DocumentID" type_name="gh_guid" type_code="9">00000000-0000-0000-0000-000000000001</item>
          </items>
        </chunk>
        <chunk name="DefinitionProperties">
          <items count="1">
            <item name="Name" type_name="gh_string" type_code="10">minimal.ghx</item>
          </items>
        </chunk>
        <chunk name="DefinitionObjects">
          <items count="1">
            <item name="ObjectCount" type_name="gh_int32" type_code="3">0</item>
          </items>
        </chunk>
      </chunks>
    </chunk>
  </chunks>
</Archive>
"""


def generate_minimal_document(output_path: Path | str) -> Path:
    """Write a minimal empty GHX document to disk."""
    path = Path(output_path)
    path.write_text(MINIMAL_GHX_TEMPLATE, encoding="utf-8")
    return path


def generate_addition_document(
    output_path: Path | str,
    document_name: str | None = None,
) -> Path:
    """Write a RhinoCompute-ready addition GHX document to disk."""
    path = Path(output_path)
    resolved_document_name = _resolve_document_name(
        path,
        document_name,
        default_document_name=DEFAULT_ADDITION_DOCUMENT_NAME,
    )
    template_text = _load_template_text(ADDITION_COMPUTE_TEMPLATE_NAME)
    generated_text = _replace_definition_name(template_text, resolved_document_name)
    path.write_text(generated_text, encoding="utf-8")
    return path


def load_default_csharp_script_source() -> str:
    """Return the default Grasshopper C# Script source template text."""
    return _load_template_text(DEFAULT_CSHARP_SCRIPT_TEMPLATE_NAME)


def write_default_csharp_script_source(output_path: Path | str) -> Path:
    """Write the default Grasshopper C# Script source template to disk."""
    path = Path(output_path)
    path.write_text(load_default_csharp_script_source(), encoding="utf-8")
    return path


def generate_csharp_addition_document(
    output_path: Path | str,
    document_name: str | None = None,
) -> Path:
    """Write a RhinoCompute-ready C# Script addition GHX document to disk."""
    path = Path(output_path)
    resolved_document_name = _resolve_document_name(
        path,
        document_name,
        default_document_name=DEFAULT_CSHARP_ADDITION_DOCUMENT_NAME,
    )
    template_text = _load_template_text(CSHARP_ADDITION_COMPUTE_TEMPLATE_NAME)
    generated_text = _replace_definition_name(template_text, resolved_document_name)
    path.write_text(generated_text, encoding="utf-8")
    return path


def _resolve_document_name(
    output_path: Path,
    document_name: str | None,
    default_document_name: str,
) -> str:
    if document_name is not None:
        return document_name

    if output_path.suffix.lower() == ".ghx":
        return output_path.name

    return default_document_name


def _load_template_text(template_name: str) -> str:
    template_path = resources.files("pyghx.templates") / template_name
    return template_path.read_text(encoding="utf-8")


def _replace_definition_name(template_text: str, document_name: str) -> str:
    replacement = rf"\g<1>{document_name}\g<2>"
    updated_text, replacement_count = DEFINITION_NAME_PATTERN.subn(
        replacement,
        template_text,
        count=1,
    )
    if replacement_count != 1:
        raise RuntimeError("Could not update DefinitionProperties Name in addition template.")

    return updated_text
