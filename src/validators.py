"""Validation and normalisation of raw regex hits.

A regex says "this *looks* like a blood pressure"; a validator decides whether
it really is one and turns it into a canonical value.  Every validator takes the
match's named groups plus the raw matched text and returns either

    (value, details)   -> accepted, `value` is the canonical scalar
    None               -> rejected, the hit is counted but not exported

Validators are looked up by the ``validator`` key of a field in
``config/patterns.json``.
"""

from __future__ import annotations

from datetime import date as _date
from typing import Callable, Optional

Groups = dict[str, Optional[str]]
Result = Optional[tuple[str, dict[str, object]]]

VALIDATORS: dict[str, Callable[[Groups, str], Result]] = {}


def validator(name: str) -> Callable[[Callable[[Groups, str], Result]], Callable[[Groups, str], Result]]:
    """Register a validator under the name used in the pattern config."""

    def register(func: Callable[[Groups, str], Result]) -> Callable[[Groups, str], Result]:
        VALIDATORS[name] = func
        return func

    return register


def default_validator(groups: Groups, raw: str) -> Result:
    """Fallback for fields that declare no validator: keep the raw text."""
    details = {k: v.strip() for k, v in groups.items() if v}
    return raw.strip(), details


# --------------------------------------------------------------------------- #
# dates
# --------------------------------------------------------------------------- #

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


def _expand_year(raw_year: str) -> int:
    """Two-digit years: 70-99 -> 19xx, 00-69 -> 20xx."""
    year = int(raw_year)
    if len(raw_year) <= 2:
        year += 1900 if year >= 70 else 2000
    return year


@validator("date")
def validate_date(groups: Groups, raw: str) -> Result:
    year_raw = groups.get("y")
    day_raw = groups.get("d")
    if not year_raw or not day_raw:
        return None

    month_name = groups.get("mon")
    if month_name:
        month = MONTHS.get(month_name[:3].lower())
    elif groups.get("m"):
        month = int(groups["m"])
    else:
        month = None
    if not month:
        return None

    try:
        parsed = _date(_expand_year(year_raw), month, int(day_raw))
    except ValueError:  # e.g. 02/31/2024
        return None

    return parsed.isoformat(), {
        "year": parsed.year,
        "month": parsed.month,
        "day": parsed.day,
        "iso": parsed.isoformat(),
    }


# --------------------------------------------------------------------------- #
# demographics
# --------------------------------------------------------------------------- #

SEX_MAP = {
    "m": "male", "male": "male", "man": "male",
    "f": "female", "female": "female", "woman": "female",
}


@validator("age")
def validate_age(groups: Groups, raw: str) -> Result:
    age = int(groups["age"])
    if not 0 <= age <= 120:
        return None
    details: dict[str, object] = {"age_years": age}
    sex = groups.get("sex")
    if sex:
        details["sex"] = SEX_MAP.get(sex.lower(), sex.lower())
    value = f"{age} y/o"
    if "sex" in details:
        value = f"{value} {details['sex']}"
    return value, details


# --------------------------------------------------------------------------- #
# vitals
# --------------------------------------------------------------------------- #

@validator("blood_pressure")
def validate_blood_pressure(groups: Groups, raw: str) -> Result:
    systolic, diastolic = int(groups["sys"]), int(groups["dia"])
    labelled = bool(groups.get("label") or groups.get("unit"))

    # Without a "BP"/"mmHg" anchor the reading has to stand on its own, which
    # keeps fractions and partial dates (11/15) out of the results.
    low, high = (50, 300) if labelled else (70, 260)
    if not low <= systolic <= high:
        return None
    if not (30 <= diastolic <= 200 if labelled else 30 <= diastolic <= 160):
        return None
    if diastolic >= systolic:
        return None

    return f"{systolic}/{diastolic} mmHg", {
        "systolic": systolic,
        "diastolic": diastolic,
        "labelled": labelled,
    }


