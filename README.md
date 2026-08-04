# RegexRx — Clinical Text Extractor

Turn unstructured clinical notes (or logs) into structured records with nothing but
Python's `re` module.

RegexRx reads messy free text — an ED note dictated at 2 a.m., a discharge summary,
a triage log — and pulls out **dates, ages, blood pressures, vitals, lab values,
drug doses, ICD-10 codes, MRNs, phone numbers and e-mail addresses** as JSON or CSV,
with per-field match counts.

```
raw note                            structured record
─────────────────────────────       ─────────────────────────────────────────────
67yo M, BP 162/95 mmHg, HR 104.  →  ages           67 y/o male
glucose 212 mg/dL.                  blood_pressure 162/95 mmHg  {sys:162, dia:95}
gave asa 324 mg PO.                 vitals         heart_rate 104
dx code I25.10 on 3/2/2024.         lab_values     glucose 212 mg/dL
                                    medications    asa 324 mg PO
                                    icd_codes      I25.10  {category:I25}
                                    dates          2024-03-02
```

Zero third-party dependencies — the standard library only (`re`, `json`, `csv`, `argparse`).

---

## Extracted fields

| Field | Catches | Example input | Structured output | Core of the pattern |
|---|---|---|---|---|
| `dates` | ISO, US-numeric, written | `04/17/1971`, `3 Mar 2024`, `April 22, 2024` | `1971-04-17` | `(?P<m>1[0-2]\|0?[1-9])[/-](?P<d>3[01]\|[12]\d\|0?[1-9])[/-](?P<y>\d{4}\|\d{2})` |
| `ages` | age + sex | `67yo M`, `34-year-old woman` | `67 y/o male` | `(?P<age>\d{1,3})[ -]*(?:y\.o\.\|y/o\|yo\|year[s]?[ -]?old)` |
| `blood_pressure` | systolic/diastolic | `BP 138 / 86mmHg` | `138/86 mmHg` | `(?<![\d/.])(?P<sys>\d{2,3})\s*/\s*(?P<dia>\d{2,3})(?![\d/])` |
| `vitals` | HR, RR, temp, SpO2, wt, ht, BMI | `HR:78bpm`, `temp 37.1 C` | `heart_rate 78 bpm` | `(?P<vital>HR\|pulse\|RR\|temp…)\s*[:=]?\s*(?P<value>\d{1,3}(?:\.\d+)?)` |
| `lab_values` | 60+ named analytes | `hgb 13.9 g/dL`, `WBC was 18.4 K/uL` | `hemoglobin 13.9 g/dL` | `(?P<analyte>hba1c\|glucose\|Na\|K…)\b…(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>%\|mg/dL…)?` |
| `medications` | drug + dose + route + frequency | `metformin 500mg bid` | `metformin 500 mg BID` | `(?P<drug>…)?(?P<amount>\d+(?:\.\d+)?)\s*(?P<unit>mcg\|mg\|g\|mL…)(?!\s*/)` |
| `icd_codes` | ICD-10-CM style codes | `dx code I25.10`, `M54.5` | `I25.10` | `(?P<code>[A-TV-Z][0-9][0-9A-Z](?:\.[0-9A-Z]{1,4})?)` |
| `mrns` | labelled record numbers | `mrn# MR-7741902` | `MR-7741902` | `\b(?:MRN\|medical\s+record\s+(?:number\|no\.?))\s*[:#=]?\s*(?P<mrn>…)` |
| `phones` | NANP numbers + extension | `+1 555.311.7788`, `(555) 208-4417 ext 22` | `(555) 311-7788` | `(?:\((?P<area_paren>\d{3})\)\|(?P<area>\d{3}))[ .-]*(?P<prefix>\d{3})[ .-]*(?P<line>\d{4})` |
| `emails` | addresses | `jane.doe+labs@example.org` | `jane.doe+labs@example.org` | `[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}` |

Every pattern lives in [config/patterns.json](config/patterns.json) — no regex is hard-coded in the Python.

---

## Features

- **Ten field types, fourteen named patterns**, each with groups, alternation, anchors and lookarounds.
- **Structured output** — `dict` → JSON per note, plus a corpus-wide `summary.json`.
- **Validation, not just matching.** A regex only proposes; a validator in
  [src/validators.py](src/validators.py) decides. `2024-02-30` is dropped (no such day),
  `Na 5000` is dropped (out of physiological range), `12/25` is a room number and not a
  blood pressure, `555 000 1234` is not a valid phone number.
