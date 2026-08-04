"""RegexRx - regex-driven extraction of structured records from clinical text."""

from .extractors import (
    ConfigError,
    Document,
    Extractor,
    Match,
    extract_text,
    load_patterns,
    normalize_text,
)

__version__ = "1.0.0"
__all__ = [
    "ConfigError",
    "Document",
    "Extractor",
    "Match",
    "extract_text",
    "load_patterns",
    "normalize_text",
]