VITAL_NAMES = {
    "hr": "heart_rate", "pulse": "heart_rate", "heart rate": "heart_rate",
    "rr": "respiratory_rate", "resp rate": "respiratory_rate",
    "respiratory rate": "respiratory_rate",
    "temp": "temperature", "temperature": "temperature",
    "spo2": "oxygen_saturation", "sao2": "oxygen_saturation",
    "o2 sat": "oxygen_saturation", "o2 saturation": "oxygen_saturation",
    "oxygen saturation": "oxygen_saturation",
    "weight": "weight", "wt": "weight",
    "height": "height", "bmi": "bmi",
}

VITAL_RANGES = {
    "heart_rate": (20, 250),
    "respiratory_rate": (4, 60),
    "temperature": (25, 115),       # covers both °C and °F scales
    "oxygen_saturation": (50, 100),
    "weight": (1, 700),
    "height": (30, 250),
    "bmi": (8, 100),
}


@validator("vital")
def validate_vital(groups: Groups, raw: str) -> Result:
    label = " ".join(groups["vital"].split()).lower()
    name = VITAL_NAMES.get(label)
    if name is None:
        return None

    value = float(groups["value"])
    low, high = VITAL_RANGES[name]
    if not low <= value <= high:
        return None

    unit = (groups.get("unit") or "").strip()
    unit = " ".join(unit.split()).replace("° ", "°")
    if name == "temperature" and unit in {"F", "C"}:
        unit = "°" + unit.upper()

    number = int(value) if value.is_integer() else value
    return f"{name} {number}{(' ' + unit) if unit else ''}".strip(), {
        "measure": name,
        "value": number,
        "unit": unit or None,
        "label_used": groups["vital"].strip(),
    }


# --------------------------------------------------------------------------- #
# medications
# --------------------------------------------------------------------------- #

# Words that sit in front of a dose but are not drug names.
DRUG_STOPWORDS = {
    "the", "and", "for", "with", "was", "were", "are", "has", "had", "his",
    "her", "she", "they", "take", "takes", "taking", "took", "give", "given",
    "gives", "start", "started", "starting", "stop", "stopped", "increase",
    "increased", "decrease", "decreased", "reduce", "reduced", "dose", "dosed",
    "dosing", "total", "about", "approx", "approximately", "received",
    "receives", "now", "then", "daily", "past", "last", "next", "over",
    "under", "also", "add", "added", "continue", "continued", "prescribed",
    "sig", "plus", "per", "from", "into", "onto", "still", "gave", "lost",
    "gained", "used", "using", "another", "additional", "extra", "sent",
    "home", "one", "two", "three", "four", "five", "each", "every", "about",
    "day", "days", "week", "weeks", "month", "months", "year", "years",
    "patient", "pt", "note", "plan", "gtt", "drip", "bolus", "rate",
}

UNIT_CANON = {
    "mcg": "mcg", "ug": "mcg", "mg": "mg", "g": "g", "kg": "kg",
    "meq": "mEq", "ml": "mL", "l": "L", "iu": "IU",
    "unit": "units", "units": "units",
    "tab": "tablets", "tabs": "tablets", "tablet": "tablets",
    "tablets": "tablets", "cap": "capsules", "caps": "capsules",
    "capsule": "capsules", "capsules": "capsules",
    "puff": "puffs", "puffs": "puffs", "drop": "drops", "drops": "drops",
    "patch": "patches", "patches": "patches",
}

ROUTE_CANON = {
    "po": "PO", "by mouth": "PO", "iv": "IV", "im": "IM", "subq": "SubQ",
    "sq": "SubQ", "sc": "SubQ", "sl": "SL", "pr": "PR",
    "topical": "topical", "inhaled": "inhaled", "intranasal": "intranasal",
}


