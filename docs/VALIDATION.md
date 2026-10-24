# Validation for 0.1.0

Executed on 2026-10-24 with Windows and CPython 3.13.16:

- `python -m unittest discover -s tests -v`: 22 tests passed.
- Ruff 0.17.2 lint and formatting checks passed.
- Covered nested conditions, all predicate operators, warning gates, exact-string
  behavior, multiline physical positions, BOM/Unicode/tab input, duplicate/blank
  headers, inactive-branch missing columns, ragged and blank records, malformed
  CSV, invalid UTF-8, missing files, header-only data and invalid rulebooks.
- Byte/record limits failed incomplete validation; a 2,000-finding input retained
  exact counts with only three stored findings. Duplicate JSON keys and excessive
  predicate nesting were rejected. Invalid configuration returned exit 2.
- CLI integration tests confirmed failing data returns exit 1, private source and
  expected literal markers stay absent from both output streams, and input byte
  hashes remain unchanged.

The release procedure additionally builds sdist/wheel, installs the wheel without
network/dependencies in a separate clean venv, reruns tests and both README
examples, checks pip metadata and verifies a fresh public clone installation.
Release assets are created only after those checks and GitHub CI pass.

The CI workflow runs on Linux (Python 3.10/3.13), Windows (3.13) and macOS
(3.13), with a Linux formatting/build job. See Actions for actual run status.
No security scan can establish absence of unknown vulnerabilities. Runtime
dependencies are zero; the separately installed development toolchain was
checked with pip-audit 2.10.1 with no known vulnerabilities reported.

Review kept strict zip pairing, fail-on-partial behavior and up-front column
validation. No external code or data was copied into this project.
