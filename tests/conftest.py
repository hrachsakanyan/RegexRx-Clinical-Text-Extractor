"""Shared fixtures. Adds the project root to sys.path so `src` imports work."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.extractors import Extractor  # noqa: E402  (path set up above)

SAMPLE_NOTES = PROJECT_ROOT / "data" / "sample_notes"


@pytest.fixture(scope="session")
def extractor() -> Extractor:
    return Extractor()


@pytest.fixture(scope="session")
def sample_notes() -> Path:
    return SAMPLE_NOTES


@pytest.fixture
def values(extractor):
    """values(text, "dates") -> list of normalised values for that field."""

    def _values(text: str, field: str) -> list[str]:
        return extractor.extract(text).values(field)

    return _values