def _canon_frequency(freq: str) -> str:
    squashed = " ".join(freq.split()).lower().replace(".", "")
    table = {
        "bid": "BID", "twice daily": "BID",
        "tid": "TID", "three times a day": "TID", "three times day": "TID",
        "qid": "QID", "qhs": "QHS", "at bedtime": "QHS", "nightly": "QHS",
        "qd": "daily", "q daily": "daily", "q day": "daily", "q d": "daily",
        "once daily": "daily", "daily": "daily", "weekly": "weekly",
        "prn": "PRN",
    }
    if squashed in table:
        return table[squashed]
    # q6h / q 8 hours / every 6 hours -> q6h ; q5min / every 30 minutes -> q30min
    digits = "".join(ch for ch in squashed if ch.isdigit())
    if digits and "min" in squashed:
        return f"q{digits}min"
    if digits and "h" in squashed:
        return f"q{digits}h"
    return squashed


def _clean_drug_name(candidate: str | None) -> str:
    """Keep the drug words in front of a dose and drop the sentence around them.

    "gave asa 324 mg" -> "asa";  "Potassium chloride 20 mEq" -> "Potassium chloride".
    """
    words = (candidate or "").split()
    while words and words[0].lower() in DRUG_STOPWORDS:
        words.pop(0)
    name = " ".join(words)
    return name if len(name) >= 3 else ""


@validator("medication")
def validate_medication(groups: Groups, raw: str) -> Result:
    amount = float(groups["amount"])
    if amount <= 0 or amount > 100000:
        return None

    unit = UNIT_CANON.get(groups["unit"].lower(), groups["unit"])
    drug = _clean_drug_name(groups.get("drug"))

    number = int(amount) if amount.is_integer() else amount
    details: dict[str, object] = {"amount": number, "unit": unit}
    parts = [f"{number} {unit}"]
    if drug:
        details["drug"] = drug
        parts.insert(0, drug)
    if groups.get("route"):
        route = ROUTE_CANON.get(" ".join(groups["route"].split()).lower(), groups["route"])
        details["route"] = route
        parts.append(route)
    if groups.get("freq"):
        frequency = _canon_frequency(groups["freq"])
        details["frequency"] = frequency
        parts.append(frequency)

    return " ".join(parts), details


# --------------------------------------------------------------------------- #
# labs
# --------------------------------------------------------------------------- #

ANALYTE_CANON = {
    "a1c": "HbA1c", "hba1c": "HbA1c", "hb a1c": "HbA1c",
    "hemoglobin a1c": "HbA1c",
    "glucose": "glucose", "fasting glucose": "glucose",
    "bun": "BUN", "creatinine": "creatinine", "cr": "creatinine",
    "egfr": "eGFR", "sodium": "sodium", "na": "sodium",
    "potassium": "potassium", "k": "potassium",
    "chloride": "chloride", "cl": "chloride",
    "bicarbonate": "bicarbonate", "bicarb": "bicarbonate", "co2": "bicarbonate",
    "calcium": "calcium", "ca": "calcium",
    "magnesium": "magnesium", "mg": "magnesium",
    "phosphorus": "phosphorus", "phos": "phosphorus",
    "hemoglobin": "hemoglobin", "hgb": "hemoglobin", "hb": "hemoglobin",
    "hematocrit": "hematocrit", "hct": "hematocrit",
    "platelets": "platelets", "platelet": "platelets", "plt": "platelets",
    "wbc": "WBC", "rbc": "RBC", "mcv": "MCV", "inr": "INR",
    "pt": "PT", "ptt": "PTT", "ast": "AST", "alt": "ALT",
    "alp": "ALP", "alk phos": "ALP",
    "bilirubin": "bilirubin", "total bilirubin": "bilirubin",
    "albumin": "albumin",
    "ldl": "LDL", "ldl-c": "LDL", "hdl": "HDL", "hdl-c": "HDL",
    "triglycerides": "triglycerides",
    "cholesterol": "cholesterol", "total cholesterol": "cholesterol",
    "tsh": "TSH", "free t4": "free T4", "t4": "T4",
    "crp": "CRP", "esr": "ESR",
    "troponin": "troponin", "troponin i": "troponin I", "troponin t": "troponin T",
    "bnp": "BNP", "nt-probnp": "NT-proBNP", "lactate": "lactate",
    "ferritin": "ferritin", "vitamin d": "vitamin D", "vit d": "vitamin D",
    "b12": "vitamin B12", "folate": "folate", "psa": "PSA",
}

