"""Create csharp_step_scale.ghx: STEP import + Get Number multiplier through C# Script."""

from __future__ import annotations

import argparse
from pathlib import Path

from pyghx.fixture_generation import create_csharp_step_scale_fixture

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = REPOSITORY_ROOT / "tests" / "fixtures" / "csharp_step_scale.ghx"


def main(output_path: Path | None = None) -> Path:
    destination_path = output_path or OUTPUT_PATH
    return create_csharp_step_scale_fixture(
        output_path=destination_path,
        repository_root=REPOSITORY_ROOT,
    )


if __name__ == "__main__":
    argument_parser = argparse.ArgumentParser(description=__doc__)
    argument_parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional output path for the generated GHX fixture.",
    )
    command_line_arguments = argument_parser.parse_args()
    print(main(command_line_arguments.output))
