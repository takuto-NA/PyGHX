"""Command-line interface for PyGHX."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pyghx.compute import ComputeInputValue, evaluate_document, extract_numeric_result
from pyghx.compute_encoding import parse_point3d_coordinates
from pyghx.constants import DEFAULT_RHINO_COMPUTE_URL
from pyghx.generate import (
    generate_addition_document,
    generate_csharp_addition_document,
    generate_minimal_document,
    write_default_csharp_script_source,
)
from pyghx.script_edit import (
    read_script_source_text,
    remove_context_bake_by_instance_guid,
    rename_contextual_input_nickname,
    repair_duplicate_contextual_input_nicknames,
    set_script_source_text,
)
from pyghx.script_graph_edit import (
    ScriptGraphEditError,
    add_csharp_number_input,
    remove_csharp_input,
    rename_csharp_input,
)
from pyghx.inspect import inspect_document
from pyghx.reference import extract_patterns, generate_from_pattern, load_pattern_catalog
from pyghx.reference.catalog import find_pattern_entry
from pyghx.gradient_descent import (
    CONTEXTUAL_INPUT_NICKNAMES,
    DEFAULT_DESCENT_RECORD_PATH,
    DEFAULT_FINITE_DIFFERENCE_STEP,
    DEFAULT_FIXED_VARIABLE_VALUES,
    DEFAULT_GRADIENT_TOLERANCE,
    DEFAULT_INITIAL_INPUT_VALUES,
    DEFAULT_INITIAL_STEP_SIZE,
    DEFAULT_MAXIMUM_ITERATION_COUNT,
    DEFAULT_MAXIMUM_STEP_SIZE,
    DEFAULT_MINIMUM_STEP_SIZE,
    DEFAULT_PENALTY_TOLERANCE,
    DEFAULT_STEP_GROWTH_FACTOR,
    GradientDescentConfig,
    GradientDescentError,
    OriginalFiniteDifferenceEvaluator,
    RhinoComputePenaltyGradientEvaluator,
    run_projected_gradient_descent,
    write_descent_run_record,
)
from pyghx.gradient_transform import GradientTransformError, transform_penalty_graph_for_gradient
from pyghx.validate import validate_document


def _parse_key_value_pair(raw_pair: str) -> tuple[str, str]:
    if "=" not in raw_pair:
        raise argparse.ArgumentTypeError(f"Expected KEY=VALUE format, got {raw_pair!r}.")
    key, value = raw_pair.split("=", 1)
    if not key:
        raise argparse.ArgumentTypeError(f"Missing key in {raw_pair!r}.")
    return key, value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pyghx",
        description="Inspect, validate, compute, and generate Grasshopper GHX files.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="Inspect a GHX file.")
    inspect_parser.add_argument("ghx_path", type=Path)
    inspect_parser.add_argument("--json", action="store_true", help="Emit JSON summary.")
    inspect_parser.add_argument(
        "--full",
        action="store_true",
        help="Include full object inventory in JSON summary.",
    )

    validate_parser = subparsers.add_parser("validate", help="Validate a GHX file.")
    validate_parser.add_argument("ghx_path", type=Path)
    validate_parser.add_argument("--json", action="store_true", help="Emit JSON diagnostics.")

    compute_parser = subparsers.add_parser(
        "compute",
        help="Evaluate a GHX file through RhinoCompute.",
    )
    compute_parser.add_argument("ghx_path", type=Path)
    compute_parser.add_argument(
        "--number",
        action="append",
        default=[],
        type=_parse_key_value_pair,
        metavar="NICKNAME=VALUE",
        help="Numeric contextual input value.",
    )
    compute_parser.add_argument(
        "--point",
        action="append",
        default=[],
        type=_parse_key_value_pair,
        metavar="NICKNAME=X,Y,Z",
        help="Point contextual input value. Repeat for multiple points.",
    )
    compute_parser.add_argument(
        "--text",
        action="append",
        default=[],
        type=_parse_key_value_pair,
        metavar="NICKNAME=VALUE",
        help="Text or file-path contextual input value.",
    )
    compute_parser.add_argument(
        "--url",
        default=DEFAULT_RHINO_COMPUTE_URL,
        help="RhinoCompute base URL.",
    )
    compute_parser.add_argument("--json", action="store_true", help="Emit JSON result.")
    compute_parser.add_argument(
        "--profile",
        action="store_true",
        help="Include per-phase timing in the result.",
    )
    compute_parser.add_argument(
        "--profile-solve",
        action="store_true",
        help=(
            "With --profile, issue pointer follow-up requests to estimate "
            "Grasshopper solve vs definition transfer time."
        ),
    )

    generate_parser = subparsers.add_parser(
        "generate-minimal",
        help="Generate a minimal GHX document.",
    )
    generate_parser.add_argument("--output", type=Path, required=True)

    generate_addition_parser = subparsers.add_parser(
        "generate-addition",
        help="Generate a RhinoCompute-ready addition GHX document.",
    )
    generate_addition_parser.add_argument("--output", type=Path, required=True)
    generate_addition_parser.add_argument(
        "--document-name",
        help="Override the DefinitionProperties Name item.",
    )

    generate_csharp_addition_parser = subparsers.add_parser(
        "generate-csharp-addition",
        help="Generate a RhinoCompute-ready C# Script addition GHX document.",
    )
    generate_csharp_addition_parser.add_argument("--output", type=Path, required=True)
    generate_csharp_addition_parser.add_argument(
        "--document-name",
        help="Override the DefinitionProperties Name item.",
    )

    write_csharp_script_template_parser = subparsers.add_parser(
        "write-csharp-script-template",
        help="Write the default Grasshopper C# Script source template to disk.",
    )
    write_csharp_script_template_parser.add_argument("--output", type=Path, required=True)

    set_script_source_parser = subparsers.add_parser(
        "set-script-source",
        help="Replace C# Script source text in a GHX file.",
    )
    set_script_source_parser.add_argument("ghx_path", type=Path)
    set_script_source_parser.add_argument(
        "--source-file",
        type=Path,
        help="Path to a C# source file.",
    )
    set_script_source_parser.add_argument(
        "--source-text",
        help="Inline C# source text.",
    )
    set_script_source_parser.add_argument(
        "--instance-guid",
        help="Target one C# Script component when multiple are present.",
    )

    rename_contextual_input_parser = subparsers.add_parser(
        "rename-contextual-input",
        help="Rename one contextual Get Number input nickname.",
    )
    rename_contextual_input_parser.add_argument("ghx_path", type=Path)
    rename_contextual_input_parser.add_argument("instance_guid")
    rename_contextual_input_parser.add_argument("nickname")

    repair_contextual_inputs_parser = subparsers.add_parser(
        "repair-contextual-inputs",
        help="Assign unique contextual input nicknames by instance GUID.",
    )
    repair_contextual_inputs_parser.add_argument("ghx_path", type=Path)
    repair_contextual_inputs_parser.add_argument(
        "--nickname",
        action="append",
        default=[],
        type=_parse_key_value_pair,
        metavar="INSTANCE_GUID=NICKNAME",
        help="Contextual input nickname assignment.",
    )

    get_script_source_parser = subparsers.add_parser(
        "get-script-source",
        help="Print decoded C# Script source text from a GHX file.",
    )
    get_script_source_parser.add_argument("ghx_path", type=Path)
    get_script_source_parser.add_argument(
        "--instance-guid",
        help="Target one C# Script component when multiple are present.",
    )

    remove_context_bake_parser = subparsers.add_parser(
        "remove-context-bake",
        help="Remove one Context Bake component from a GHX file.",
    )
    remove_context_bake_parser.add_argument("ghx_path", type=Path)
    remove_context_bake_parser.add_argument("instance_guid")

    add_csharp_number_input_parser = subparsers.add_parser(
        "add-csharp-number-input",
        help="Add one Get Number input wired to a C# Script InputParam.",
    )
    add_csharp_number_input_parser.add_argument("ghx_path", type=Path)
    add_csharp_number_input_parser.add_argument(
        "--name",
        required=True,
        help="RhinoCompute contextual input nickname (for example Z).",
    )
    add_csharp_number_input_parser.add_argument(
        "--variable-name",
        required=True,
        help="C# Script input variable name (for example z).",
    )
    add_csharp_number_input_parser.add_argument(
        "--instance-guid",
        help="Target one C# Script component when multiple are present.",
    )

    remove_csharp_input_parser = subparsers.add_parser(
        "remove-csharp-input",
        help="Remove one C# Script input and its wired Get Number component.",
    )
    remove_csharp_input_parser.add_argument("ghx_path", type=Path)
    remove_csharp_input_parser.add_argument(
        "--variable-name",
        required=True,
        help="C# Script input variable name to remove.",
    )
    remove_csharp_input_parser.add_argument(
        "--instance-guid",
        help="Target one C# Script component when multiple are present.",
    )

    rename_csharp_input_parser = subparsers.add_parser(
        "rename-csharp-input",
        help="Rename one wired Get Number nickname and C# Script input variable.",
    )
    rename_csharp_input_parser.add_argument("ghx_path", type=Path)
    rename_csharp_input_parser.add_argument(
        "--name",
        required=True,
        help="Current contextual input nickname.",
    )
    rename_csharp_input_parser.add_argument(
        "--new-name",
        required=True,
        help="New contextual input nickname.",
    )
    rename_csharp_input_parser.add_argument(
        "--variable-name",
        required=True,
        help="New C# Script input variable name.",
    )
    rename_csharp_input_parser.add_argument(
        "--instance-guid",
        help="Target one C# Script component when multiple are present.",
    )

    extract_patterns_parser = subparsers.add_parser(
        "extract-patterns",
        help="Extract reusable patterns from a reference GHX file.",
    )
    extract_patterns_parser.add_argument("source_path", type=Path)
    extract_patterns_parser.add_argument("--output-dir", type=Path, required=True)
    extract_patterns_parser.add_argument(
        "--include-embedded-geometry",
        action="store_true",
        help=(
            "Keep Brep objects inside extracted pattern GHX. "
            "By default, Brep objects are removed from pattern members."
        ),
    )

    list_patterns_parser = subparsers.add_parser(
        "list-patterns",
        help="List patterns from a local catalog.",
    )
    list_patterns_parser.add_argument("--catalog", type=Path, required=True)
    list_patterns_parser.add_argument("--json", action="store_true")

    inspect_pattern_parser = subparsers.add_parser(
        "inspect-pattern",
        help="Inspect one catalog pattern.",
    )
    inspect_pattern_parser.add_argument("pattern_id")
    inspect_pattern_parser.add_argument("--catalog", type=Path, required=True)
    inspect_pattern_parser.add_argument("--json", action="store_true")

    generate_from_pattern_parser = subparsers.add_parser(
        "generate-from-pattern",
        help="Generate a GHX file from one catalog pattern.",
    )
    generate_from_pattern_parser.add_argument("pattern_id")
    generate_from_pattern_parser.add_argument("--catalog", type=Path, required=True)
    generate_from_pattern_parser.add_argument("--output", type=Path, required=True)
    generate_from_pattern_parser.add_argument(
        "--document-name",
        help="Override the DefinitionProperties Name item.",
    )

    add_gradient_outputs_parser = subparsers.add_parser(
        "add-gradient-outputs",
        help="Derive one GHX that returns penalty and Gradient in a single RhinoCompute solve.",
    )
    add_gradient_outputs_parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Source penalty GHX path.",
    )
    add_gradient_outputs_parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Derived gradient GHX output path.",
    )

    descend_gradient_parser = subparsers.add_parser(
        "descend-gradient",
        help=(
            "Run projected gradient descent on a gradient-enabled GHX to drive penalty toward zero."
        ),
    )
    descend_gradient_parser.add_argument("ghx_path", type=Path)
    descend_gradient_parser.add_argument(
        "--initial",
        action="append",
        default=[],
        type=_parse_key_value_pair,
        metavar="NICKNAME=VALUE",
        help="Override one initial contextual input value.",
    )
    descend_gradient_parser.add_argument(
        "--fixed",
        action="append",
        default=[],
        type=_parse_key_value_pair,
        metavar="NICKNAME=VALUE",
        help="Keep one contextual input fixed during optimization.",
    )
    descend_gradient_parser.add_argument(
        "--tolerance",
        type=float,
        default=DEFAULT_PENALTY_TOLERANCE,
        help="Target penalty value reported with the run. Gradient norm controls convergence.",
    )
    descend_gradient_parser.add_argument(
        "--gradient-tolerance",
        type=float,
        default=DEFAULT_GRADIENT_TOLERANCE,
        help="Stop when the projected Gradient norm is at or below this value.",
    )
    descend_gradient_parser.add_argument(
        "--max-iterations",
        type=int,
        default=DEFAULT_MAXIMUM_ITERATION_COUNT,
        help="Maximum number of accepted gradient descent iterations.",
    )
    descend_gradient_parser.add_argument(
        "--initial-step-size",
        type=float,
        default=DEFAULT_INITIAL_STEP_SIZE,
        help="Initial step size for Armijo backtracking line search.",
    )
    descend_gradient_parser.add_argument(
        "--maximum-step-size",
        type=float,
        default=DEFAULT_MAXIMUM_STEP_SIZE,
        help="Largest step size that line search may try.",
    )
    descend_gradient_parser.add_argument(
        "--minimum-step-size",
        type=float,
        default=DEFAULT_MINIMUM_STEP_SIZE,
        help="Stop line search when trial step falls below this value.",
    )
    descend_gradient_parser.add_argument(
        "--step-growth-factor",
        type=float,
        default=DEFAULT_STEP_GROWTH_FACTOR,
        help="Multiplier for the next trial step after an accepted step.",
    )
    descend_gradient_parser.add_argument(
        "--source-ghx",
        type=Path,
        help=(
            "Original scalar penalty GHX. When set, descent uses external finite "
            "difference on this file so penalty and gradient come from the same objective."
        ),
    )
    descend_gradient_parser.add_argument(
        "--finite-difference-step",
        type=float,
        default=DEFAULT_FINITE_DIFFERENCE_STEP,
        help="Forward-difference step used with --source-ghx.",
    )
    descend_gradient_parser.add_argument(
        "--url",
        default=DEFAULT_RHINO_COMPUTE_URL,
        help="RhinoCompute base URL.",
    )
    descend_gradient_parser.add_argument("--json", action="store_true", help="Emit JSON result.")
    descend_gradient_parser.add_argument(
        "--record-json",
        nargs="?",
        const=str(DEFAULT_DESCENT_RECORD_PATH),
        default=str(DEFAULT_DESCENT_RECORD_PATH),
        metavar="PATH",
        help=(
            "Write a run record with metrics and result to JSON. "
            f"Default: {DEFAULT_DESCENT_RECORD_PATH}"
        ),
    )
    descend_gradient_parser.add_argument(
        "--no-record",
        action="store_true",
        help="Do not write a JSON run record to disk.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = _build_parser()
    arguments = parser.parse_args(argv)

    if arguments.command == "inspect":
        return _run_inspect(arguments)
    if arguments.command == "validate":
        return _run_validate(arguments)
    if arguments.command == "compute":
        return _run_compute(arguments)
    if arguments.command == "generate-minimal":
        return _run_generate_minimal(arguments)
    if arguments.command == "generate-addition":
        return _run_generate_addition(arguments)
    if arguments.command == "generate-csharp-addition":
        return _run_generate_csharp_addition(arguments)
    if arguments.command == "write-csharp-script-template":
        return _run_write_csharp_script_template(arguments)
    if arguments.command == "set-script-source":
        return _run_set_script_source(arguments)
    if arguments.command == "rename-contextual-input":
        return _run_rename_contextual_input(arguments)
    if arguments.command == "repair-contextual-inputs":
        return _run_repair_contextual_inputs(arguments)
    if arguments.command == "get-script-source":
        return _run_get_script_source(arguments)
    if arguments.command == "remove-context-bake":
        return _run_remove_context_bake(arguments)
    if arguments.command == "add-csharp-number-input":
        return _run_add_csharp_number_input(arguments)
    if arguments.command == "remove-csharp-input":
        return _run_remove_csharp_input(arguments)
    if arguments.command == "rename-csharp-input":
        return _run_rename_csharp_input(arguments)
    if arguments.command == "extract-patterns":
        return _run_extract_patterns(arguments)
    if arguments.command == "list-patterns":
        return _run_list_patterns(arguments)
    if arguments.command == "inspect-pattern":
        return _run_inspect_pattern(arguments)
    if arguments.command == "generate-from-pattern":
        return _run_generate_from_pattern(arguments)
    if arguments.command == "add-gradient-outputs":
        return _run_add_gradient_outputs(arguments)
    if arguments.command == "descend-gradient":
        return _run_descend_gradient(arguments)

    parser.error(f"Unknown command: {arguments.command}")
    return 2


def _run_inspect(arguments: argparse.Namespace) -> int:
    summary = inspect_document(arguments.ghx_path, include_objects=arguments.full)
    if arguments.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0

    print(summary["summary_text"])
    print(f"Objects: {summary['object_count']}")
    print(f"Compute inputs: {len(summary['compute_contract']['inputs'])}")
    print(f"Compute outputs: {len(summary['compute_contract']['outputs'])}")
    return 0


def _run_validate(arguments: argparse.Namespace) -> int:
    validation_result = validate_document(arguments.ghx_path)
    if arguments.json:
        print(json.dumps(validation_result.to_dict(), indent=2, ensure_ascii=False))
    else:
        for diagnostic in validation_result.diagnostics:
            print(f"[{diagnostic['level']}] {diagnostic['code']}: {diagnostic['message']}")

    return 0 if validation_result.valid else 1


def _run_compute(arguments: argparse.Namespace) -> int:
    input_values = _build_compute_input_values(arguments)
    compute_result = evaluate_document(
        arguments.ghx_path,
        input_values=input_values,
        compute_url=arguments.url,
        collect_timing=arguments.profile,
        estimate_grasshopper_solve=arguments.profile_solve,
    )
    payload = compute_result.to_dict()
    payload["numeric_summary"] = extract_numeric_result(compute_result.outputs)

    if arguments.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(payload, indent=2, ensure_ascii=False))

    return 0 if compute_result.success else 1


def _run_generate_minimal(arguments: argparse.Namespace) -> int:
    output_path = generate_minimal_document(arguments.output)
    print(str(output_path))
    return 0


def _run_generate_addition(arguments: argparse.Namespace) -> int:
    output_path = generate_addition_document(
        arguments.output,
        document_name=arguments.document_name,
    )
    print(str(output_path))
    return 0


def _run_generate_csharp_addition(arguments: argparse.Namespace) -> int:
    output_path = generate_csharp_addition_document(
        arguments.output,
        document_name=arguments.document_name,
    )
    print(str(output_path))
    return 0


def _run_write_csharp_script_template(arguments: argparse.Namespace) -> int:
    output_path = write_default_csharp_script_source(arguments.output)
    print(str(output_path))
    return 0


def _run_set_script_source(arguments: argparse.Namespace) -> int:
    source_text = _resolve_script_source_text(arguments)
    output_path = set_script_source_text(
        arguments.ghx_path,
        source_text=source_text,
        instance_guid=arguments.instance_guid,
    )
    print(str(output_path))
    return 0


def _run_rename_contextual_input(arguments: argparse.Namespace) -> int:
    output_path = rename_contextual_input_nickname(
        arguments.ghx_path,
        instance_guid=arguments.instance_guid,
        nickname=arguments.nickname,
    )
    print(str(output_path))
    return 0


def _run_repair_contextual_inputs(arguments: argparse.Namespace) -> int:
    nickname_assignments = [
        (instance_guid, nickname) for instance_guid, nickname in arguments.nickname
    ]
    output_path = repair_duplicate_contextual_input_nicknames(
        arguments.ghx_path,
        nickname_assignments=nickname_assignments,
    )
    print(str(output_path))
    return 0


def _run_get_script_source(arguments: argparse.Namespace) -> int:
    source_text = read_script_source_text(
        arguments.ghx_path,
        instance_guid=arguments.instance_guid,
    )
    print(source_text)
    return 0


def _run_remove_context_bake(arguments: argparse.Namespace) -> int:
    output_path = remove_context_bake_by_instance_guid(
        arguments.ghx_path,
        instance_guid=arguments.instance_guid,
    )
    print(str(output_path))
    return 0


def _run_add_csharp_number_input(arguments: argparse.Namespace) -> int:
    try:
        output_path = add_csharp_number_input(
            arguments.ghx_path,
            contextual_nickname=arguments.name,
            variable_name=arguments.variable_name,
            instance_guid=arguments.instance_guid,
        )
    except ScriptGraphEditError as edit_error:
        print(str(edit_error), file=sys.stderr)
        return 1
    print(str(output_path))
    return 0


def _run_remove_csharp_input(arguments: argparse.Namespace) -> int:
    try:
        output_path = remove_csharp_input(
            arguments.ghx_path,
            variable_name=arguments.variable_name,
            instance_guid=arguments.instance_guid,
        )
    except ScriptGraphEditError as edit_error:
        print(str(edit_error), file=sys.stderr)
        return 1
    print(str(output_path))
    return 0


def _run_rename_csharp_input(arguments: argparse.Namespace) -> int:
    try:
        output_path = rename_csharp_input(
            arguments.ghx_path,
            contextual_nickname=arguments.name,
            new_contextual_nickname=arguments.new_name,
            new_variable_name=arguments.variable_name,
            instance_guid=arguments.instance_guid,
        )
    except ScriptGraphEditError as edit_error:
        print(str(edit_error), file=sys.stderr)
        return 1
    print(str(output_path))
    return 0


def _resolve_script_source_text(arguments: argparse.Namespace) -> str:
    if arguments.source_file is not None and arguments.source_text is not None:
        raise SystemExit("Use either --source-file or --source-text, not both.")
    if arguments.source_file is not None:
        return arguments.source_file.read_text(encoding="utf-8")
    if arguments.source_text is not None:
        return arguments.source_text
    raise SystemExit("One of --source-file or --source-text is required.")


def _run_extract_patterns(arguments: argparse.Namespace) -> int:
    exclude_embedded_geometry = not arguments.include_embedded_geometry
    catalog_path = extract_patterns(
        arguments.source_path,
        output_dir=arguments.output_dir,
        exclude_embedded_geometry=exclude_embedded_geometry,
    )
    print(str(catalog_path))
    return 0


def _run_list_patterns(arguments: argparse.Namespace) -> int:
    catalog = load_pattern_catalog(arguments.catalog)
    if arguments.json:
        print(json.dumps(catalog.to_dict(), indent=2, ensure_ascii=False))
        return 0

    for pattern in catalog.patterns:
        print(f"{pattern.pattern_id}: {pattern.title}")
    return 0


def _run_inspect_pattern(arguments: argparse.Namespace) -> int:
    catalog = load_pattern_catalog(arguments.catalog)
    pattern = find_pattern_entry(catalog, arguments.pattern_id)
    payload = {
        "pattern_id": pattern.pattern_id,
        "title": pattern.title,
        "pattern_ghx": pattern.pattern_ghx,
        "object_count": pattern.object_count,
        "valid": pattern.valid,
        "rhino_compute_ready": pattern.rhino_compute_ready,
        "geometry_embedded": pattern.geometry_embedded,
        "compute_contract": pattern.compute_contract,
        "boundary_inputs": pattern.boundary_inputs,
    }
    if arguments.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def _run_generate_from_pattern(arguments: argparse.Namespace) -> int:
    output_path = generate_from_pattern(
        arguments.pattern_id,
        catalog_directory=arguments.catalog,
        output_path=arguments.output,
        document_name=arguments.document_name,
    )
    print(str(output_path))
    return 0


def _run_add_gradient_outputs(arguments: argparse.Namespace) -> int:
    try:
        transform_result = transform_penalty_graph_for_gradient(
            arguments.input,
            arguments.output,
        )
    except GradientTransformError as transform_error:
        print(str(transform_error), file=sys.stderr)
        return 1

    print(str(transform_result.output_path))
    return 0


def _run_descend_gradient(arguments: argparse.Namespace) -> int:
    try:
        descent_config = _build_gradient_descent_config(arguments)
        evaluator = _build_gradient_descent_evaluator(arguments)
        descent_result = run_projected_gradient_descent(evaluator, descent_config)
    except GradientDescentError as descent_error:
        print(str(descent_error), file=sys.stderr)
        return 1

    payload = descent_result.to_dict()
    if not arguments.no_record:
        record_path = write_descent_run_record(
            record_path=Path(arguments.record_json),
            gradient_ghx_path=arguments.ghx_path,
            descent_config=descent_config,
            descent_result=descent_result,
            compute_url=arguments.url,
        )
        payload["record_path"] = str(record_path)

    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def _build_gradient_descent_evaluator(
    arguments: argparse.Namespace,
) -> OriginalFiniteDifferenceEvaluator | RhinoComputePenaltyGradientEvaluator:
    if arguments.source_ghx is None:
        return RhinoComputePenaltyGradientEvaluator(
            gradient_ghx_path=arguments.ghx_path,
            compute_url=arguments.url,
        )
    if not arguments.source_ghx.is_file():
        raise GradientDescentError(f"Source GHX file was not found: {arguments.source_ghx}")
    return OriginalFiniteDifferenceEvaluator(
        source_ghx_path=arguments.source_ghx,
        compute_url=arguments.url,
        finite_difference_step=arguments.finite_difference_step,
    )


def _build_gradient_descent_config(arguments: argparse.Namespace) -> GradientDescentConfig:
    initial_input_values = dict(DEFAULT_INITIAL_INPUT_VALUES)
    for nickname, raw_value in arguments.initial:
        if nickname not in CONTEXTUAL_INPUT_NICKNAMES:
            raise GradientDescentError(
                f"Unsupported initial input nickname {nickname!r}. "
                f"Expected one of: {', '.join(CONTEXTUAL_INPUT_NICKNAMES)}."
            )
        initial_input_values[nickname] = float(raw_value)

    fixed_variable_values = dict(DEFAULT_FIXED_VARIABLE_VALUES)
    for nickname, raw_value in arguments.fixed:
        if nickname not in CONTEXTUAL_INPUT_NICKNAMES:
            raise GradientDescentError(
                f"Unsupported fixed input nickname {nickname!r}. "
                f"Expected one of: {', '.join(CONTEXTUAL_INPUT_NICKNAMES)}."
            )
        fixed_variable_values[nickname] = float(raw_value)

    return GradientDescentConfig(
        initial_input_values=initial_input_values,
        fixed_variable_values=fixed_variable_values,
        penalty_tolerance=arguments.tolerance,
        gradient_tolerance=arguments.gradient_tolerance,
        maximum_iteration_count=arguments.max_iterations,
        initial_step_size=arguments.initial_step_size,
        maximum_step_size=arguments.maximum_step_size,
        minimum_step_size=arguments.minimum_step_size,
        step_growth_factor=arguments.step_growth_factor,
    )


def _parse_numeric_value(raw_value: str) -> float | int:
    if "." in raw_value or "e" in raw_value.lower():
        return float(raw_value)
    return int(raw_value)


def _build_compute_input_values(arguments: argparse.Namespace) -> list[ComputeInputValue]:
    input_values: list[ComputeInputValue] = [
        ComputeInputValue(nickname=nickname, value=_parse_numeric_value(raw_value), kind="number")
        for nickname, raw_value in arguments.number
    ]
    for nickname, raw_value in arguments.point:
        input_values.append(
            ComputeInputValue(
                nickname=nickname,
                value=parse_point3d_coordinates(raw_value),
                kind="point",
            )
        )
    for nickname, raw_value in arguments.text:
        input_values.append(
            ComputeInputValue(
                nickname=nickname,
                value=raw_value,
                kind="string",
            )
        )
    return input_values


if __name__ == "__main__":
    sys.exit(main())
