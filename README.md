# 🏥 RegexRx

### Clinical Text Extractor — Unstructured Notes → Structured Data

<p align="center">
  <b>Extract clinical information from messy text using pure Python regex.</b>
</p>

<p align="center">

![Python](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python)
![Tests](https://img.shields.io/badge/tests-132%20passed-success?logo=pytest)
![Dependencies](https://img.shields.io/badge/dependencies-0-brightgreen)
![License](https://img.shields.io/badge/license-MIT-blue)

</p>

---

## 🧠 What is RegexRx?

RegexRx transforms **unstructured clinical notes** into structured, machine-readable records.

It can extract:

* 📅 Dates
* 👤 Ages & sex
* ❤️ Blood pressure
* 📊 Vital signs
* 🧪 Laboratory values
* 💊 Medications & dosages
* 🏷️ ICD-10 codes
* 🆔 Medical Record Numbers
* ☎️ Phone numbers
* 📧 E-mail addresses

```text
67yo M, BP 162/95 mmHg, HR 104.
glucose 212 mg/dL.
gave asa 324 mg PO.
dx code I25.10 on 3/2/2024.
```

⬇️

```json
{
  "ages": ["67 y/o male"],
  "blood_pressure": ["162/95 mmHg"],
  "vitals": ["heart_rate 104"],
  "lab_values": ["glucose 212 mg/dL"],
  "medications": ["asa 324 mg PO"],
  "icd_codes": ["I25.10"],
  "dates": ["2024-03-02"]
}
```

---

## ✨ Features

| Feature                   | Description                                        |
| ------------------------- | -------------------------------------------------- |
| 🔍 **Regex Extraction**   | Extracts 10 clinical field types                   |
| 🛡️ **Validation**        | Rejects impossible or invalid matches              |
| 🔄 **Normalization**      | Converts equivalent inputs into consistent formats |
| ⚔️ **Overlap Resolution** | Prevents conflicting matches between fields        |
| ⚙️ **Config-Driven**      | Add new patterns without changing Python code      |
| 📦 **Batch Processing**   | Process individual files or entire folders         |
| 📄 **JSON & CSV**         | Export structured records                          |
| 🎨 **Highlighting**       | Display detected matches directly in terminal      |
| 📊 **Statistics**         | Per-field match, unique and rejected counts        |
| 🧪 **132 Tests**          | Extensive automated test coverage                  |

---

## ⚡ Quick Start

```bash
git clone <your-fork-url> regexrx
cd regexrx
python src/main.py
```

Run the test suite:

```bash
python -m pytest -q
```

Expected result:

```text
132 passed
```

---

## 🚀 Usage

### Extract bundled sample notes

```bash
python src/main.py
```

### Extract a single note

```bash
python src/main.py \
  -i data/sample_notes/note_002_ed_messy.txt \
  -f json csv
```

### Process an entire folder

```bash
python src/main.py \
  -i data/sample_notes \
  --fields dates lab_values
```

### Extract directly from text

```bash
python src/main.py \
  --text "67yo M, BP 162/95 mmHg, glucose 212 mg/dL"
```

### Highlight matches

```bash
cat note.txt | python src/main.py --stdin --highlight
```

---

## 🏗️ Architecture

```text
                    ┌──────────────────────┐
                    │   Clinical Text      │
                    │  Unstructured Notes  │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │  Pattern Engine      │
                    │  config/patterns.json│
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │    Extractors        │
                    │ compile → scan       │
                    │ overlap resolution   │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │     Validators       │
                    │ normalize + validate │
                    └──────────┬───────────┘
                               │
                               ▼
              ┌─────────────────────────────────┐
              │          Reporting              │
              │      JSON / CSV / Summary      │
              └─────────────────────────────────┘
```

---

## 📊 Example Results

Across the five bundled synthetic clinical notes:

```text
Extraction summary
────────────────────────────────────────
Field                  Matches   Unique
────────────────────────────────────────
ages                       10        10
blood_pressure              9         8
dates                      26        13
emails                      6         6
icd_codes                  12        11
lab_values                 51        51
medications                29        29
mrns                        7         7
phones                      8         8
vitals                     23        21
────────────────────────────────────────
TOTAL                     181
```

The extractor also tracks **rejected candidates**, allowing you to see when a regex matched something that failed validation.

---

## 🧩 Project Structure

```text
regexrx/
│
├── ⚙️ config/
│   └── patterns.json
│
├── 🐍 src/
│   ├── main.py
│   ├── extractors.py
│   ├── validators.py
│   └── reporting.py
│
├── 📚 data/
│   ├── sample_notes/
│   └── output/
│
├── 🧪 tests/
│
├── requirements.txt
├── README.md
└── LICENSE
```

---

## 🧪 Testing

The test suite covers:

* Happy-path extraction
* Invalid dates
* Out-of-range laboratory values
* Invalid phone numbers
* ICD-10 edge cases
* Overlap resolution
* Configuration errors
* JSON/CSV output
* CLI modes

```bash
python -m pytest -q
```

---

## 🔧 Add Your Own Field

RegexRx is **configuration-driven**.

You can add a new field by editing:

```text
config/patterns.json
```

No changes to the extraction engine are required.

---

## ⚠️ Limitations

RegexRx is intentionally a **regex-based text extraction tool**, not a full clinical NLP system.

It does not reliably understand:

* Negation
* Clinical context
* Semantic meaning
* Drug identification in every sentence
* Unlisted laboratory analytes
* Non-North-American phone formats

For example:

> "Patient denies chest pain."

The extractor may still identify `chest pain` as a mention because regex alone does not understand clinical negation.

---

## 🔒 Disclaimer

All sample notes included in this project are **synthetic** and contain no real patient information.

RegexRx is an **educational text-processing project**, not a medical device. It has not been validated for clinical use and must not be used to make medical decisions.

---

## 📜 License

MIT License