- **Normalisation.** `hgb`, `Hgb` and `hemoglobin` all become `hemoglobin`; `nightly`
  and `QHS` both become `QHS`; every date becomes ISO-8601.
- **Messy-text handling** — CRLF, tabs, non-breaking spaces, smart quotes, en/em dashes,
  missing spaces (`500mg`), missing units, ALL CAPS, values wrapped across lines.
- **Summary counts** per field, per document, plus unique values and how many candidate
  hits each field *rejected*.
- **Overlap resolution** — `glucose 180 mg/dL` is one lab value, not a lab value plus a
  `180 mg` dose. Fields carry a priority; the strongest match wins the span.
- **Config-driven patterns** — add a field by editing JSON, no code change ([example](#adding-your-own-field)).
- **CSV export** for spreadsheets, **batch folder processing**, and **match highlighting**
  in the terminal.

---

## Install

```bash
git clone <your-fork-url> regexrx
cd regexrx
pip install -r requirements.txt   # only needed to run the tests
```

Python 3.9+ (developed on 3.11). On Windows use `py` instead of `python`.

## Usage

```bash
# Extract from the bundled sample notes -> data/output/*.json + summary.json
python src/main.py

# One note, JSON + CSV
python src/main.py -i data/sample_notes/note_002_ed_messy.txt -f json csv

# A whole folder of notes (batch mode), only two fields
python src/main.py -i data/sample_notes --fields dates lab_values

# Ad-hoc string, records straight to stdout
python src/main.py --text "67yo M, BP 162/95 mmHg, glucose 212 mg/dL"

# Pipe a note in, see every match highlighted in place
cat note.txt | python src/main.py --stdin --highlight

# What can it extract?
python src/main.py --list-fields
```

| Flag | Meaning |
|---|---|
| `-i, --input` | file or folder (default `data/sample_notes`) |
| `--text` / `--stdin` | extract from a literal string / stdin instead |
| `-o, --out` | output folder (default `data/output`) |
| `-f, --format` | `json`, `csv`, `none` (repeatable) |
| `--fields` | restrict to given fields |
| `--config` | use a different pattern file |
| `--ext`, `--no-recursive` | which files to pick up in folder mode |
| `--highlight`, `--no-color` | print each note with matches marked |
| `--print-json`, `-q/--quiet` | records to stdout / suppress the summary |

### As a library

```python
from src.extractors import Extractor

extractor = Extractor()
doc = extractor.extract("Metformin 1000 mg PO BID started 2024-03-14")

doc.summary()               # {'dates': 1, 'medications': 1}
doc.values("medications")   # ['Metformin 1000 mg PO BID']
doc.to_dict()               # full JSON-ready record
extractor.extract_folder("data/sample_notes")   # batch
```

---

## Input / output example

Input (`data/sample_notes/note_002_ed_messy.txt`, deliberately unpolished):

```text
67yo M brought in by EMS c/o chest pressure x 2 hrs, started ~19:30. hx of CAD, dx code I25.10,
triage vitals ..... bp 162/95 , hr 104, rr 22, temp 37.1 C, spo2 94% on RA
 troponin I 0.42 ng/mL --> repeat troponin 0.61 ng/mL at 23:10
gave asa 324 mg PO, nitroglycerin 0.4 mg SL q5min x3, heparin 4000 units IV bolus,
```

Output (`data/output/note_002_ed_messy.json`, trimmed):

```json
{
  "source": "note_002_ed_messy.txt",
  "total_matches": 33,
  "summary": {
    "ages": 1, "blood_pressure": 2, "dates": 3, "emails": 1, "icd_codes": 3,
    "lab_values": 11, "medications": 5, "mrns": 1, "phones": 2, "vitals": 4
  },
  "rejected": {},
  "extracted": {
    "blood_pressure": [
      {
        "value": "162/95 mmHg",
        "raw": "bp 162/95",
        "line": 7,
        "start": 271,
        "end": 281,
        "pattern": "blood_pressure.systolic_diastolic",
        "context": "...triage vitals ..... bp 162/95 , hr 104, rr 22...",
        "details": { "systolic": 162, "diastolic": 95, "labelled": true }
      }
    ],
    "medications": [
      {
        "value": "nitroglycerin 0.4 mg SL q5min",
        "raw": "nitroglycerin 0.4 mg SL q5min",
        "line": 19,
        "pattern": "medications.drug_dose",
        "details": {
          "amount": 0.4, "unit": "mg", "drug": "nitroglycerin",
          "route": "SL", "frequency": "q5min"
        }
      }
    ]
  }
}
```

CSV (`data/output/extractions.csv`):

```csv
source,field,value,raw,line,start,end,pattern,details
note_001_clinic.txt,mrns,00841239,MRN: 00841239,4,140,153,mrns.labelled_mrn,mrn=00841239; digits=8
note_001_clinic.txt,dates,1971-04-17,04/17/1971,5,158,168,dates.numeric_us,year=1971; month=4; day=17; iso=1971-04-17
note_001_clinic.txt,phones,(555) 208-4417 x22,(555) 208-4417 ext 22,6,221,242,phones.na_phone,digits=5552084417; e164=+15552084417; extension=22
```

Terminal summary over the five bundled notes:

```text
Extraction summary
  field            matches  unique  rejected
  ------------------------------------------
  ages                  10      10         1
  blood_pressure         9       8         1
  dates                 26      13         1
  emails                 6       6         0
  icd_codes             12      11         4
  lab_values            51      51         3
  medications           29      29         0
  mrns                   7       7         0
  phones                 8       8         1
  vitals                23      21         1
  ------------------------------------------
  TOTAL                181
```

The `rejected` column is the interesting one: those are candidate matches the regex found
and the validators threw away.

---

## Adding your own field

No Python needed — append to `config/patterns.json`:

```json
{
  "name": "room_numbers",
  "description": "Inpatient room numbers",
  "priority": 10,
  "patterns": [
    { "name": "room", "regex": "\\bRoom\\s+(?P<room>\\d{3})\\b", "flags": ["IGNORECASE"] }
  ]
}
```

```bash
python src/main.py --text "seen in room 412 today" --fields room_numbers
```

Named groups end up in the record's `details`. To normalise or range-check the value,
register a validator in `src/validators.py` and name it in the `"validator"` key:

```python
@validator("room")
def validate_room(groups, raw):
    number = int(groups["room"])
    return (f"room {number}", {"floor": number // 100}) if 100 <= number <= 999 else None
```

---

## Project layout

```text
regexrx/
├── config/
│   └── patterns.json          # every regex lives here
├── src/
│   ├── main.py                # CLI
│   ├── extractors.py          # engine: compile, scan, resolve overlaps, batch
│   ├── validators.py          # normalise + sanity-check each hit
│   └── reporting.py           # JSON / CSV / summary / highlighting
├── data/
│   ├── sample_notes/          # 5 synthetic notes, incl. an edge-case torture test
│   └── output/                # generated records (git-ignored)
├── tests/                     # 132 tests
├── requirements.txt
└── README.md
```

## Tests

```bash
python -m pytest -q      # 132 passed
```

The suite covers each field's happy path, the rejections (impossible dates, out-of-range
labs, fake phone numbers, `Q8H` is not a diagnosis code), config loading errors,
overlap resolution, JSON/CSV writers and every CLI mode.

## Known limitations

Regex is a scalpel, not a parser. Deliberate trade-offs:

- **Unlabelled three-character ICD codes are skipped** (`I10` on its own is indistinguishable
  from an abbreviation). Write `ICD-10 I10` or use the dotted form and it is captured.
- **Negation and context are invisible to it.** "denies chest pain, no metformin" still
  yields `metformin` if a dose follows; the extractor reports mentions, not clinical truth.
- **Drug names are guessed positionally** — the word(s) in front of the dose, minus a
  stopword list. A sentence like "she drank 500 mL of water" yields `water 500 mL`.
- **Analytes come from a fixed list**; an unlisted lab is not found. Add it to
  `config/patterns.json`.
- **Phone numbers assume North-American formats.**
- No de-duplication across a note: the same value mentioned twice is two matches
  (`unique` in the summary tells you how many distinct values there were).

## Disclaimer

Every note in `data/sample_notes/` is **synthetic** — written for this project, containing
no real patient data, no real people, no real phone numbers (all use the reserved `555`
exchange and `.example` domains).

RegexRx is an **educational text-processing exercise**, not a medical device. It is not
validated for clinical use, must not be used to make care decisions, and is not
HIPAA/GDPR-compliant tooling. If you point it at real records you are responsible for
de-identification, storage and every applicable regulation.

## License

MIT — see [LICENSE](LICENSE).
