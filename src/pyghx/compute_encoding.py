"""Encode RhinoCompute Grasshopper parameter values."""

from __future__ import annotations

import json
from typing import Any

POINT_COORDINATE_COUNT = 3


def encode_number_parameter_for_grasshopper(number_value: int | float) -> str:
    """Encode a numeric contextual input for RhinoCompute."""
    return str(number_value)


def encode_text_parameter_for_grasshopper(text_value: str) -> str:
    """
    Encode a text contextual input for RhinoCompute.

    Windows paths must be JSON-quoted or Compute Regex.Unescape fails on sequences
    such as \\U in \\Users.
    """
    return json.dumps(text_value)


def encode_point3d_parameter_for_grasshopper(
    x_coordinate: float,
    y_coordinate: float,
    z_coordinate: float,
) -> str:
    """Encode a Point3d contextual input as a Grasshopper JSON string."""
    return json.dumps(
        {
            "X": x_coordinate,
            "Y": y_coordinate,
            "Z": z_coordinate,
        }
    )


def parse_point3d_coordinates(raw_coordinates: str) -> tuple[float, float, float]:
    """Parse X,Y,Z coordinates from a comma-separated CLI value."""
    coordinate_parts = [part.strip() for part in raw_coordinates.split(",")]
    if len(coordinate_parts) != POINT_COORDINATE_COUNT:
        raise ValueError(
            f"Point coordinates must contain {POINT_COORDINATE_COUNT} values, "
            f"got {len(coordinate_parts)}: {raw_coordinates!r}."
        )

    parsed_coordinates = tuple(float(part) for part in coordinate_parts)
    return (
        parsed_coordinates[0],
        parsed_coordinates[1],
        parsed_coordinates[2],
    )


def build_inner_tree_data_entries(kind: str, value: Any) -> list[dict[str, str]]:
    """Build InnerTree branch entries for one contextual input value."""
    if kind == "number":
        return [{"data": encode_number_parameter_for_grasshopper(value)}]

    if kind == "point":
        point_coordinates_list = _normalize_point_coordinates_list(value)
        return [
            {
                "data": encode_point3d_parameter_for_grasshopper(
                    x_coordinate=point_coordinates[0],
                    y_coordinate=point_coordinates[1],
                    z_coordinate=point_coordinates[2],
                )
            }
            for point_coordinates in point_coordinates_list
        ]

    if kind in {"string", "file_path"}:
        return [{"data": encode_text_parameter_for_grasshopper(str(value))}]

    raise ValueError(f"Unsupported RhinoCompute input kind for encoding: {kind!r}.")


def _normalize_point_coordinates_list(
    value: Any,
) -> list[tuple[float, float, float]]:
    if isinstance(value, tuple):
        if len(value) != POINT_COORDINATE_COUNT:
            raise ValueError(f"Point tuple must have {POINT_COORDINATE_COUNT} coordinates.")
        return [(float(value[0]), float(value[1]), float(value[2]))]

    if isinstance(value, list):
        normalized_points: list[tuple[float, float, float]] = []
        for point_entry in value:
            normalized_points.extend(_normalize_point_coordinates_list(point_entry))
        return normalized_points

    raise ValueError(f"Unsupported point value type: {type(value)!r}.")
