"""Output formats: JSON files, CSV export, aggregate counts, highlighting."""

from __future__ import annotations

import csv
import json
import re

from src.reporting import aggregate, format_summary, highlight, write_csv, write_json

NOTE_A = "MRN: 12345678\n53 y/o female, BP 138/86 mmHg, HbA1c 7.8 %"
NOTE_B = "Metformin 1000 mg PO BID started 2024-03-14, call (555) 208-4400"


def _documents(extractor):
    return [
        extractor.extract(NOTE_A, source="a.txt"),
        extractor.extract(NOTE_B, source="b.txt"),
    ]


def test_aggregate_counts(extractor):
    stats = aggregate(_documents(extractor))
    assert stats["documents"] == 2
    assert stats["total_matches"] == sum(stats["matches_by_field"].values())
    assert stats["matches_by_field"]["blood_pressure"] == 1
    assert set(stats["matches_by_document"]) == {"a.txt", "b.txt"}


def test_aggregate_counts_unique_values(extractor):
    documents = [extractor.extract("BP 138/86 mmHg and later BP 138/86 mmHg", source="x.txt")]
    stats = aggregate(documents)
    assert stats["matches_by_field"]["blood_pressure"] == 2
    assert stats["unique_values_by_field"]["blood_pressure"] == 1


def test_write_json_creates_one_file_per_note_plus_summary(extractor, tmp_path):
    written = write_json(_documents(extractor), tmp_path)
    names = {p.name for p in written}
    assert names == {"a.json", "b.json", "summary.json"}

    payload = json.loads((tmp_path / "a.json").read_text(encoding="utf-8"))
    assert payload["source"] == "a.txt"
    assert payload["extracted"]["ages"][0]["value"] == "53 y/o female"

    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["documents"] == 2


def test_write_csv_is_flat_and_complete(extractor, tmp_path):
    documents = _documents(extractor)
    target = write_csv(documents, tmp_path / "extractions.csv")
    with target.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == sum(len(d.matches) for d in documents)
    assert set(rows[0]) == {
        "source", "field", "value", "raw", "line", "start", "end", "pattern", "details",
    }
    bp_row = next(r for r in rows if r["field"] == "blood_pressure")
    assert bp_row["value"] == "138/86 mmHg"
    assert "systolic=138" in bp_row["details"]


def test_write_csv_creates_missing_folders(extractor, tmp_path):
    target = write_csv(_documents(extractor), tmp_path / "deep" / "nested" / "out.csv")
    assert target.exists()


def test_highlight_plain_marks_every_match(extractor):
    document = extractor.extract("BP 138/86 mmHg today")
    marked = highlight(document, use_color=False)
    assert marked == "[blood_pressure: BP 138/86 mmHg] today"


def test_highlight_color_wraps_in_ansi(extractor):
    document = extractor.extract("BP 138/86 mmHg")
    marked = highlight(document, use_color=True)
    assert marked.startswith("\033[")
    assert marked.endswith("\033[0m")


def test_highlight_preserves_the_note_text(extractor):
    document = extractor.extract(NOTE_A)
    marked = highlight(document, use_color=True)
    assert re.sub(r"\033\[[0-9;]*m", "", marked) == document.text


def test_format_summary_lists_fields_and_totals(extractor):
    text = format_summary(_documents(extractor), use_color=False)
    assert "Extraction summary" in text
    assert "blood_pressure" in text
    assert "a.txt" in text and "b.txt" in text
    assert "TOTAL" in text


def test_format_summary_handles_no_matches(extractor):
    documents = [extractor.extract("nothing structured here", source="empty.txt")]
    assert "no matches found" in format_summary(documents, use_color=False)
