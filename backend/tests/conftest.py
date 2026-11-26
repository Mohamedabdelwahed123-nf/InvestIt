"""Shared fixtures."""

from pathlib import Path

import pytest

from backend.data.load_csv import SAMPLE_DIR


@pytest.fixture
def sample_dir() -> Path:
    return SAMPLE_DIR


@pytest.fixture
def write_csv(tmp_path: Path):
    """Write a small CSV (header + rows) and return its path."""

    def _write(name: str, header: str, *rows: str) -> Path:
        path = tmp_path / name
        path.write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")
        return path

    return _write
