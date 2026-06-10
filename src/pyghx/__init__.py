"""PyGHX: inspect, validate, and evaluate Grasshopper GHX files."""

from pyghx.compute import evaluate_document
from pyghx.generate import (
    generate_addition_document,
    generate_csharp_addition_document,
    generate_minimal_document,
)
from pyghx.script_edit import (
    read_script_source_text,
    remove_context_bake_by_instance_guid,
    rename_contextual_input_nickname,
    repair_duplicate_contextual_input_nicknames,
    set_script_source_text,
)
from pyghx.script_graph_edit import (
    add_csharp_number_input,
    list_script_input_variable_names,
    remove_csharp_input,
    rename_csharp_input,
)
from pyghx.inspect import inspect_document
from pyghx.reference import extract_patterns, generate_from_pattern, load_pattern_catalog
from pyghx.validate import validate_document

__all__ = [
    "evaluate_document",
    "extract_patterns",
    "generate_addition_document",
    "generate_csharp_addition_document",
    "generate_from_pattern",
    "generate_minimal_document",
    "add_csharp_number_input",
    "inspect_document",
    "list_script_input_variable_names",
    "load_pattern_catalog",
    "read_script_source_text",
    "remove_csharp_input",
    "remove_context_bake_by_instance_guid",
    "rename_csharp_input",
    "rename_contextual_input_nickname",
    "repair_duplicate_contextual_input_nicknames",
    "set_script_source_text",
    "validate_document",
]
