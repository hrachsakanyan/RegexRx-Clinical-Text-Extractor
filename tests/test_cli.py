"""End-to-end behaviour of `py src/main.py`."""

from __future__ import annotations

import json

from src.main import main

NOTE = "MRN: 12345678\n53 y/o female, BP 138/86 mmHg, HbA1c 7.8 % on 2024-03-14"


def test_text_mode_prints_json(capsys):
    assert main(["--text", NOTE, "--quiet"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["source"] == "<text>"
    assert payload["summary"]["blood_pressure"] == 1


def test_text_mode_writes_nothing(tmp_path, capsys):
    main(["--text", NOTE, "--out", str(tmp_path), "--quiet"])
    capsys.readouterr()
    assert list(tmp_path.iterdir()) == []


def test_file_mode_writes_json_and_summary(tmp_path, sample_notes, capsys):
    note = sample_notes / "note_001_clinic.txt"
    assert main(["-i", str(note), "-o", str(tmp_path), "--no-color"]) == 0
    out = capsys.readouterr().out

    assert (tmp_path / "note_001_clinic.json").exists()
    assert (tmp_path / "summary.json").exists()
    assert "Extraction summary" in out
    payload = json.loads((tmp_path / "note_001_clinic.json").read_text(encoding="utf-8"))
    assert payload["total_matches"] > 20


def test_folder_mode_with_csv(tmp_path, sample_notes, capsys):
    code = main(["-i", str(sample_notes), "-o", str(tmp_path), "-f", "json", "csv", "-q"])
    capsys.readouterr()
    assert code == 0

    csv_path = tmp_path / "extractions.csv"
    assert csv_path.exists()
    rows = csv_path.read_text(encoding="utf-8").splitlines()
    assert len(rows) > 100  # header + one row per match

    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["documents"] == 5
    assert summary["total_matches"] == sum(summary["matches_by_field"].values())


def test_fields_filter(tmp_path, sample_notes, capsys):
    main(["-i", str(sample_notes), "-o", str(tmp_path), "--fields", "dates", "-q"])
    capsys.readouterr()
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert set(summary["matches_by_field"]) == {"dates"}


def test_format_none_writes_nothing(tmp_path, sample_notes, capsys):
    main(["-i", str(sample_notes), "-o", str(tmp_path), "-f", "none", "-q"])
    capsys.readouterr()
    assert not tmp_path.exists() or list(tmp_path.iterdir()) == []


def test_highlight_marks_matches(capsys):
    main(["--text", "BP 138/86 mmHg", "--highlight", "--no-color", "-q", "--format", "none"])
    out = capsys.readouterr().out
    assert "[blood_pressure: BP 138/86 mmHg]" in out
    assert "legend:" in out


def test_list_fields(capsys):
    assert main(["--list-fields"]) == 0
    out = capsys.readouterr().out
    assert "blood_pressure.systolic_diastolic" in out
    assert "priority=" in out


def test_missing_input_returns_error_code(tmp_path, capsys):
    assert main(["-i", str(tmp_path / "nope.txt")]) == 2
    assert "input error" in capsys.readouterr().err


def test_unknown_field_returns_config_error(capsys):
    assert main(["--fields", "horoscope"]) == 2
    assert "config error" in capsys.readouterr().err


def test_empty_folder_returns_one(tmp_path, capsys):
    (tmp_path / "in").mkdir()
    assert main(["-i", str(tmp_path / "in"), "-o", str(tmp_path / "out")]) == 1
    assert "no input documents" in capsys.readouterr().err


def test_stdin_mode(monkeypatch, capsys):
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO("HbA1c 7.2 % on 2024-01-05"))
    assert main(["--stdin", "-q"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["source"] == "<stdin>"
    assert payload["summary"] == {"dates": 1, "lab_values": 1}
