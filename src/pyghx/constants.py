"""Shared constants for PyGHX."""

from pathlib import Path

SCHEMA_VERSION = "1"
DEFAULT_RHINO_COMPUTE_URL = "http://localhost:5000/"

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
}

SUPPORTED_RHINO_COMPUTE_INPUT_KINDS = {"number"}
