"""Field-by-field behaviour of the shipped patterns and validators."""

from __future__ import annotations

import pytest


# --------------------------------------------------------------------------- #
# dates
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "text, expected",
    [
        ("Visit date: 2024-03-14", "2024-03-14"),
        ("DOB 04/17/1971", "1971-04-17"),
        ("drawn 03/09/24", "2024-03-09"),
        ("seen 12/31/99", "1999-12-31"),
        ("admitted 15 Jan 2024", "2024-01-15"),
        ("follow up 29 January 2024", "2024-01-29"),
        ("Next appointment: April 22, 2024", "2024-04-22"),
        ("d/c 3 Mar 2024", "2024-03-03"),
    ],
)
def test_dates_are_normalised_to_iso(values, text, expected):
    assert values(text, "dates") == [expected]


@pytest.mark.parametrize("text", ["note 2024-02-30", "seen 13/25/2024", "code 99/99/9999"])
def test_impossible_dates_are_rejected(values, text):
    assert values(text, "dates") == []


# --------------------------------------------------------------------------- #
# ages
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "text, expected",
    [
        ("53 y/o female here for f/u", "53 y/o female"),
        ("67yo M brought in by EMS", "67 y/o male"),
        ("A 34-year-old woman was admitted", "34 y/o female"),
        ("8 y/o boy", "8 y/o"),
        ("102 yo woman", "102 y/o female"),
    ],
)
def test_ages(values, text, expected):
    assert values(text, "ages") == [expected]


def test_impossible_age_is_rejected(values):
    assert values("200 y/o patient", "ages") == []


def test_age_without_sex_does_not_swallow_punctuation(extractor):
    match = extractor.extract("45-year-old, presenting today").matches[0]
    assert match.raw == "45-year-old"
    assert match.value == "45 y/o"


# --------------------------------------------------------------------------- #
# blood pressure
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "text, expected",
    [
        ("VITALS: BP 138/86 mmHg", "138/86 mmHg"),
        ("bp 162/95 , hr 104", "162/95 mmHg"),
        ("Blood pressure of 104/62 improved", "104/62 mmHg"),
        ("BP 138 / 86mmHg", "138/86 mmHg"),
        ("146/92 on recheck", "146/92 mmHg"),  # unlabelled but physiological
    ],
)
def test_blood_pressure(values, text, expected):
    assert values(text, "blood_pressure") == [expected]


@pytest.mark.parametrize(
    "text",
    [
        "the ratio 3/4 in the I&O section",
        "1/2 tablet in the med list",
        "Room 12/25 is a room number",
        "dated 11/15/2024",
        "reading 86/138 is inverted",
    ],
)
def test_non_bp_slashes_are_rejected(values, text):
    assert values(text, "blood_pressure") == []


def test_blood_pressure_details(extractor):
    match = extractor.extract("BP 138/86 mmHg").matches[0]
    assert match.details == {"systolic": 138, "diastolic": 86, "labelled": True}


# --------------------------------------------------------------------------- #
# vitals
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "text, expected",
    [
        ("HR 78 bpm", "heart_rate 78 bpm"),
        ("HR:78bpm", "heart_rate 78 bpm"),
        ("pulse 66", "heart_rate 66"),
        ("RR 16", "respiratory_rate 16"),
        ("Temp 98.4 F", "temperature 98.4 °F"),
        ("temp 37.1 C", "temperature 37.1 °C"),
        ("SpO2 97%", "oxygen_saturation 97 %"),
        ("oxygen saturation 89% on room air", "oxygen_saturation 89 %"),
        ("wt 91.2 kg", "weight 91.2 kg"),
        ("BMI 33.5", "bmi 33.5"),
    ],
)
def test_vitals(values, text, expected):
    assert values(text, "vitals") == [expected]


@pytest.mark.parametrize("text", ["HR 900 bpm", "RR 300", "SpO2 2%"])
def test_implausible_vitals_are_rejected(values, text):
    assert values(text, "vitals") == []


# --------------------------------------------------------------------------- #
# labs
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "text, expected",
    [
        ("HbA1c 7.8 %", "HbA1c 7.8 %"),
        ("fasting glucose 154 mg/dL", "glucose 154 mg/dL"),
        ("Na 139 mmol/L", "sodium 139 mmol/L"),
        ("hgb 13.9 g/dL", "hemoglobin 13.9 g/dL"),
        ("WBC was 18.4 K/uL", "WBC 18.4 K/uL"),
        ("hemoglobin of 11.2 g/dL", "hemoglobin 11.2 g/dL"),
        ("creatinine 0.8", "creatinine 0.8"),
        ("eGFR 68 mL/min/1.73m2", "eGFR 68 mL/min/1.73m2"),
        ("troponin I 0.42 ng/mL", "troponin I 0.42 ng/mL"),
    ],
)
def test_lab_values(values, text, expected):
    assert values(text, "lab_values") == [expected]


