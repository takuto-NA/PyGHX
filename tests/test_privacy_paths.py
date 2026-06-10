"""Guard against committing private local file paths into tracked artifacts."""

from __future__ import annotations

from pathlib import Path

PRIVATE_PATH_FRAGMENT_PATTERNS = (
    "\\Downloads\\",
    "\\資料系\\",
)

TRACKED_SCAN_PATHS = (
    Path("tests/fixtures"),
    Path("src"),
    Path("scripts"),
    Path("README.md"),
)


def test_tracked_sources_do_not_embed_private_local_paths() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    violations: list[str] = []

    for scan_root in TRACKED_SCAN_PATHS:
        scan_path = repository_root / scan_root
        if scan_path.is_file():
            candidate_paths = [scan_path]
        else:
            candidate_paths = [
                path
                for path in scan_path.rglob("*")
                if path.is_file()
                and path.suffix in {".py", ".ghx", ".md", ".cs"}
                and "__pycache__" not in path.parts
            ]

        for candidate_path in candidate_paths:
            file_text = candidate_path.read_text(encoding="utf-8")
            for fragment_pattern in PRIVATE_PATH_FRAGMENT_PATTERNS:
                if fragment_pattern in file_text:
                    relative_path = candidate_path.relative_to(repository_root)
                    violations.append(f"{relative_path}: contains {fragment_pattern!r}")

    assert not violations, "Private path fragments found:\n" + "\n".join(violations)
