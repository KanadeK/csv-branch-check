from __future__ import annotations

import argparse
import json
import sys

from . import __version__
from .core import validate
from .rules import RuleError, load_rules


def positive(text: str) -> int:
    try:
        value = int(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Expected positive integer") from exc
    if value < 1:
        raise argparse.ArgumentTypeError("Expected positive integer")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check CSV conditional rules without exposing cells"
    )
    parser.add_argument("csv", help="UTF-8 CSV filename")
    parser.add_argument("--rules", required=True, help="Version 1 JSON rulebook")
    parser.add_argument("--version", action="version", version=f"csv-branch-check {__version__}")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--delimiter", choices=["comma", "tab", "semicolon", "pipe"], default="comma"
    )
    parser.add_argument("--warnings-as-errors", action="store_true")
    parser.add_argument("--max-findings", type=positive, default=1000)
    parser.add_argument("--max-rows", type=positive, default=1_000_000)
    parser.add_argument("--max-bytes", type=positive, default=250_000_000)
    args = parser.parse_args(argv)
    try:
        result = validate(
            args.csv,
            load_rules(args.rules),
            delimiter={"comma": ",", "tab": "\t", "semicolon": ";", "pipe": "|"}[args.delimiter],
            max_findings=args.max_findings,
            max_rows=args.max_rows,
            max_bytes=args.max_bytes,
            warnings_as_errors=args.warnings_as_errors,
        )
    except RuleError as exc:
        error = {"ok": False, "kind": "configuration-error", "message": str(exc)}
        print(json.dumps(error), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, ensure_ascii=True, indent=2))
    else:
        print(
            f"{'OK' if result['ok'] else 'FAIL'}: {result['records_read']} records; "
            f"{result['error_count']} errors; {result['warning_count']} warnings"
        )
        for finding in result["findings"]:
            print(json.dumps(finding, ensure_ascii=True))
        if result["findings_truncated"]:
            print("Additional findings omitted; counts include all checked records")
    return 0 if result["ok"] else 1
