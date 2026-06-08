"""Generate minimal GHX documents."""

from __future__ import annotations

from pathlib import Path

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
