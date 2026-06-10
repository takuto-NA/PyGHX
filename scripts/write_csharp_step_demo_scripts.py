"""Write demo C# Script files that match composed C# STEP fixture script bodies."""

from __future__ import annotations

from pathlib import Path

from pyghx.fixture_generation import write_csharp_step_demo_script_files

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    import_demo_script_path, scale_demo_script_path = write_csharp_step_demo_script_files(
        REPOSITORY_ROOT,
    )
    print(import_demo_script_path)
    print(scale_demo_script_path)
