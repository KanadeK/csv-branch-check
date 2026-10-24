"""Streaming CSV checks with bounded findings and no source cell excerpts."""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any

from .rules import RuleBook, RuleError, parse_rules


class InputLimit(ValueError):
    pass


class BoundedInput(io.RawIOBase):
    def __init__(self, source, limit: int):
        self.source = source
        self.remaining = limit

    def readable(self) -> bool:
        return True

    def readinto(self, buffer) -> int:
        chunk = self.source.read(min(len(buffer), self.remaining + 1))
        if len(chunk) > self.remaining:
            raise InputLimit("CSV byte limit exceeded")
        self.remaining -= len(chunk)
        buffer[: len(chunk)] = chunk
        return len(chunk)


def validate(
    path: str | Path,
    rulebook: RuleBook | dict[str, Any],
    *,
    delimiter: str = ",",
    max_findings: int = 1000,
    max_rows: int = 1_000_000,
    max_bytes: int = 250_000_000,
    warnings_as_errors: bool = False,
) -> dict[str, Any]:
    """Validate UTF-8 CSV. A nonempty header and at least one data record are required.

    Rules operate on exact strings without implicit trimming or type coercion.
    Structural input errors are findings; invalid rules/options raise RuleError.
    max_findings bounds storage only; validation continues to count every error.
    """
    book = rulebook if isinstance(rulebook, RuleBook) else parse_rules(rulebook)
    if not isinstance(delimiter, str) or len(delimiter) != 1 or delimiter in '\r\n\0"':
        raise RuleError("Delimiter must be one character other than newline, NUL or quote")
    for limit in (max_findings, max_rows, max_bytes):
        if type(limit) is not int or limit < 1:
            raise RuleError("Resource limits must be positive integers")
    findings = []
    errors = warnings = records = 0
    complete = False
    outcomes = [
        {"id": rule.id, "severity": rule.severity, "evaluated": 0, "failed": 0}
        for rule in book.rules
    ]

    def add(code: str, severity: str = "error", **location: Any) -> None:
        nonlocal errors, warnings
        if severity == "error":
            errors += 1
        else:
            warnings += 1
        if len(findings) < max_findings:
            findings.append({"code": code, "severity": severity, **location})

    source = Path(path)
    try:
        if not source.is_file():
            raise OSError("Expected a regular CSV file")
        with (
            source.open("rb") as raw,
            io.TextIOWrapper(
                io.BufferedReader(BoundedInput(raw, max_bytes)), encoding="utf-8-sig", newline=""
            ) as text,
        ):
            reader = csv.reader(text, delimiter=delimiter, strict=True)
            header = next(reader, None)
            if not header or any(not name.strip() for name in header):
                add("empty-header")
            elif len(set(header)) != len(header):
                add("duplicate-header")
            elif missing := sorted(book.columns - set(header)):
                add("missing-columns", columns=missing)
            else:
                previous_line = reader.line_num
                for row in reader:
                    if records >= max_rows:
                        raise InputLimit("CSV record limit exceeded")
                    records += 1
                    location = {
                        "record": records,
                        "line_start": previous_line + 1,
                        "line_end": reader.line_num,
                    }
                    previous_line = reader.line_num
                    if len(row) != len(header):
                        add(
                            "ragged-record",
                            **location,
                            expected_fields=len(header),
                            observed_fields=len(row),
                        )
                        continue
                    values = dict(zip(header, row, strict=True))
                    for rule, summary in zip(book.rules, outcomes, strict=True):
                        if rule.when is not None and not rule.when.matches(values):
                            continue
                        summary["evaluated"] += 1
                        if not rule.check.matches(values):
                            summary["failed"] += 1
                            add(
                                "rule-failed",
                                rule.severity,
                                **location,
                                rule=rule.id,
                                columns=sorted(rule.check.columns),
                            )
                complete = True
                if not records:
                    add("empty-data")
    except InputLimit as exc:
        add("input-limit", limit="records" if "record" in str(exc) else "bytes")
    except (OSError, UnicodeError, csv.Error):
        # Parser exceptions can include input values: never echo them.
        add("unreadable-csv")
    total = errors + warnings
    return {
        "schema_version": 1,
        "ok": errors == 0 and (warnings == 0 or not warnings_as_errors),
        "complete": complete,
        "records_read": records,
        "error_count": errors,
        "warning_count": warnings,
        "finding_count": total,
        "findings_truncated": total > len(findings),
        "rules": outcomes,
        "findings": findings,
    }
