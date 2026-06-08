"""Detect reusable subgraph patterns in reference GHX documents."""

from __future__ import annotations

from dataclasses import dataclass

from pyghx.constants import CONTEXTUAL_INPUT_COMPONENT_NAMES
from pyghx.loader import GhxDefinitionObject, GhxDocument, build_instance_guid_owner_map

LOGGER_MANAGER_COMPONENT_NAME = "LoggerManager"
GROUP_COMPONENT_NAME = "Group"
MAX_GROUP_MEMBER_COUNT = 12
MAX_PATTERN_OBJECT_COUNT = 20
EMBEDDED_GEOMETRY_COMPONENT_NAMES = frozenset({"Brep"})
NUMBER_COMPONENT_NAME = "Number"


@dataclass(frozen=True)
class PatternCandidate:
    """One detected subgraph pattern before GHX extraction."""

    pattern_id: str
    title: str
    member_instance_guids: frozenset[str]
    geometry_embedded: bool = False


def detect_patterns(
    document: GhxDocument,
    exclude_embedded_geometry: bool = True,
) -> list[PatternCandidate]:
    """Detect extractable patterns in a loaded GHX document."""
    guid_owner_map = build_instance_guid_owner_map(document.objects)
    detected_patterns: list[PatternCandidate] = []
    seen_pattern_ids: set[str] = set()

    pattern_detectors = (
        _detect_addition_binary,
        _detect_context_bake_number_output,
        _detect_contextual_input_bake_patterns,
        _detect_get_number_to_number_chains,
        _detect_vector_xyz_from_get_numbers,
        _detect_group_subgraphs,
    )
    for pattern_detector in pattern_detectors:
        for pattern_candidate in pattern_detector(document, guid_owner_map):
            if pattern_candidate.pattern_id in seen_pattern_ids:
                continue
            finalized_pattern = finalize_pattern_candidate(
                pattern_candidate,
                guid_owner_map,
                exclude_embedded_geometry=exclude_embedded_geometry,
            )
            if finalized_pattern is None:
                continue
            seen_pattern_ids.add(finalized_pattern.pattern_id)
            detected_patterns.append(finalized_pattern)

    return detected_patterns


def expand_instance_guid_closure(
    seed_instance_guids: set[str],
    objects: tuple[GhxDefinitionObject, ...],
    include_upstream: bool = True,
    include_downstream: bool = True,
) -> set[str]:
    """Expand seed instance GUIDs along Source wiring."""
    guid_owner_map = build_instance_guid_owner_map(objects)
    selected_instance_guids = set(seed_instance_guids)
    active_connection_guids = _expand_active_connection_guids(
        selected_instance_guids,
        guid_owner_map,
    )

    if include_upstream:
        pending_guids = list(selected_instance_guids)
        while pending_guids:
            current_guid = pending_guids.pop()
            owner_object = guid_owner_map.get(current_guid)
            if owner_object is None:
                continue
            for source_guid in owner_object.source_guids:
                source_owner = guid_owner_map.get(source_guid)
                if source_owner is None:
                    continue
                if source_owner.instance_guid is None:
                    continue
                if source_owner.instance_guid in selected_instance_guids:
                    continue
                selected_instance_guids.add(source_owner.instance_guid)
                active_connection_guids.update(
                    _expand_active_connection_guids(
                        {source_owner.instance_guid},
                        guid_owner_map,
                    )
                )
                pending_guids.append(source_owner.instance_guid)

    if include_downstream:
        changed = True
        while changed:
            changed = False
            for definition_object in objects:
                if definition_object.instance_guid is None:
                    continue
                if definition_object.instance_guid in selected_instance_guids:
                    continue
                if not definition_object.source_guids:
                    continue
                if any(
                    source_guid in active_connection_guids
                    for source_guid in definition_object.source_guids
                ):
                    selected_instance_guids.add(definition_object.instance_guid)
                    active_connection_guids.update(
                        _expand_active_connection_guids(
                            {definition_object.instance_guid},
                            guid_owner_map,
                        )
                    )
                    changed = True

    return selected_instance_guids


