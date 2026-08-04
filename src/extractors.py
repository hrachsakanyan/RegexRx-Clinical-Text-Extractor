"""The extraction engine: config -> compiled regexes -> structured records."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from .validators import VALIDATORS, default_validator

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "patterns.json"

FLAG_MAP = {
    "IGNORECASE": re.IGNORECASE, "I": re.IGNORECASE,
    "MULTILINE": re.MULTILINE, "M": re.MULTILINE,
    "DOTALL": re.DOTALL, "S": re.DOTALL,
    "VERBOSE": re.VERBOSE, "X": re.VERBOSE,
}

CONTEXT_CHARS = 40


class ConfigError(ValueError):
    """Raised when a pattern config is malformed or references an unknown validator."""


# --------------------------------------------------------------------------- #
# text clean-up
# --------------------------------------------------------------------------- #

_REPLACEMENTS = {
    "\r\n": "\n", "\r": "\n",
    " ": " ", " ": " ", " ": " ", "﻿": "",
    "‐": "-", "‑": "-", "‒": "-", "–": "-",
    "—": "-", "−": "-",
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "⁄": "/", "：": ":",
    "μ": "µ",  # Greek mu -> micro sign, so "µg" is one spelling
}


def normalize_text(text: str) -> str:
    """Tame the messy bits of real notes before matching.

    Line endings, non-breaking spaces, smart quotes and the various Unicode
    dashes are folded to their ASCII equivalents.  Offsets reported by the
    extractor refer to this normalised text, which is also what
    :func:`highlight` renders.
    """
    text = unicodedata.normalize("NFC", text)
    for old, new in _REPLACEMENTS.items():
        text = text.replace(old, new)
    # Collapse runs of spaces/tabs (but never newlines - line numbers matter).
    return re.sub(r"[ \t]+", " ", text)


# --------------------------------------------------------------------------- #
# config
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class CompiledPattern:
    """One named regex belonging to one field."""

    field: str
    name: str
    regex: re.Pattern[str]
    priority: int
    validator: str | None = None
    description: str = ""

    @property
    def qualified_name(self) -> str:
        return f"{self.field}.{self.name}"


def load_patterns(
    config_path: str | Path | None = None,
    fields: Sequence[str] | None = None,
) -> list[CompiledPattern]:
    """Compile the pattern config into :class:`CompiledPattern` objects.

    `fields` optionally restricts extraction to a subset of field names.
    """
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"pattern config not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"pattern config is not valid JSON ({path}): {exc}") from exc

    if not isinstance(raw.get("fields"), list) or not raw["fields"]:
        raise ConfigError(f"pattern config {path} has no 'fields' list")

    wanted = {f.lower() for f in fields} if fields else None
    known_fields = {entry.get("name") for entry in raw["fields"]}
    if wanted:
        unknown = wanted - {name.lower() for name in known_fields if name}
        if unknown:
            raise ConfigError(
                f"unknown field(s): {', '.join(sorted(unknown))}. "
                f"Available: {', '.join(sorted(n for n in known_fields if n))}"
            )

    compiled: list[CompiledPattern] = []
    for entry in raw["fields"]:
        name = entry.get("name")
        if not name:
            raise ConfigError("every field needs a 'name'")
        if wanted and name.lower() not in wanted:
            continue

        validator_name = entry.get("validator")
        if validator_name and validator_name not in VALIDATORS:
            raise ConfigError(
                f"field '{name}' references unknown validator '{validator_name}'"
            )

        patterns = entry.get("patterns") or []
        if not patterns:
            raise ConfigError(f"field '{name}' has no patterns")

        for index, spec in enumerate(patterns):
            flags = 0
            for flag_name in spec.get("flags", []):
                try:
                    flags |= FLAG_MAP[flag_name.upper()]
                except KeyError as exc:
                    raise ConfigError(
                        f"unknown regex flag '{flag_name}' in {name}.{spec.get('name')}"
                    ) from exc
            try:
                regex = re.compile(spec["regex"], flags)
            except KeyError as exc:
                raise ConfigError(f"pattern {name}[{index}] has no 'regex'") from exc
            except re.error as exc:
                raise ConfigError(
                    f"invalid regex in {name}.{spec.get('name', index)}: {exc}"
                ) from exc

            compiled.append(
                CompiledPattern(
                    field=name,
                    name=spec.get("name", f"pattern_{index}"),
                    regex=regex,
                    priority=int(entry.get("priority", 50)),
                    validator=validator_name,
                    description=entry.get("description", ""),
                )
            )
    return compiled


# --------------------------------------------------------------------------- #
# results
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Match:
    """A single validated hit."""

    field: str
    pattern: str
    value: str
    raw: str
    start: int
    end: int
    line: int
    context: str
    details: dict[str, Any] = dataclass_field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "raw": self.raw,
            "line": self.line,
            "start": self.start,
            "end": self.end,
            "pattern": self.pattern,
            "context": self.context,
            **({"details": self.details} if self.details else {}),
        }


@dataclass
class Document:
    """Everything extracted from one note."""

    source: str
    text: str
    matches: list[Match] = dataclass_field(default_factory=list)
    rejected: dict[str, int] = dataclass_field(default_factory=dict)

    def by_field(self) -> dict[str, list[Match]]:
        grouped: dict[str, list[Match]] = {}
        for match in self.matches:
            grouped.setdefault(match.field, []).append(match)
        return grouped

    def summary(self) -> dict[str, int]:
        """How many matches of each kind - the headline number of the project."""
        counts = {field: len(items) for field, items in self.by_field().items()}
        return dict(sorted(counts.items()))

    def values(self, field: str) -> list[str]:
        return [m.value for m in self.matches if m.field == field]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "characters": len(self.text),
            "lines": self.text.count("\n") + 1 if self.text else 0,
            "total_matches": len(self.matches),
            "summary": self.summary(),
            "rejected": dict(sorted(self.rejected.items())),
            "extracted": {
                field: [m.to_dict() for m in items]
                for field, items in sorted(self.by_field().items())
            },
        }


# --------------------------------------------------------------------------- #
# engine
# --------------------------------------------------------------------------- #

def _line_starts(text: str) -> list[int]:
    starts = [0]
    for index, char in enumerate(text):
        if char == "\n":
            starts.append(index + 1)
    return starts


def _line_number(line_starts: list[int], position: int) -> int:
    low, high = 0, len(line_starts) - 1
    while low < high:
        mid = (low + high + 1) // 2
        if line_starts[mid] <= position:
            low = mid
        else:
            high = mid - 1
    return low + 1


def resolve_overlaps(matches: Iterable[Match], priorities: dict[str, int]) -> list[Match]:
    """Drop hits whose span is already claimed by a stronger match.

    "glucose 180 mg/dL" should be one lab value, not a lab value plus a dose.
    Ranking: field priority, then the longer span, then the earlier position.
    """
    ranked = sorted(
        matches,
        key=lambda m: (-priorities.get(m.field, 0), -(m.end - m.start), m.start),
    )
    kept: list[Match] = []
    for match in ranked:
        if any(match.start < other.end and other.start < match.end for other in kept):
            continue
        kept.append(match)
    return sorted(kept, key=lambda m: (m.start, m.field))


class Extractor:
    """Runs every compiled pattern over a note and returns structured records."""

    def __init__(
        self,
        patterns: Sequence[CompiledPattern] | None = None,
        *,
        config_path: str | Path | None = None,
        fields: Sequence[str] | None = None,
        resolve_conflicts: bool = True,
    ) -> None:
        self.patterns = list(patterns) if patterns is not None else load_patterns(config_path, fields)
        self.resolve_conflicts = resolve_conflicts
        self.priorities = {p.field: p.priority for p in self.patterns}

    @property
    def fields(self) -> list[str]:
        seen: dict[str, None] = {}
        for pattern in self.patterns:
            seen.setdefault(pattern.field, None)
        return list(seen)

    def extract(self, text: str, source: str = "<text>") -> Document:
        clean = normalize_text(text)
        line_starts = _line_starts(clean)
        found: list[Match] = []
        rejected: dict[str, int] = {}

        for pattern in self.patterns:
            validate = VALIDATORS.get(pattern.validator or "", default_validator)
            for hit in pattern.regex.finditer(clean):
                raw = " ".join(hit.group(0).split())  # doses can wrap across lines
                if not raw:
                    continue
                try:
                    result = validate(hit.groupdict(), raw)
                except (ValueError, KeyError, TypeError):
                    result = None
                if result is None:
                    rejected[pattern.field] = rejected.get(pattern.field, 0) + 1
                    continue
                value, details = result
                found.append(
                    Match(
                        field=pattern.field,
                        pattern=pattern.qualified_name,
                        value=value,
                        raw=raw,
                        start=hit.start(),
                        end=hit.end(),
                        line=_line_number(line_starts, hit.start()),
                        context=_context(clean, hit.start(), hit.end()),
                        details=details,
                    )
                )

        if self.resolve_conflicts:
            found = resolve_overlaps(found, self.priorities)
        else:
            found.sort(key=lambda m: (m.start, m.field))

        return Document(source=source, text=clean, matches=found, rejected=rejected)

    def extract_file(self, path: str | Path, encoding: str = "utf-8") -> Document:
        file_path = Path(path)
        text = file_path.read_text(encoding=encoding, errors="replace")
        return self.extract(text, source=file_path.name)

    def extract_folder(
        self,
        folder: str | Path,
        *,
        extensions: Sequence[str] = (".txt", ".md", ".log"),
        recursive: bool = True,
        encoding: str = "utf-8",
    ) -> list[Document]:
        """Batch mode: every matching file in a folder, sorted by name."""
        root = Path(folder)
        if not root.is_dir():
            raise NotADirectoryError(f"not a folder: {root}")
        wanted = {ext.lower() if ext.startswith(".") else f".{ext.lower()}" for ext in extensions}
        paths = sorted(
            p for p in (root.rglob("*") if recursive else root.glob("*"))
            if p.is_file() and p.suffix.lower() in wanted
        )
        return [self.extract_file(path, encoding=encoding) for path in paths]


def _context(text: str, start: int, end: int, width: int = CONTEXT_CHARS) -> str:
    left = max(0, start - width)
    right = min(len(text), end + width)
    snippet = text[left:right].replace("\n", " ")
    return f"{'...' if left > 0 else ''}{snippet.strip()}{'...' if right < len(text) else ''}"


def extract_text(text: str, **kwargs: Any) -> dict[str, Any]:
    """One-call convenience wrapper: text in, plain dict out."""
    return Extractor(**kwargs).extract(text).to_dict()


def iter_documents(documents: Iterable[Document]) -> Iterator[tuple[str, Match]]:
    for document in documents:
        for match in document.matches:
            yield document.source, match
