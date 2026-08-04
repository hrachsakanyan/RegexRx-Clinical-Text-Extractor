"""Turning :class:`Document` objects into JSON, CSV, summaries and highlights."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable, Sequence

from .extractors import Document, Match

CSV_COLUMNS = [
    "source", "field", "value", "raw", "line", "start", "end", "pattern", "details",
]

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

# One colour per field so a highlighted note stays readable at a glance.
FIELD_COLORS = {
    "dates": "\033[38;5;39m",
    "ages": "\033[38;5;213m",
    "blood_pressure": "\033[38;5;203m",
    "vitals": "\033[38;5;208m",
    "lab_values": "\033[38;5;77m",
    "medications": "\033[38;5;220m",
    "icd_codes": "\033[38;5;141m",
    "mrns": "\033[38;5;45m",
    "phones": "\033[38;5;180m",
    "emails": "\033[38;5;117m",
}
FALLBACK_COLOR = "\033[38;5;250m"


# --------------------------------------------------------------------------- #
# aggregation
# --------------------------------------------------------------------------- #

def aggregate(documents: Sequence[Document]) -> dict[str, object]:
    """Corpus-level counts: per file, per field, and unique values per field."""
    totals: dict[str, int] = {}
    rejected: dict[str, int] = {}
    unique: dict[str, set[str]] = {}
    per_file: dict[str, dict[str, int]] = {}

    for document in documents:
        per_file[document.source] = document.summary()
        for field, count in document.summary().items():
            totals[field] = totals.get(field, 0) + count
        for field, count in document.rejected.items():
            rejected[field] = rejected.get(field, 0) + count
        for match in document.matches:
            unique.setdefault(match.field, set()).add(match.value)

    return {
        "documents": len(documents),
        "total_matches": sum(totals.values()),
        "matches_by_field": dict(sorted(totals.items())),
        "unique_values_by_field": {
            field: len(values) for field, values in sorted(unique.items())
        },
        "rejected_by_field": dict(sorted(rejected.items())),
        "matches_by_document": per_file,
    }


# --------------------------------------------------------------------------- #
# writers
# --------------------------------------------------------------------------- #

def write_json(documents: Sequence[Document], out_dir: str | Path) -> list[Path]:
    """One <note>.json per input note, plus a corpus-wide summary.json."""
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for document in documents:
        target = directory / f"{Path(document.source).stem}.json"
        target.write_text(
            json.dumps(document.to_dict(), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        written.append(target)

    summary_path = directory / "summary.json"
    summary_path.write_text(
        json.dumps(aggregate(documents), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    written.append(summary_path)
    return written


def _flatten_details(match: Match) -> str:
    return "; ".join(f"{k}={v}" for k, v in match.details.items() if v is not None)


def write_csv(documents: Sequence[Document], out_path: str | Path) -> Path:
    """Every match from every note as one flat row - spreadsheet friendly."""
    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for document in documents:
            for match in document.matches:
                writer.writerow({
                    "source": document.source,
                    "field": match.field,
                    "value": match.value,
                    "raw": match.raw,
                    "line": match.line,
                    "start": match.start,
                    "end": match.end,
                    "pattern": match.pattern,
                    "details": _flatten_details(match),
                })
    return target


# --------------------------------------------------------------------------- #
# console output
# --------------------------------------------------------------------------- #

def _color(field: str, use_color: bool) -> str:
    if not use_color:
        return ""
    return FIELD_COLORS.get(field, FALLBACK_COLOR)


def highlight(document: Document, use_color: bool = True) -> str:
    """Re-render the note with every match marked.

    With colour the matched span is painted in the field's colour; without it
    (piping to a file, Windows terminals without ANSI) the span is wrapped as
    ``[field: value]`` so the output stays readable in plain text.
    """
    text = document.text
    chunks: list[str] = []
    cursor = 0
    for match in sorted(document.matches, key=lambda m: m.start):
        if match.start < cursor:  # defensive: overlaps are already resolved
            continue
        chunks.append(text[cursor:match.start])
        if use_color:
            chunks.append(f"{_color(match.field, True)}{BOLD}{text[match.start:match.end]}{RESET}")
        else:
            chunks.append(f"[{match.field}: {text[match.start:match.end]}]")
        cursor = match.end
    chunks.append(text[cursor:])
    return "".join(chunks)


def legend(fields: Iterable[str], use_color: bool = True) -> str:
    parts = []
    for field in fields:
        parts.append(f"{_color(field, use_color)}{field}{RESET if use_color else ''}")
    return "legend: " + "  ".join(parts)


def format_summary(documents: Sequence[Document], use_color: bool = True) -> str:
    """A compact per-field / per-file count table for the terminal."""
    stats = aggregate(documents)
    fields = sorted(stats["matches_by_field"])  # type: ignore[arg-type]
    bold = BOLD if use_color else ""
    dim = DIM if use_color else ""
    reset = RESET if use_color else ""

    lines = [f"{bold}Extraction summary{reset}"]
    if not fields:
        lines.append("  no matches found")
        return "\n".join(lines)

    width = max(len(f) for f in fields) + 2
    lines.append(f"  {'field'.ljust(width)}{'matches':>8}{'unique':>8}{'rejected':>10}")
    lines.append(f"  {'-' * (width + 26)}")
    for field in fields:
        matches = stats["matches_by_field"][field]  # type: ignore[index]
        unique = stats["unique_values_by_field"].get(field, 0)  # type: ignore[union-attr]
        dropped = stats["rejected_by_field"].get(field, 0)  # type: ignore[union-attr]
        lines.append(
            f"  {_color(field, use_color)}{field.ljust(width)}{reset}"
            f"{matches:>8}{unique:>8}{dropped:>10}"
        )
    lines.append(f"  {'-' * (width + 26)}")
    lines.append(f"  {'TOTAL'.ljust(width)}{stats['total_matches']:>8}")
    lines.append("")
    lines.append(f"{bold}Per document{reset}")
    for source, counts in stats["matches_by_document"].items():  # type: ignore[union-attr]
        total = sum(counts.values())
        detail = ", ".join(f"{field}={count}" for field, count in counts.items())
        lines.append(f"  {source}: {total} match(es) {dim}[{detail}]{reset}")
    return "\n".join(lines)
