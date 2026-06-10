"""Create import_two_models.ghx with two Import 3DM chains for RhinoCompute tests."""

from __future__ import annotations

import argparse
from pathlib import Path

from pyghx.fixture_generation import create_default_import_two_models_fixture

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = REPOSITORY_ROOT / "tests" / "fixtures" / "import_model.ghx"
OUTPUT_PATH = REPOSITORY_ROOT / "tests" / "fixtures" / "import_two_models.ghx"


def main(output_path: Path | None = None) -> Path:
    destination_path = output_path or OUTPUT_PATH
    return create_default_import_two_models_fixture(
        output_path=destination_path,
        import_model_source_path=SOURCE_PATH,
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
