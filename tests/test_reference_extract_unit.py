"""Unit tests for reference pattern extraction helpers."""

from __future__ import annotations

import xml.etree.ElementTree as element_tree

from pyghx.loader import load_ghx_document
from pyghx.reference.extract import build_pattern_ghx
from pyghx.reference.patterns import detect_patterns, expand_instance_guid_closure
from tests.helpers import ADDITION_FIXTURE_PATH


def test_detect_addition_binary_pattern_from_addition_fixture() -> None:
    document = load_ghx_document(ADDITION_FIXTURE_PATH)
    pattern_candidates = detect_patterns(document, exclude_embedded_geometry=True)
    pattern_ids = {pattern.pattern_id for pattern in pattern_candidates}
    assert "addition_binary" in pattern_ids


def test_build_pattern_ghx_is_well_formed_xml(tmp_path) -> None:
    document = load_ghx_document(ADDITION_FIXTURE_PATH)
    pattern_candidates = detect_patterns(document, exclude_embedded_geometry=True)
    addition_pattern = next(
        pattern for pattern in pattern_candidates if pattern.pattern_id == "addition_binary"
    )

    output_path = build_pattern_ghx(
        source_file_path=ADDITION_FIXTURE_PATH,
        member_instance_guids=addition_pattern.member_instance_guids,
        output_path=tmp_path / "addition_binary.ghx",
        document_name="addition_binary.ghx",
    )

    element_tree.parse(output_path)
    generated_text = output_path.read_text(encoding="utf-8")
    assert "LoggerManager" not in generated_text


def test_expand_instance_guid_closure_includes_upstream_inputs() -> None:
    document = load_ghx_document(ADDITION_FIXTURE_PATH)
    addition_object = next(
        definition_object
        for definition_object in document.objects
        if definition_object.component_name == "Addition"
    )
    assert addition_object.instance_guid is not None

    closure = expand_instance_guid_closure(
        {addition_object.instance_guid},
        document.objects,
        include_upstream=True,
        include_downstream=True,
    )
    nicknames = {
        definition_object.nickname
        for definition_object in document.objects
        if definition_object.instance_guid in closure
    }
    assert "X" in nicknames
    assert "Y" in nicknames


def test_finalize_pattern_candidate_strips_brep_instead_of_skipping_pattern() -> None:
    document = load_ghx_document(ADDITION_FIXTURE_PATH)
    pattern_candidates = detect_patterns(document, exclude_embedded_geometry=True)
    assert pattern_candidates
    assert all(
        len(pattern_candidate.member_instance_guids) <= 20
        for pattern_candidate in pattern_candidates
    )


def test_detect_patterns_returns_unique_pattern_ids() -> None:
    document = load_ghx_document(ADDITION_FIXTURE_PATH)
    pattern_candidates = detect_patterns(document, exclude_embedded_geometry=True)
    pattern_ids = [pattern_candidate.pattern_id for pattern_candidate in pattern_candidates]
    assert len(pattern_ids) == len(set(pattern_ids))