def _expand_active_connection_guids(
    instance_guids: set[str],
    guid_owner_map: dict[str, GhxDefinitionObject],
) -> set[str]:
    """Include owned parameter GUIDs so downstream Context Bake wiring is followed."""
    active_connection_guids: set[str] = set(instance_guids)
    for instance_guid in instance_guids:
        owner_object = guid_owner_map.get(instance_guid)
        if owner_object is None:
            continue
        active_connection_guids.update(owner_object.owned_instance_guids)
    return active_connection_guids


def filter_operational_objects(
    member_instance_guids: set[str],
    guid_owner_map: dict[str, GhxDefinitionObject],
) -> set[str]:
    """Remove organizational components that should not ship in a pattern."""
    filtered_guids: set[str] = set()
    for instance_guid in member_instance_guids:
        owner_object = guid_owner_map.get(instance_guid)
        if owner_object is None:
            continue
        if owner_object.component_name in {
            LOGGER_MANAGER_COMPONENT_NAME,
            GROUP_COMPONENT_NAME,
        }:
            continue
        filtered_guids.add(instance_guid)
    return filtered_guids


def pattern_contains_embedded_geometry(
    member_instance_guids: set[str],
    guid_owner_map: dict[str, GhxDefinitionObject],
) -> bool:
    """Return True when a pattern includes geometry-embedding components."""
    for instance_guid in member_instance_guids:
        owner_object = guid_owner_map.get(instance_guid)
        if owner_object is None:
            continue
        if owner_object.component_name in EMBEDDED_GEOMETRY_COMPONENT_NAMES:
            return True
    return False


def remove_embedded_geometry_members(
    member_instance_guids: set[str],
    guid_owner_map: dict[str, GhxDefinitionObject],
) -> set[str]:
    """Drop geometry-embedding objects from a pattern member set."""
    filtered_member_guids: set[str] = set()
    for instance_guid in member_instance_guids:
        owner_object = guid_owner_map.get(instance_guid)
        if owner_object is None:
            continue
        if owner_object.component_name in EMBEDDED_GEOMETRY_COMPONENT_NAMES:
            continue
        filtered_member_guids.add(instance_guid)
    return filtered_member_guids


def finalize_pattern_candidate(
    pattern_candidate: PatternCandidate,
    guid_owner_map: dict[str, GhxDefinitionObject],
    exclude_embedded_geometry: bool,
) -> PatternCandidate | None:
    """Apply operational filtering, optional geometry scrubbing, and size limits."""
    member_instance_guids = set(pattern_candidate.member_instance_guids)
    geometry_was_embedded = pattern_candidate.geometry_embedded

    member_instance_guids = filter_operational_objects(member_instance_guids, guid_owner_map)
    if exclude_embedded_geometry:
        member_instance_guids = remove_embedded_geometry_members(
            member_instance_guids,
            guid_owner_map,
        )

    if not member_instance_guids:
        return None
    if len(member_instance_guids) > MAX_PATTERN_OBJECT_COUNT:
        return None

    return PatternCandidate(
        pattern_id=pattern_candidate.pattern_id,
        title=pattern_candidate.title,
        member_instance_guids=frozenset(member_instance_guids),
        geometry_embedded=geometry_was_embedded,
    )


def _detect_addition_binary(
    document: GhxDocument,
    guid_owner_map: dict[str, GhxDefinitionObject],
) -> list[PatternCandidate]:
    addition_objects = [
        definition_object
        for definition_object in document.objects
        if definition_object.component_name == "Addition"
        and definition_object.instance_guid is not None
    ]
    if not addition_objects:
        return []

    seed_guid = addition_objects[0].instance_guid
    if seed_guid is None:
        return []

    member_instance_guids = expand_instance_guid_closure(
        {seed_guid},
        document.objects,
        include_upstream=True,
        include_downstream=True,
    )
    member_instance_guids = filter_operational_objects(member_instance_guids, guid_owner_map)
    if not member_instance_guids:
        return []

    return [
        PatternCandidate(
            pattern_id="addition_binary",
            title="Addition with Get Number inputs and Context Bake output",
            member_instance_guids=frozenset(member_instance_guids),
            geometry_embedded=pattern_contains_embedded_geometry(
                member_instance_guids,
                guid_owner_map,
            ),
        )
    ]


