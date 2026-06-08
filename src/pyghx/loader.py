"""Load Grasshopper GHX XML documents while preserving unknown structure."""

from __future__ import annotations

import xml.etree.ElementTree as element_tree
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class GhxItem:
    """One GHX archive item."""

    name: str
    type_name: str
    type_code: str
    text: str | None
    children: tuple["GhxItem", ...] = ()


@dataclass(frozen=True)
class GhxChunk:
    """One GHX archive chunk."""

    name: str
    index: str | None
    items: tuple[GhxItem, ...]
    chunks: tuple["GhxChunk", ...]


@dataclass(frozen=True)
class GhxArchive:
    """Parsed GHX archive root."""

    name: str
    items: tuple[GhxItem, ...]
    chunks: tuple[GhxChunk, ...]
    source_path: Path | None = None


@dataclass
class GhxDefinitionObject:
    """One Grasshopper definition object extracted from GHX."""

    index: int
    component_guid: str | None
    component_name: str | None
    instance_guid: str | None
    nickname: str | None
    optional: bool | None
    source_guids: tuple[str, ...] = field(default_factory=tuple)
    owned_instance_guids: tuple[str, ...] = field(default_factory=tuple)


@dataclass
class GhxDocument:
    """Facade over a loaded GHX archive."""

    archive: GhxArchive
    document_name: str | None
    object_count: int
    objects: tuple[GhxDefinitionObject, ...]
    unknown_component_names: tuple[str, ...]


class GhxLoadError(Exception):
    """Raised when GHX XML cannot be parsed."""


def load_ghx_document(source_path: Path | str) -> GhxDocument:
    """Load a GHX file from disk."""
    path = Path(source_path)
    xml_text = path.read_text(encoding="utf-8-sig")
    return parse_ghx_text(xml_text, source_path=path)


def parse_ghx_text(xml_text: str, source_path: Path | None = None) -> GhxDocument:
    """Parse GHX XML text into a document model."""
    try:
        root_element = element_tree.fromstring(xml_text)
    except element_tree.ParseError as parse_error:
        raise GhxLoadError(str(parse_error)) from parse_error

    archive = _parse_archive_element(root_element, source_path=source_path)
    document_name = _find_document_name(archive)
    objects = _extract_definition_objects(archive)
    unknown_component_names = tuple(
        sorted(
            {
                definition_object.component_name
                for definition_object in objects
                if definition_object.component_name
                and definition_object.component_name not in _known_component_names()
            }
        )
    )
    return GhxDocument(
        archive=archive,
        document_name=document_name,
        object_count=len(objects),
        objects=tuple(objects),
        unknown_component_names=unknown_component_names,
    )


def _known_component_names() -> set[str]:
    from pyghx.constants import KNOWN_COMPONENT_NAMES

    return KNOWN_COMPONENT_NAMES


def _parse_archive_element(
    element: element_tree.Element,
    source_path: Path | None,
) -> GhxArchive:
    if element.tag != "Archive":
        raise GhxLoadError("Root element must be Archive.")

    return GhxArchive(
        name=element.get("name", ""),
        items=_parse_items(element.find("items")),
        chunks=_parse_chunks(element.find("chunks")),
        source_path=source_path,
    )


def _parse_items(items_element: element_tree.Element | None) -> tuple[GhxItem, ...]:
    if items_element is None:
        return ()

    parsed_items: list[GhxItem] = []
    for item_element in items_element.findall("item"):
        parsed_items.append(_parse_item_element(item_element))
    return tuple(parsed_items)


def _parse_item_element(item_element: element_tree.Element) -> GhxItem:
    child_items = tuple(
        _parse_item_element(child_element)
        for child_element in item_element.findall("item")
    )
    direct_text = item_element.text.strip() if item_element.text else None
    return GhxItem(
        name=item_element.get("name", ""),
        type_name=item_element.get("type_name", ""),
        type_code=item_element.get("type_code", ""),
        text=direct_text,
        children=child_items,
    )


def _parse_chunks(chunks_element: element_tree.Element | None) -> tuple[GhxChunk, ...]:
    if chunks_element is None:
        return ()

    parsed_chunks: list[GhxChunk] = []
    for chunk_element in chunks_element.findall("chunk"):
        parsed_chunks.append(
            GhxChunk(
                name=chunk_element.get("name", ""),
                index=chunk_element.get("index"),
                items=_parse_items(chunk_element.find("items")),
                chunks=_parse_chunks(chunk_element.find("chunks")),
            )
        )
    return tuple(parsed_chunks)


