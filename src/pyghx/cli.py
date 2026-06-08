"""Command-line interface for PyGHX."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from pyghx.compute import ComputeInputValue, evaluate_document, extract_numeric_result
from pyghx.constants import DEFAULT_RHINO_COMPUTE_URL
from pyghx.generate import generate_minimal_document
from pyghx.inspect import inspect_document
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

    parser.error(f"Unknown command: {arguments.command}")
    return 2


def _run_inspect(arguments: argparse.Namespace) -> int:
    summary = inspect_document(arguments.ghx_path)
    if arguments.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0

    print(f"Document: {summary['document_metadata'].get('document_name')}")
    print(f"Objects: {summary['object_count']}")
    print(f"Contextual inputs: {len(summary['contextual_inputs'])}")
    print(f"Context Bake outputs: {len(summary['context_bake_outputs'])}")
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


def _parse_numeric_value(raw_value: str) -> float | int:
    if "." in raw_value or "e" in raw_value.lower():
        return float(raw_value)
    return int(raw_value)


if __name__ == "__main__":
    sys.exit(main())
