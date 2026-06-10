"""Tests for GHX structural integrity diagnostics."""

from __future__ import annotations

from pathlib import Path

import pytest

from pyghx.ghx_integrity import build_ghx_integrity_diagnostics
from pyghx.validate import validate_document
from pyghx.compute import ComputeInputValue, evaluate_document
from tests.ghx_fixture_mutators import (
    mutate_definition_objects_chunks_count,
    mutate_definition_objects_object_count,
    mutate_definition_objects_object_index_gap,
    mutate_duplicate_instance_guid,
    mutate_gha_libraries_count,
    mutate_unresolved_source_guid,
    write_mutated_ghx_fixture,
)
from tests.helpers import (
    ADDITION_FIXTURE_PATH,
    IMPORT_TWO_MODELS_FIXTURE_PATH,
    run_pyghx_cli,
)

UNREACHABLE_COMPUTE_URL = "http://localhost:1/"


def _diagnostic_codes(diagnostics: list[dict[str, str]]) -> set[str]:
    return {diagnostic["code"] for diagnostic in diagnostics}


def test_known_good_fixtures_have_no_integrity_errors() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    ghx_paths = sorted(
        path
        for path in repository_root.glob("**/*.ghx")
        if path.name != "malformed.ghx"
    )
    assert ghx_paths

    for ghx_path in ghx_paths:
        diagnostics = build_ghx_integrity_diagnostics(ghx_path)
        error_codes = {
            diagnostic["code"]
            for diagnostic in diagnostics
            if diagnostic["level"] == "error"
        }
        assert not error_codes, f"{ghx_path} reported integrity errors: {error_codes}"


def test_generated_addition_may_report_library_count_warning_only() -> None:
    repository_root = Path(__file__).resolve().parents[1]
    generated_addition_path = repository_root / "generated_addition.ghx"
    if not generated_addition_path.is_file():
        pytest.skip("generated_addition.ghx is not present.")

    diagnostics = build_ghx_integrity_diagnostics(generated_addition_path)
    error_codes = {
        diagnostic["code"]
        for diagnostic in diagnostics
        if diagnostic["level"] == "error"
    }
    warning_codes = {
        diagnostic["code"]
        for diagnostic in diagnostics
        if diagnostic["level"] == "warning"
    }
    assert not error_codes
    assert "library_count_mismatch" in warning_codes


@pytest.mark.parametrize(
    ("mutation_callback", "expected_error_code"),
    [
        (lambda root: mutate_definition_objects_object_count(root, stale_object_count=99), "object_count_mismatch"),
        (lambda root: mutate_definition_objects_chunks_count(root, stale_chunks_count=99), "definition_objects_chunks_count_mismatch"),
        (lambda root: mutate_definition_objects_object_index_gap(root), "object_index_mismatch"),
        (lambda root: mutate_duplicate_instance_guid(root), "duplicate_instance_guid"),
        (lambda root: mutate_unresolved_source_guid(root), "unresolved_source_guid"),
    ],
)
def test_mutated_import_two_models_reports_structural_errors(
    tmp_path: Path,
    mutation_callback,
    expected_error_code: str,
) -> None:
    broken_fixture_path = tmp_path / "broken_import_two_models.ghx"
    write_mutated_ghx_fixture(
        IMPORT_TWO_MODELS_FIXTURE_PATH,
        broken_fixture_path,
        mutation_callback,
    )

    diagnostics = build_ghx_integrity_diagnostics(broken_fixture_path)
    assert expected_error_code in _diagnostic_codes(diagnostics)

    validation_result = validate_document(broken_fixture_path)
    assert validation_result.valid is False
    assert expected_error_code in _diagnostic_codes(list(validation_result.diagnostics))


def test_mutated_library_count_is_warning_not_preflight_blocker(tmp_path: Path) -> None:
    broken_fixture_path = tmp_path / "broken_library_count.ghx"
    write_mutated_ghx_fixture(
        ADDITION_FIXTURE_PATH,
        broken_fixture_path,
        lambda root: mutate_gha_libraries_count(root, stale_library_count=99),
    )

    diagnostics = build_ghx_integrity_diagnostics(broken_fixture_path)
    assert "library_count_mismatch" in _diagnostic_codes(diagnostics)
    assert not any(diagnostic["level"] == "error" for diagnostic in diagnostics)

    validation_result = validate_document(broken_fixture_path)
    assert validation_result.valid is True


def test_compute_preflight_blocks_structurally_invalid_ghx_before_http(tmp_path: Path) -> None:
    broken_fixture_path = tmp_path / "broken_preflight.ghx"
    write_mutated_ghx_fixture(
        IMPORT_TWO_MODELS_FIXTURE_PATH,
        broken_fixture_path,
        lambda root: mutate_definition_objects_object_count(root, stale_object_count=99),
    )

    compute_result = evaluate_document(
        broken_fixture_path,
        input_values=[
            ComputeInputValue(
                nickname="Target",
                value=r"C:\models\target.stp",
                kind="file_path",
            ),
            ComputeInputValue(
                nickname="Obstacle",
                value=r"C:\models\obstacle.stp",
                kind="file_path",
            ),
        ],
        compute_url=UNREACHABLE_COMPUTE_URL,
    )
    assert compute_result.success is False
    diagnostic_codes = _diagnostic_codes(list(compute_result.diagnostics))
    assert "ghx_validation_error" in diagnostic_codes
    assert "object_count_mismatch" in diagnostic_codes
    assert "rhino_compute_unreachable" not in diagnostic_codes


def test_cli_validate_and_compute_preflight_for_broken_two_model_ghx(tmp_path: Path) -> None:
    broken_fixture_path = tmp_path / "broken_cli.ghx"
    write_mutated_ghx_fixture(
        IMPORT_TWO_MODELS_FIXTURE_PATH,
        broken_fixture_path,
        lambda root: mutate_definition_objects_object_index_gap(root),
    )

    validate_process = run_pyghx_cli(["validate", str(broken_fixture_path)])
    assert validate_process.returncode != 0
    assert "object_index_mismatch" in validate_process.stdout

    compute_process = run_pyghx_cli(
        [
            "compute",
            str(broken_fixture_path),
            "--text",
            "Target=C:\\models\\target.stp",
            "--text",
            "Obstacle=C:\\models\\obstacle.stp",
            "--url",
            UNREACHABLE_COMPUTE_URL,
            "--json",
        ]
    )
    assert compute_process.returncode != 0
    assert "ghx_validation_error" in compute_process.stdout
    assert "rhino_compute_unreachable" not in compute_process.stdout
