"""Create csharp_addition_compute.ghx from tests/fixtures/csharp_addition.ghx."""

from __future__ import annotations

import xml.etree.ElementTree as element_tree
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = REPOSITORY_ROOT / "tests" / "fixtures" / "csharp_addition.ghx"
OUTPUT_PATH = REPOSITORY_ROOT / "src" / "pyghx" / "templates" / "csharp_addition_compute.ghx"
CSHARP_ADDITION_COMPUTE_DOCUMENT_NAME = "csharp_addition_compute.ghx"


def create_csharp_addition_compute_template() -> Path:
    if not SOURCE_PATH.is_file():
        raise RuntimeError(
            "csharp_addition fixture was not found. Run scripts/create_csharp_fixtures.py first."
        )

    root_element = element_tree.parse(SOURCE_PATH).getroot()
    definition_element = _find_child_chunk(root_element, "Definition")
    if definition_element is None:
        raise RuntimeError("Definition chunk was not found in csharp_addition fixture.")

    _update_definition_name(definition_element, CSHARP_ADDITION_COMPUTE_DOCUMENT_NAME)
    _refresh_chunk_counts(root_element)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    element_tree.indent(root_element, space="  ")
    element_tree.ElementTree(root_element).write(
        OUTPUT_PATH,
        encoding="utf-8",
        xml_declaration=True,
    )
    return OUTPUT_PATH


def _find_child_chunk(parent_element: element_tree.Element, chunk_name: str) -> element_tree.Element | None:
    chunks_element = parent_element.find("chunks")
    if chunks_element is None:
        return None
    for child_element in chunks_element.findall("chunk"):
        if child_element.get("name") == chunk_name:
            return child_element
    return None


def _update_definition_name(definition_element: element_tree.Element, document_name: str) -> None:
    definition_properties_element = _find_child_chunk(definition_element, "DefinitionProperties")
    if definition_properties_element is None:
        raise RuntimeError("DefinitionProperties chunk was not found.")
    document_name_item = definition_properties_element.find('./items/item[@name="Name"]')
    if document_name_item is None:
        raise RuntimeError("DefinitionProperties Name item was not found.")
    document_name_item.text = document_name


def _refresh_chunk_counts(root_element: element_tree.Element) -> None:
    _set_chunks_count_attribute(root_element)


def _set_chunks_count_attribute(parent_element: element_tree.Element) -> None:
    chunks_element = parent_element.find("chunks")
    if chunks_element is None:
        return
    child_chunks = chunks_element.findall("chunk")
    chunks_element.set("count", str(len(child_chunks)))
    for child_chunk in child_chunks:
        _set_chunks_count_attribute(child_chunk)


if __name__ == "__main__":
    template_path = create_csharp_addition_compute_template()
    print(template_path)