@pytest.mark.parametrize("text", ["Na 5000 mmol/L", "K 99", "HbA1c 87 %"])
def test_out_of_range_labs_are_rejected(values, text):
    assert values(text, "lab_values") == []


def test_lab_details_carry_the_original_label(extractor):
    match = extractor.extract("hgb 13.9 g/dL").matches[0]
    assert match.details["analyte"] == "hemoglobin"
    assert match.details["label_used"] == "hgb"
    assert match.details["value"] == 13.9


# --------------------------------------------------------------------------- #
# medications
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "text, expected",
    [
        ("Metformin 1000 mg PO BID", "Metformin 1000 mg PO BID"),
        ("metformin 500mg bid", "metformin 500 mg BID"),
        ("Atorvastatin 40 mg PO nightly", "Atorvastatin 40 mg PO QHS"),
        ("Albuterol 2 puffs inhaled q6h", "Albuterol 2 puffs inhaled q6h"),
        ("vancomycin 1.5 g IV q12h", "vancomycin 1.5 g IV q12h"),
        ("insulin glargine 24 units subq at bedtime", "insulin glargine 24 units SubQ QHS"),
        ("gave 500 mg of acetaminophen", "acetaminophen 500 mg"),
        ("Potassium chloride 20 mEq PO daily", "Potassium chloride 20 mEq PO daily"),
    ],
)
def test_medications(values, text, expected):
    assert values(text, "medications") == [expected]


@pytest.mark.parametrize(
    "text, expected_drug",
    [
        ("gave asa 324 mg PO", "asa"),
        ("then metoprolol 5 mg IV", "metoprolol"),
        ("given amlodipine 5 mg PO daily", "amlodipine"),
    ],
)
def test_leading_verbs_are_not_mistaken_for_drug_names(extractor, text, expected_drug):
    match = extractor.extract(text).matches[0]
    assert match.details["drug"] == expected_drug
    assert match.raw.startswith(expected_drug)


def test_dose_without_drug_still_recorded(extractor):
    match = extractor.extract("TAKE 2 TABLETS PO Q8H").matches[0]
    assert "drug" not in match.details
    assert match.value == "2 tablets PO q8h"


def test_lab_result_is_not_read_as_a_dose(extractor):
    document = extractor.extract("glucose 180 mg/dL and creatinine 1.2 mg/dL")
    assert document.summary() == {"lab_values": 2}


# --------------------------------------------------------------------------- #
# codes and contacts
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "text, expected",
    [
        ("ICD-10: E11.9", ["E11.9"]),
        ("dx code I25.10", ["I25.10"]),
        ("Dotted codes stand alone: M54.5, S72.001A", ["M54.5", "S72.001A"]),
        ("ICD-10 I10", ["I10"]),
        ("vitamin B12 was 410 pg/mL", []),          # unlabelled 3-char token
        ("TAKE 2 TABLETS PO Q8H", []),              # Q8H is not a diagnosis
    ],
)
def test_icd_codes(values, text, expected):
    assert values(text, "icd_codes") == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("MRN: 00841239", "00841239"),
        ("mrn# MR-7741902", "MR-7741902"),
        ("Medical Record Number: 4471028", "4471028"),
        ("Record #: 90210771", "90210771"),
    ],
)
def test_mrns(values, text, expected):
    assert values(text, "mrns") == [expected]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("ph (555) 208-4417 ext 22", "(555) 208-4417 x22"),
        ("cell +1 555.311.7788", "(555) 311-7788"),
        ("son -- 5553119042", "(555) 311-9042"),
        ("nurse line: 555.774.1911", "(555) 774-1911"),
    ],
)
def test_phones(values, text, expected):
    assert values(text, "phones") == [expected]


@pytest.mark.parametrize("text", ["fax 555 000 1234", "call 155 123 4567"])
def test_invalid_phone_numbers_are_rejected(values, text):
    assert values(text, "phones") == []


@pytest.mark.parametrize(
    "text, expected",
    [
        ("email a.patel@riverbend-clinic.example", ["a.patel@riverbend-clinic.example"]),
        ("portal: jane.doe+labs@example.org", ["jane.doe+labs@example.org"]),
        ("MIXED.Case@Example.COM", ["mixed.case@example.com"]),
        ("broken not..valid@@example.com", []),
    ],
)
def test_emails(values, text, expected):
    assert values(text, "emails") == expected