# Physiologically possible bounds - a sanity filter, not a reference range.
ANALYTE_BOUNDS = {
    "HbA1c": (2.0, 20.0),
    "glucose": (10, 2000),
    "sodium": (90, 200),
    "potassium": (1.0, 10.0),
    "chloride": (60, 140),
    "bicarbonate": (5, 50),
    "creatinine": (0.1, 25.0),
    "BUN": (1, 300),
    "eGFR": (1, 200),
    "hemoglobin": (2.0, 25.0),
    "hematocrit": (5, 75),
    "platelets": (1, 2000),
    "WBC": (0.1, 500),
    "INR": (0.5, 12.0),
    "TSH": (0.01, 200),
    "LDL": (5, 600),
    "HDL": (5, 200),
    "cholesterol": (50, 800),
    "triglycerides": (10, 5000),
}


@validator("lab")
def validate_lab(groups: Groups, raw: str) -> Result:
    label = " ".join(groups["analyte"].split()).lower()
    analyte = ANALYTE_CANON.get(label)
    if analyte is None:
        return None

    value = float(groups["value"])
    low, high = ANALYTE_BOUNDS.get(analyte, (0, float("inf")))
    if not low <= value <= high:
        return None

    unit = (groups.get("unit") or "").strip()
    number = int(value) if value.is_integer() and "." not in groups["value"] else value
    return f"{analyte} {number}{(' ' + unit) if unit else ''}".strip(), {
        "analyte": analyte,
        "value": number,
        "unit": unit or None,
        "label_used": groups["analyte"].strip(),
    }


# --------------------------------------------------------------------------- #
# identifiers
# --------------------------------------------------------------------------- #

@validator("icd")
def validate_icd(groups: Groups, raw: str) -> Result:
    code = groups["code"]
    labelled = bool(groups.get("label"))

    # Unlabelled three-character codes (I10, B12, A1C...) are indistinguishable
    # from ordinary abbreviations, so only the dotted form is accepted there.
    if not labelled and "." not in code:
        return None

    details: dict[str, object] = {"code": code, "category": code.split(".")[0]}
    if "." in code:
        details["subcode"] = code.split(".", 1)[1]
    if labelled:
        details["label"] = " ".join(groups["label"].split())
    return code, details


@validator("mrn")
def validate_mrn(groups: Groups, raw: str) -> Result:
    mrn = groups["mrn"].upper()
    digits = "".join(ch for ch in mrn if ch.isdigit())
    if not 5 <= len(digits) <= 10:
        return None
    return mrn, {"mrn": mrn, "digits": len(digits)}


@validator("phone")
def validate_phone(groups: Groups, raw: str) -> Result:
    area = groups.get("area_paren") or groups.get("area") or ""
    digits = f"{area}{groups['prefix']}{groups['line']}"
    if len(digits) != 10:
        return None
    # NANP: area and exchange codes never start with 0 or 1.
    if digits[0] in "01" or digits[3] in "01":
        return None

    value = f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    details: dict[str, object] = {"digits": digits, "e164": f"+1{digits}"}
    if groups.get("ext"):
        details["extension"] = groups["ext"]
        value = f"{value} x{groups['ext']}"
    return value, details


@validator("email")
def validate_email(groups: Groups, raw: str) -> Result:
    address = raw.strip().strip(".,;:")
    local, _, domain = address.partition("@")
    if not local or domain.count(".") < 1 or ".." in address:
        return None
    return address.lower(), {
        "local_part": local.lower(),
        "domain": domain.lower(),
    }
