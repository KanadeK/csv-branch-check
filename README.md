# csv-branch-check

Validate conditional rules across CSV columns using a small JSON rulebook.
Stream local data and get actionable record/line locations without printing
cell values. No runtime dependencies, network access or expression evaluation.

```text
FAIL: 2 records; 3 errors; 1 warnings
```

Useful for rules such as “active records need email or phone”, “US records
must use the expected country label”, or “every selected tag must be allowed”.
The [Frictionless community has asked for these conditional checks and warning
levels](https://github.com/frictionlessdata/frictionlessdata.io/discussions/933).
Frictionless, Great Expectations, JSON Schema and fileprep are capable broader
alternatives. This tool focuses on exact strings, a deliberately small safe
rule language, bounded output and zero runtime dependencies. It does not infer
a schema or replace a general data-quality platform.

## Install and remove

Python 3.10+ and Git are required. Distributed on GitHub; not published to PyPI.

```sh
git clone https://github.com/KanadeK/csv-branch-check.git
cd csv-branch-check
python -m venv .venv
```

Activate with `source .venv/bin/activate` on Linux/macOS or
`.venv\Scripts\Activate.ps1` on Windows PowerShell, then:

```sh
python -m pip install .
csv-branch-check --version
```

If activation is restricted, directly use `.venv\Scripts\python.exe` and
`.venv\Scripts\csv-branch-check.exe`; no execution-policy change is required.
Building may download setuptools. Installed validation works offline.

Uninstall with `python -m pip uninstall csv-branch-check`. No caches or hidden
configuration are created. Deactivate and remove the clone/virtual environment
when no longer needed; remove any report files you redirected yourself.

## Run the complete example

```sh
csv-branch-check examples/valid.csv --rules examples/rules.json --json
# exit 0: 2 records, 0 errors, 1 warning

csv-branch-check examples/invalid.csv --rules examples/rules.json --json
# exit 1: 2 records, 3 errors, 1 warning

csv-branch-check examples/valid.csv --rules examples/rules.json --warnings-as-errors
# exit 1: the optional email warning is now a gate
```

Use `--delimiter comma|tab|semicolon|pipe` to choose the separator explicitly.
Input must be UTF-8 (a leading BOM is accepted). Quoted multiline cells are
supported; `record` is the 1-based data-record number and `line_start` /
`line_end` identify physical lines including the header. Blank data lines are
records with zero fields and are reported as ragged.

## Write rules

```json
{
  "version": 1,
  "rules": [
    {
      "id": "active-needs-contact",
      "severity": "error",
      "when": {"column": "status", "equals": "active"},
      "check": {"any": [
        {"column": "email", "not_empty": true},
        {"column": "phone", "not_empty": true}
      ]}
    }
  ]
}
```

`when` is optional. A rule is evaluated only for matching rows. Severity defaults
to `error`; `warning` findings preserve exit 0 unless `--warnings-as-errors` is
set. Rule IDs must be unique and contain 1–64 ASCII letters, digits, dots,
underscores or hyphens, beginning with a letter or digit.

Each leaf predicate has `column` and exactly one operator:

| Operator | Argument | Meaning |
| --- | --- | --- |
| `equals` / `not_equals` | string | Exact string equality/inequality |
| `in` / `not_in` | nonempty string array | Exact whole-cell membership/nonmembership |
| `not_empty` | boolean | `true`: cell is not `""`; `false`: cell is `""` |
| `equals_column` / `not_equals_column` | column name | Compare two cells in the same row |
| `each_in` | nonempty string array | Split cell and require every nonempty token to be allowed |

Only `each_in` accepts `separator` (default `;`, 1–16 characters). An empty cell,
unknown token, repeated separator or trailing separator fails that predicate.
Tokens are not trimmed; repeated valid tokens are allowed. Cells such as `001`,
`1` and `001 ` remain different. Whitespace-only cells are nonempty.

Combine predicates with `{"all": [p1, p2]}`, `{"any": [p1, p2]}` or
`{"not": p}`; all/any require a nonempty array. The same predicate language
works in both `when` and `check`. All referenced columns, including inactive
branches and column comparisons, must exist in the header before data scanning.
Unknown keys, operators, duplicate JSON object keys and invalid argument types
are configuration errors. No Python, SQL, regex or plugin code is accepted.

## Output and failure behavior

Exit **0**: no error findings and warning policy satisfied. Exit **1**: data,
structure, input or resource-limit findings. Exit **2**: invalid rules/options.
Rule errors are written as JSON to stderr. Data reports are written to stdout.

`--json` returns schema version 1 with `ok`, `complete`, `records_read`, exact
error/warning counts, per-rule evaluated/failed counts and bounded findings.
`complete=false` means the entire input could not be validated. A ragged record
is counted and reported but is not evaluated against rules. Valid header-only
input is an `empty-data` error. Blank/duplicate headers and missing columns stop
data scanning. Parser exceptions are reported without their source excerpts.

```python
from csv_branch_check import load_rules, validate

report = validate("data.csv", load_rules("rules.json"))
assert report["ok"], report["findings"]
```

## Limits in 0.1.0

Rules operate on one CSV row at a time: no joins, global uniqueness, sorting,
type inference, numeric ordering, date arithmetic or automatic correction.
Use a schema tool or database when you need these features.

Defaults: 1 MiB rulebook, 1,000 rules, 10,000 predicate nodes, 16 nesting edges,
250 MB of CSV bytes, 1,000,000 data records and 1,000 stored findings.
`--max-bytes`, `--max-rows` and `--max-findings` change CSV limits. Validation
continues after finding storage fills; exact counts and exit status are retained.
Byte or row-limit exhaustion always fails and marks the result incomplete.
Python's CSV field-size limit also applies (normally 131,072 characters); the
tool does not change that process-global setting. Parser behavior follows
`csv.reader(strict=True)`, not an independent full RFC 4180 conformance check.
Memory holds one record, the compiled rules and bounded findings. Inputs are
not snapshotted; do not modify them during a check.

Reports omit cell values and rule literals. Column names and rule IDs remain
visible and can themselves be sensitive. Review output before sharing.

See [validation](docs/VALIDATION.md), [contribution guide](CONTRIBUTING.md),
[security policy](SECURITY.md) and [MIT license](LICENSE).

## 中文说明

用 JSON 编写跨字段条件校验，例如“状态为 active 时必须提供邮箱或电话”、
“国家代码为 US 时名称必须匹配”、多选标签必须全部有效。支持逻辑组合、
跨列相等比较和警告级别，不需要编写脚本。逐行读取 UTF-8 CSV，输出记录号、
行号、字段和规则 ID，不输出单元格内容。不会修改文件或联网。

执行 `python -m pip install .` 安装，运行上方 examples 即可体验完整流程。
默认警告不阻止通过，可加 `--warnings-as-errors`。字段按原始字符串比较，
不自动去空格或转换数字；当前版本不处理跨行关系、类型校验或数据修复。