def _find_document_name(archive: GhxArchive) -> str | None:
    definition_properties = _find_chunk_recursive(archive.chunks, "DefinitionProperties")
    if definition_properties is None:
        return None

    for item in definition_properties.items:
        if item.name == "Name":
            return item.text
    return None


def _extract_definition_objects(archive: GhxArchive) -> list[GhxDefinitionObject]:
    definition_chunk = _find_chunk_by_name(archive.chunks, "Definition")
    if definition_chunk is None:
        return []

    definition_objects_chunk = _find_chunk_by_name(definition_chunk.chunks, "DefinitionObjects")
    if definition_objects_chunk is None:
        return []

    parsed_objects: list[GhxDefinitionObject] = []
    for object_index, object_chunk in enumerate(definition_objects_chunk.chunks):
        if object_chunk.name != "Object":
            continue
        parsed_objects.append(_parse_definition_object(object_chunk, object_index))
    return parsed_objects


def _parse_definition_object(object_chunk: GhxChunk, object_index: int) -> GhxDefinitionObject:
    component_guid = _find_item_text(object_chunk.items, "GUID")
    component_name = _find_item_text(object_chunk.items, "Name")
    container_chunk = _find_chunk_by_name(object_chunk.chunks, "Container")
    instance_guid = None
    nickname = None
    optional = None
    source_guids: list[str] = []

    owned_instance_guids: list[str] = []
    if container_chunk is not None:
        instance_guid = _find_item_text(container_chunk.items, "InstanceGuid")
        nickname = _find_item_text(container_chunk.items, "NickName")
        optional_text = _find_item_text(container_chunk.items, "Optional")
        if optional_text is not None:
            optional = optional_text.lower() == "true"
        source_guids.extend(_collect_source_guids(container_chunk))
        owned_instance_guids.extend(_collect_instance_guids(container_chunk))

    return GhxDefinitionObject(
        index=object_index,
        component_guid=component_guid,
        component_name=component_name,
        instance_guid=instance_guid,
        nickname=nickname,
        optional=optional,
        source_guids=tuple(source_guids),
        owned_instance_guids=tuple(owned_instance_guids),
    )


def build_instance_guid_owner_map(
    objects: tuple[GhxDefinitionObject, ...],
) -> dict[str, GhxDefinitionObject]:
    """Map every owned instance GUID to its parent definition object."""
    owner_map: dict[str, GhxDefinitionObject] = {}
    for definition_object in objects:
        if definition_object.instance_guid:
            owner_map[definition_object.instance_guid] = definition_object
        for owned_guid in definition_object.owned_instance_guids:
            owner_map[owned_guid] = definition_object
    return owner_map


def _collect_source_guids(container_chunk: GhxChunk) -> list[str]:
    source_guids: list[str] = []
    for item in container_chunk.items:
        if item.name == "Source":
            if item.text:
                source_guids.append(item.text)

    for nested_chunk in container_chunk.chunks:
        source_guids.extend(_collect_source_guids(nested_chunk))
    return source_guids


def _collect_instance_guids(container_chunk: GhxChunk) -> list[str]:
    instance_guids: list[str] = []
    for item in container_chunk.items:
        if item.name == "InstanceGuid" and item.text:
            instance_guids.append(item.text)

    for nested_chunk in container_chunk.chunks:
        instance_guids.extend(_collect_instance_guids(nested_chunk))
    return instance_guids


def _find_chunk_recursive(chunks: tuple[GhxChunk, ...], chunk_name: str) -> GhxChunk | None:
    for chunk in chunks:
        if chunk.name == chunk_name:
            return chunk
        nested_match = _find_chunk_recursive(chunk.chunks, chunk_name)
        if nested_match is not None:
            return nested_match
    return None


def _find_chunk_by_name(chunks: tuple[GhxChunk, ...], chunk_name: str) -> GhxChunk | None:
    for chunk in chunks:
        if chunk.name == chunk_name:
            return chunk
    return None


def _find_item_text(items: tuple[GhxItem, ...], item_name: str) -> str | None:
    for item in items:
        if item.name == item_name:
            return item.text
    return None
