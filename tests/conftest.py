"""Shared pytest fixtures for PyGHX."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers import (
    ADDITION_FIXTURE_PATH,
    MALFORMED_FIXTURE_PATH,
    UNKNOWN_STRUCTURE_FIXTURE_PATH,
    VARIATION_FIXTURE_PATH,
)


@pytest.fixture
def addition_fixture_path() -> Path:
    return ADDITION_FIXTURE_PATH


@pytest.fixture
def variation_fixture_path() -> Path:
    return VARIATION_FIXTURE_PATH


@pytest.fixture
def malformed_fixture_path() -> Path:
    return MALFORMED_FIXTURE_PATH


@pytest.fixture
def unknown_structure_fixture_path() -> Path:
    return UNKNOWN_STRUCTURE_FIXTURE_PATH
