"""Command-line interface for PyGHX."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pyghx.compute import ComputeInputValue, evaluate_document, extract_numeric_result
from pyghx.constants import DEFAULT_RHINO_COMPUTE_URL
from pyghx.generate import generate_addition_document, generate_minimal_document
from pyghx.inspect import inspect_document
from pyghx.reference import extract_patterns, generate_from_pattern, load_pattern_catalog
from pyghx.reference.catalog import find_pattern_entry
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
        "--url",
        default=DEFAULT_RHINO_COMPUTE_URL,
        help="RhinoCompute base URL.",
    )
    compute_parser.add_argument("--json", action="store_true", help="Emit JSON result.")

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
    if arguments.command == "extract-patterns":
        return _run_extract_patterns(arguments)
    if arguments.command == "list-patterns":
        return _run_list_patterns(arguments)
    if arguments.command == "inspect-pattern":
        return _run_inspect_pattern(arguments)
    if arguments.command == "generate-from-pattern":
        return _run_generate_from_pattern(arguments)

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
    input_values = [
        ComputeInputValue(nickname=nickname, value=_parse_numeric_value(raw_value))
        for nickname, raw_value in arguments.number
    ]
    compute_result = evaluate_document(
        arguments.ghx_path,
        input_values=input_values,
        compute_url=arguments.url,
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


def _parse_numeric_value(raw_value: str) -> float | int:
    if "." in raw_value or "e" in raw_value.lower():
        return float(raw_value)
    return int(raw_value)


if __name__ == "__main__":
    sys.exit(main())