def _detect_context_bake_number_output(
    document: GhxDocument,
    guid_owner_map: dict[str, GhxDefinitionObject],
) -> list[PatternCandidate]:
    for context_bake_object in document.objects:
        if context_bake_object.component_name != "Context Bake":
            continue
        if context_bake_object.instance_guid is None:
            continue

        member_instance_guids = expand_instance_guid_closure(
            {context_bake_object.instance_guid},
            document.objects,
            include_upstream=True,
            include_downstream=False,
        )
        member_instance_guids = filter_operational_objects(member_instance_guids, guid_owner_map)
        contextual_nicknames = _collect_contextual_input_nicknames(
            member_instance_guids,
            guid_owner_map,
        )
        if not contextual_nicknames:
            continue

        number_input_count = sum(
            1
            for instance_guid in member_instance_guids
            if (owner := guid_owner_map.get(instance_guid))
            and owner.component_name == "Get Number"
        )
        if number_input_count == 0:
            continue

        return [
            PatternCandidate(
                pattern_id="context_bake_number_output",
                title="Get Number to Context Bake output chain",
                member_instance_guids=frozenset(member_instance_guids),
                geometry_embedded=pattern_contains_embedded_geometry(
                    member_instance_guids,
                    guid_owner_map,
                ),
            )
        ]
    return []


def _detect_contextual_input_bake_patterns(
    document: GhxDocument,
    guid_owner_map: dict[str, GhxDefinitionObject],
) -> list[PatternCandidate]:
    detected_patterns: list[PatternCandidate] = []
    for contextual_object in document.objects:
        if contextual_object.component_name not in CONTEXTUAL_INPUT_COMPONENT_NAMES:
            continue
        if contextual_object.instance_guid is None:
            continue
        if not contextual_object.nickname:
            continue

        input_kind = CONTEXTUAL_INPUT_COMPONENT_NAMES[contextual_object.component_name]
        for context_bake_object in document.objects:
            if context_bake_object.component_name != "Context Bake":
                continue
            if context_bake_object.instance_guid is None:
                continue

            upstream_closure = expand_instance_guid_closure(
                {context_bake_object.instance_guid},
                document.objects,
                include_upstream=True,
                include_downstream=False,
            )
            if contextual_object.instance_guid not in upstream_closure:
                continue

            member_instance_guids = set(upstream_closure)
            member_instance_guids.add(context_bake_object.instance_guid)
            member_instance_guids = filter_operational_objects(
                member_instance_guids,
                guid_owner_map,
            )
            pattern_id = f"contextual_input_bake_{input_kind}"
            if pattern_id in {pattern.pattern_id for pattern in detected_patterns}:
                continue

            detected_patterns.append(
                PatternCandidate(
                    pattern_id=pattern_id,
                    title=(
                        f"{contextual_object.component_name} "
                        f"({contextual_object.nickname}) to Context Bake"
                    ),
                    member_instance_guids=frozenset(member_instance_guids),
                    geometry_embedded=pattern_contains_embedded_geometry(
                        member_instance_guids,
                        guid_owner_map,
                    ),
                )
            )
    return detected_patterns


