"""Engine-level behaviour: config loading, normalisation, overlaps, batching."""

from __future__ import annotations

import json

import pytest

from src.extractors import (
    ConfigError,
    Extractor,
    Match,
    extract_text,
    load_patterns,
    normalize_text,
    resolve_overlaps,
)


# --------------------------------------------------------------------------- #
# config
# --------------------------------------------------------------------------- #

def test_default_config_compiles():
    patterns = load_patterns()
    assert patterns
    assert {p.field for p in patterns} >= {
        "dates", "ages", "blood_pressure", "vitals", "lab_values",
        "medications", "icd_codes", "mrns", "phones", "emails",
    }


def test_fields_filter_limits_the_engine():
    extractor = Extractor(fields=["dates", "emails"])
    assert set(extractor.fields) == {"dates", "emails"}
    document = extractor.extract("BP 138/86 on 2024-03-14, mail me@x.example")
    assert document.summary() == {"dates": 1, "emails": 1}


def test_unknown_field_raises():
    with pytest.raises(ConfigError, match="unknown field"):
        Extractor(fields=["blood_type"])


def test_missing_config_raises(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_patterns(tmp_path / "nope.json")


def test_broken_regex_in_config_raises(tmp_path):
    path = tmp_path / "patterns.json"
    path.write_text(json.dumps({
        "fields": [{"name": "x", "patterns": [{"name": "bad", "regex": "([unclosed"}]}]
    }), encoding="utf-8")
    with pytest.raises(ConfigError, match="invalid regex"):
        load_patterns(path)


def test_unknown_validator_raises(tmp_path):
    path = tmp_path / "patterns.json"
    path.write_text(json.dumps({
        "fields": [{
            "name": "x", "validator": "does_not_exist",
            "patterns": [{"name": "p", "regex": "x"}],
        }]
    }), encoding="utf-8")
    with pytest.raises(ConfigError, match="unknown validator"):
        load_patterns(path)


def test_custom_config_can_add_a_field(tmp_path):
    path = tmp_path / "patterns.json"
    path.write_text(json.dumps({
        "fields": [{
            "name": "room_numbers",
            "priority": 10,
            "patterns": [{"name": "room", "regex": r"\bRoom\s+(?P<room>\d{3})\b", "flags": ["IGNORECASE"]}],
        }]
    }), encoding="utf-8")
    document = Extractor(config_path=path).extract("seen in room 412 today")
    assert document.values("room_numbers") == ["room 412"]
    assert document.matches[0].details == {"room": "412"}


# --------------------------------------------------------------------------- #
# messy text handling
# --------------------------------------------------------------------------- #

def test_normalize_text_folds_messy_characters():
    messy = "BP 138/86\r\nHbA1c–7.8’s   value"
    clean = normalize_text(messy)
    assert " " not in clean and "\r" not in clean
    assert "-7.8's value" in clean
    assert clean.count("\n") == 1


def test_extraction_survives_messy_whitespace(extractor):
    document = extractor.extract("VITALS:\tBP   138/86  mmHg\r\n\tHR\t78 bpm")
    assert document.values("blood_pressure") == ["138/86 mmHg"]
    assert document.values("vitals") == ["heart_rate 78 bpm"]


def test_line_numbers_and_spans(extractor):
    document = extractor.extract("line one\nMRN: 12345678\nBP 120/80")
    lines = {m.field: m.line for m in document.matches}
    assert lines == {"mrns": 2, "blood_pressure": 3}
    match = document.matches[0]
    assert document.text[match.start:match.end] == match.raw


def test_context_snippet_is_single_line(extractor):
    document = extractor.extract("first line\nHbA1c 7.2 %\nthird line")
    assert "\n" not in document.matches[0].context


# --------------------------------------------------------------------------- #
# overlap resolution
# --------------------------------------------------------------------------- #

def _match(field: str, start: int, end: int) -> Match:
    return Match(field, f"{field}.p", "v", "raw", start, end, 1, "ctx")


def test_resolve_overlaps_prefers_higher_priority():
    kept = resolve_overlaps(
        [_match("lab_values", 0, 10), _match("medications", 4, 10)],
        {"lab_values": 65, "medications": 50},
    )
    assert [m.field for m in kept] == ["lab_values"]


def test_resolve_overlaps_prefers_longer_span_within_a_field():
    kept = resolve_overlaps(
        [_match("dates", 0, 4), _match("dates", 0, 10)],
        {"dates": 70},
    )
    assert [(m.start, m.end) for m in kept] == [(0, 10)]


def test_resolve_overlaps_keeps_disjoint_matches():
    kept = resolve_overlaps(
        [_match("dates", 0, 5), _match("emails", 6, 20)],
        {"dates": 70, "emails": 95},
    )
    assert len(kept) == 2


def test_conflict_resolution_can_be_disabled():
    text = "vitamin D 2000 units daily"  # reads as both a lab result and a dose
    assert Extractor().extract(text).summary() == {"lab_values": 1}
    assert Extractor(resolve_conflicts=False).extract(text).summary() == {
        "lab_values": 1, "medications": 1,
    }


# --------------------------------------------------------------------------- #
# documents, summaries, batching
# --------------------------------------------------------------------------- #

def test_summary_counts_every_field(extractor):
    text = "53 y/o female, BP 138/86, HbA1c 7.8 %, Metformin 1000 mg PO BID on 2024-03-14"
    summary = extractor.extract(text).summary()
    assert summary == {
        "ages": 1, "blood_pressure": 1, "dates": 1,
        "lab_values": 1, "medications": 1,
    }


def test_rejected_hits_are_counted_not_exported(extractor):
    document = extractor.extract("Na 5000 mmol/L")
    assert document.matches == []
    assert document.rejected["lab_values"] == 1


def test_document_to_dict_is_json_serialisable(extractor):
    payload = extractor.extract("BP 138/86 mmHg", source="demo.txt").to_dict()
    assert payload["source"] == "demo.txt"
    assert payload["total_matches"] == 1
    assert payload["extracted"]["blood_pressure"][0]["value"] == "138/86 mmHg"
    json.dumps(payload)  # must not raise


def test_extract_text_helper():
    payload = extract_text("HbA1c 7.2 %")
    assert payload["summary"] == {"lab_values": 1}


def test_extract_folder_reads_every_sample_note(extractor, sample_notes):
    documents = extractor.extract_folder(sample_notes)
    assert len(documents) == 5
    assert [d.source for d in documents] == sorted(d.source for d in documents)
    assert all(d.matches for d in documents)


def test_extract_folder_respects_extensions(extractor, sample_notes):
    documents = extractor.extract_folder(sample_notes, extensions=[".log"])
    assert [d.source for d in documents] == ["triage_log.log"]


def test_extract_folder_rejects_a_file(extractor, sample_notes):
    with pytest.raises(NotADirectoryError):
        extractor.extract_folder(sample_notes / "note_001_clinic.txt")
