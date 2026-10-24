# Scope and acceptance

Target: data stewards who need reproducible conditional row rules without
executing code or exposing values in CI logs. Workflow: write a JSON rulebook →
validate a local CSV → locate findings by rule/record/physical lines → fix the
source data → rerun.

The MVP accepts exact string predicates, nested boolean composition, optional
conditions, warning/error levels, explicit delimiters and bounded reports.
It must reject malformed rules before reading data, reject ambiguous headers,
report ragged/malformed data, process multiline records correctly, fail partial
validation and preserve input bytes. Rule literals and source values must be
absent from successful and unsuccessful CLI output.

Architecture: JSON is compiled into immutable predicate/rule objects. Membership
lists become frozensets once; column references are checked against headers.
A bounded binary stream feeds Python's strict CSV reader through UTF-8 decoding.
Only one row and bounded findings are retained. Each rule has independent
evaluated/failed counters even after findings are truncated. Conditions never
use eval, dynamic imports, SQL or regular expressions.

Review focus: accidental source excerpts in exceptions, invalid inactive
branches, rule typos, warning-gate behavior, duplicate headers, logical/physical
line confusion, memory growth and successful exits after truncated input.
