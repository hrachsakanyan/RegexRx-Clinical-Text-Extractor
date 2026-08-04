"""RegexRx command line interface.

    py src/main.py                              # extract from data/sample_notes
    py src/main.py -i note.txt --highlight      # one note, matches marked inline
    py src/main.py --text "BP 138/86, HbA1c 7.2%"
    py src/main.py -i data/sample_notes -f json csv --fields dates lab_values
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

if __package__ in (None, ""):  # allow `py src/main.py` as well as `py -m src.main`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.extractors import ConfigError, Document, Extractor, PROJECT_ROOT
from src.reporting import format_summary, highlight, legend, write_csv, write_json

DEFAULT_INPUT = PROJECT_ROOT / "data" / "sample_notes"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "output"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="regexrx",
        description="Extract structured records (dates, doses, labs, vitals, "
                    "codes, contacts) from unstructured clinical notes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "-i", "--input", type=Path,
        help=f"note file or folder of notes (default: {DEFAULT_INPUT})",
    )
    source.add_argument("--text", help="extract from this literal string")
    source.add_argument("--stdin", action="store_true", help="read the note from stdin")

    parser.add_argument(
        "-o", "--out", type=Path, default=DEFAULT_OUTPUT,
        help=f"output folder (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "-f", "--format", nargs="+", choices=["json", "csv", "none"], default=["json"],
        help="what to write to --out (default: json)",
    )
    parser.add_argument(
        "--fields", nargs="+", metavar="FIELD",
        help="only extract these fields (e.g. dates lab_values medications)",
    )
    parser.add_argument(
        "--config", type=Path,
        help="alternative pattern config (default: config/patterns.json)",
    )
    parser.add_argument(
        "--ext", nargs="+", default=[".txt", ".md", ".log"],
        help="file extensions to pick up in folder mode",
    )
    parser.add_argument(
        "--no-recursive", action="store_true", help="do not descend into sub-folders",
    )
    parser.add_argument(
        "--highlight", action="store_true", help="print each note with matches marked",
    )
    parser.add_argument(
        "--print-json", action="store_true", help="print the records to stdout",
    )
    parser.add_argument("--no-color", action="store_true", help="disable ANSI colours")
    parser.add_argument("--quiet", "-q", action="store_true", help="suppress the summary")
    parser.add_argument("--list-fields", action="store_true", help="show the configured fields and exit")
    return parser


def _use_color(args: argparse.Namespace) -> bool:
    if args.no_color or os.environ.get("NO_COLOR"):
        return False
    if not sys.stdout.isatty():
        return False
    if sys.platform == "win32":
        # Enable virtual terminal processing; older consoles print raw escapes.
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            return False
    return True


def collect_documents(args: argparse.Namespace, extractor: Extractor) -> list[Document]:
    if args.text is not None:
        return [extractor.extract(args.text, source="<text>")]
    if args.stdin:
        return [extractor.extract(sys.stdin.read(), source="<stdin>")]

    target = args.input or DEFAULT_INPUT
    if target.is_dir():
        return extractor.extract_folder(
            target, extensions=args.ext, recursive=not args.no_recursive
        )
    if target.is_file():
        return [extractor.extract_file(target)]
    raise FileNotFoundError(f"no such file or folder: {target}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        extractor = Extractor(config_path=args.config, fields=args.fields)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    if args.list_fields:
        for pattern in extractor.patterns:
            print(f"{pattern.qualified_name:<34} priority={pattern.priority:<3} {pattern.description}")
        return 0

    try:
        documents = collect_documents(args, extractor)
    except (FileNotFoundError, NotADirectoryError, OSError) as exc:
        print(f"input error: {exc}", file=sys.stderr)
        return 2

    if not documents:
        print("no input documents found (check --input / --ext)", file=sys.stderr)
        return 1

    color = _use_color(args)
    formats = set(args.format)
    written: list[Path] = []
    to_stdout = args.text is not None or args.stdin

    if "none" not in formats and not to_stdout:
        if "json" in formats:
            written += write_json(documents, args.out)
        if "csv" in formats:
            written.append(write_csv(documents, Path(args.out) / "extractions.csv"))

    if args.print_json or to_stdout:
        payload = (
            documents[0].to_dict() if len(documents) == 1
            else [d.to_dict() for d in documents]
        )
        print(json.dumps(payload, indent=2, ensure_ascii=False))

    if args.highlight:
        for document in documents:
            print(f"\n=== {document.source} ===")
            print(highlight(document, use_color=color))
        print()
        print(legend(extractor.fields, use_color=color))

    if not args.quiet:
        print()
        print(format_summary(documents, use_color=color))
        for path in written:
            print(f"  wrote {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
