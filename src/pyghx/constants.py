"""Shared constants for PyGHX."""

from pathlib import Path

SCHEMA_VERSION = "2"
DEFAULT_RHINO_COMPUTE_URL = "http://localhost:5000/"
RHINO_COMPUTE_CONTEXT_BAKE_PARAM_NAME = "Content"

CONTEXTUAL_INPUT_COMPONENT_NAMES = {
    "Get Number": "number",
    "Get Line": "line",
    "Get Boolean": "boolean",
    "Get Point": "point",
    "Get String": "string",
    "Get File Path": "file_path",
}

CONTEXT_BAKE_COMPONENT_NAME = "Context Bake"

KNOWN_COMPONENT_NAMES = set(CONTEXTUAL_INPUT_COMPONENT_NAMES) | {
    CONTEXT_BAKE_COMPONENT_NAME,
    "Addition",
    "LoggerManager",
    "Area",
    "Brep",
    "C# Script",
    "Colour Swatch",
    "Custom Preview",
    "Deconstruct Brep",
    "Group",
    "List Item",
    "Mass Addition",
    "Merge",
    "Null Item",
    "Number",
    "Number Slider",
    "Panel",
    "Radians",
    "Relay",
    "Rotate",
    "Solid Intersection",
    "Square",
    "Stream Filter",
    "Vector XYZ",
    "Volume",
    "YZ Plane",
}

SUPPORTED_RHINO_COMPUTE_INPUT_KINDS = frozenset(
    {
        "number",
        "point",
        "string",
        "file_path",
    }
)
