"""Parse and synchronize C# Script RunScript signatures."""

from __future__ import annotations

import re

RUN_SCRIPT_SIGNATURE_PATTERN = re.compile(
    r"(private\s+void\s+RunScript\s*\()([^)]*)(\))",
    re.MULTILINE,
)

RUN_SCRIPT_INPUT_PARAMETER_PATTERN = re.compile(
    r"^object\s+([A-Za-z_][A-Za-z0-9_]*)$",
)

RUN_SCRIPT_OUTPUT_PARAMETER_PATTERN = re.compile(
    r"^ref\s+object\s+([A-Za-z_][A-Za-z0-9_]*)$",
)


class ScriptSourceError(Exception):
    """Raised when C# Script source text cannot be parsed or updated."""


def parse_run_script_signature(source_text: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return input and output variable names from a RunScript signature."""
    signature_match = RUN_SCRIPT_SIGNATURE_PATTERN.search(source_text)
    if signature_match is None:
        raise ScriptSourceError("RunScript signature was not found in C# Script source text.")

    raw_parameter_text = signature_match.group(2).strip()
    if not raw_parameter_text:
        return (), ()

    input_variable_names: list[str] = []
    output_variable_names: list[str] = []
    for raw_parameter in raw_parameter_text.split(","):
        normalized_parameter = raw_parameter.strip()
        if not normalized_parameter:
            continue

        output_match = RUN_SCRIPT_OUTPUT_PARAMETER_PATTERN.match(normalized_parameter)
        if output_match is not None:
            output_variable_names.append(output_match.group(1))
            continue

        input_match = RUN_SCRIPT_INPUT_PARAMETER_PATTERN.match(normalized_parameter)
        if input_match is not None:
            input_variable_names.append(input_match.group(1))
            continue

        raise ScriptSourceError(
            f"Unsupported RunScript parameter syntax: {normalized_parameter!r}."
        )

    return tuple(input_variable_names), tuple(output_variable_names)


def build_run_script_signature_warning(source_text: str) -> str | None:
    """Return a warning when RunScript signature is missing from script source."""
    if RUN_SCRIPT_SIGNATURE_PATTERN.search(source_text):
        return None
    return "RunScript signature was not found in C# Script source text."


def synchronize_run_script_input_variables(
    source_text: str,
    input_variable_names: list[str],
) -> str:
    """Replace RunScript input parameters while preserving output parameters."""
    signature_match = RUN_SCRIPT_SIGNATURE_PATTERN.search(source_text)
    if signature_match is None:
        raise ScriptSourceError("RunScript signature was not found in C# Script source text.")

    _, existing_output_variable_names = parse_run_script_signature(source_text)
    parameter_parts = [f"object {variable_name}" for variable_name in input_variable_names]
    parameter_parts.extend(
        f"ref object {output_variable_name}"
        for output_variable_name in existing_output_variable_names
    )
    replacement_signature = (
        f"{signature_match.group(1)}{', '.join(parameter_parts)}{signature_match.group(3)}"
    )
    return (
        source_text[: signature_match.start()]
        + replacement_signature
        + source_text[signature_match.end() :]
    )