def _detect_get_number_to_number_chains(
    document: GhxDocument,
    guid_owner_map: dict[str, GhxDefinitionObject],
) -> list[PatternCandidate]:
    detected_patterns: list[PatternCandidate] = []
    for contextual_object in document.objects:
        if contextual_object.component_name not in CONTEXTUAL_INPUT_COMPONENT_NAMES:
            continue
        if contextual_object.instance_guid is None:
            continue
        if not contextual_object.nickname:
            continue

        active_connection_guids = _expand_active_connection_guids(
            {contextual_object.instance_guid},
            guid_owner_map,
        )
        downstream_number_guids: set[str] = set()
        for definition_object in document.objects:
            if definition_object.component_name != NUMBER_COMPONENT_NAME:
                continue
            if definition_object.instance_guid is None:
                continue
            if not any(
                source_guid in active_connection_guids
                for source_guid in definition_object.source_guids
            ):
                continue
            downstream_number_guids.add(definition_object.instance_guid)

        if not downstream_number_guids:
            continue

        member_instance_guids = {contextual_object.instance_guid}
        member_instance_guids.update(downstream_number_guids)
        pattern_id = f"get_number_to_number_{contextual_object.nickname}"
        detected_patterns.append(
            PatternCandidate(
                pattern_id=pattern_id,
                title=(
                    f"Get Number ({contextual_object.nickname}) "
                    "to Number conversion chain"
                ),
                member_instance_guids=frozenset(member_instance_guids),
                geometry_embedded=pattern_contains_embedded_geometry(
                    member_instance_guids,
                    guid_owner_map,
                ),
            )
        )
    return detected_patterns


def _detect_vector_xyz_from_get_numbers(
    document: GhxDocument,
    guid_owner_map: dict[str, GhxDefinitionObject],
) -> list[PatternCandidate]:
    detected_patterns: list[PatternCandidate] = []
    for vector_object in document.objects:
        if vector_object.component_name != "Vector XYZ":
            continue
        if vector_object.instance_guid is None:
            continue

        member_instance_guids = expand_instance_guid_closure(
            {vector_object.instance_guid},
            document.objects,
            include_upstream=True,
            include_downstream=False,
        )
        member_instance_guids = filter_operational_objects(member_instance_guids, guid_owner_map)
        contextual_nicknames = _collect_contextual_input_nicknames(
            member_instance_guids,
            guid_owner_map,
        )
        if len(contextual_nicknames) < 3:
            continue

        nickname_suffix = "_".join(sorted(contextual_nicknames))
        pattern_id = f"vector_xyz_{nickname_suffix}"
        detected_patterns.append(
            PatternCandidate(
                pattern_id=pattern_id,
                title=f"Vector XYZ from Get Number inputs [{', '.join(sorted(contextual_nicknames))}]",
                member_instance_guids=frozenset(member_instance_guids),
                geometry_embedded=pattern_contains_embedded_geometry(
                    member_instance_guids,
                    guid_owner_map,
                ),
            )
        )
    return detected_patterns


def _detect_group_subgraphs(
    document: GhxDocument,
    guid_owner_map: dict[str, GhxDefinitionObject],
) -> list[PatternCandidate]:
    detected_patterns: list[PatternCandidate] = []
    for group_object in document.objects:
        if group_object.component_name != GROUP_COMPONENT_NAME:
            continue
        if group_object.instance_guid is None:
            continue

        group_member_count = len(group_object.owned_instance_guids)
        if group_member_count == 0:
            continue
        if group_member_count > MAX_GROUP_MEMBER_COUNT:
            continue

        member_instance_guids = set(group_object.owned_instance_guids)
        member_instance_guids = filter_operational_objects(member_instance_guids, guid_owner_map)
        if not member_instance_guids:
            continue

        pattern_id = f"group_subgraph_{group_object.index}"
        detected_patterns.append(
            PatternCandidate(
                pattern_id=pattern_id,
                title=f"Group subgraph with {len(member_instance_guids)} objects",
                member_instance_guids=frozenset(member_instance_guids),
                geometry_embedded=pattern_contains_embedded_geometry(
                    member_instance_guids,
                    guid_owner_map,
                ),
            )
        )
    return detected_patterns


def _collect_contextual_input_nicknames(
    member_instance_guids: set[str],
    guid_owner_map: dict[str, GhxDefinitionObject],
) -> list[str]:
    nicknames: list[str] = []
    for instance_guid in member_instance_guids:
        owner_object = guid_owner_map.get(instance_guid)
        if owner_object is None:
            continue
        if owner_object.component_name not in CONTEXTUAL_INPUT_COMPONENT_NAMES:
            continue
        if owner_object.nickname:
            nicknames.append(owner_object.nickname)
    return sorted(set(nicknames))
