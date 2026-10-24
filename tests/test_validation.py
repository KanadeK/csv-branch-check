from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from csv_branch_check import RuleError, load_rules, parse_rules, validate


def book(check, when=None, severity="error"):
    rule = {"id": "example", "check": check, "severity": severity}
    if when is not None:
        rule["when"] = when
    return {"version": 1, "rules": [rule]}


class CsvTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def csv(self, content: str, name="data.csv"):
        path = self.root / name
        path.write_text(content, encoding="utf-8", newline="")
        return path

    def test_conditional_presence(self):
        rules = book(
            {"column": "contact", "not_empty": True}, {"column": "status", "equals": "active"}
        )
        result = validate(self.csv("status,contact\nactive,yes\ninactive,\nactive,\n"), rules)
        self.assertEqual(result["records_read"], 3)
        self.assertEqual(result["rules"][0]["evaluated"], 2)
        self.assertEqual(result["error_count"], 1)
        self.assertEqual(result["findings"][0]["record"], 3)

    def test_all_any_not_and_cross_columns(self):
        condition = {
            "all": [
                {
                    "any": [
                        {"column": "a", "equals_column": "b"},
                        {"column": "a", "equals": "override"},
                    ]
                },
                {"not": {"column": "c", "not_empty": False}},
            ]
        }
        path = self.csv("a,b,c\nx,x,yes\noverride,y,yes\nx,y,yes\nx,x,\n")
        self.assertEqual(validate(path, book(condition))["error_count"], 2)

    def test_string_operators(self):
        for op, argument, failures in [
            ("equals", "x", 1),
            ("not_equals", "x", 1),
            ("in", ["x"], 1),
            ("not_in", ["x"], 1),
            ("not_empty", True, 0),
            ("not_equals_column", "b", 1),
        ]:
            with self.subTest(op=op):
                result = validate(self.csv("a,b\nx,x\ny,x\n"), book({"column": "a", op: argument}))
                self.assertEqual(result["error_count"], failures)

    def test_each_in_rejects_unknown_empty_and_trailing_tokens(self):
        rules = book({"column": "tags", "each_in": ["a", "b"], "separator": ";"})
        result = validate(self.csv('tags\na;b\na;c\n""\na;\n'), rules)
        self.assertEqual(result["error_count"], 3)
        self.assertEqual(result["rules"][0]["failed"], 3)

    def test_no_trimming_or_numeric_coercion(self):
        result = validate(
            self.csv("code\n001\n1\n001 \n"), book({"column": "code", "equals": "001"})
        )
        self.assertEqual(result["error_count"], 2)
        result = validate(self.csv('code\n" "\n'), book({"column": "code", "not_empty": True}))
        self.assertTrue(result["ok"])

    def test_warning_gate(self):
        rules = book({"column": "a", "equals": "ok"}, severity="warning")
        path = self.csv("a\nwrong\n")
        report = validate(path, rules)
        self.assertTrue(report["ok"])
        self.assertEqual(report["warning_count"], 1)
        self.assertFalse(validate(path, rules, warnings_as_errors=True)["ok"])

    def test_multiline_positions_and_bom(self):
        path = self.csv('\ufeffa,b\r\n"two\r\nlines",x\r\nwrong,y\r\n')
        report = validate(path, book({"column": "a", "equals": "no"}))
        self.assertEqual(report["findings"][0]["line_start"], 2)
        self.assertEqual(report["findings"][0]["line_end"], 3)
        self.assertEqual(report["findings"][1]["line_start"], 4)
        self.assertEqual(report["records_read"], 2)

    def test_tab_and_unicode(self):
        path = self.csv("地区\t名称\nCN\t中国\n")
        self.assertTrue(
            validate(path, book({"column": "名称", "equals": "中国"}), delimiter="\t")["ok"]
        )

    def test_duplicate_and_blank_headers(self):
        rules = book({"column": "a", "not_empty": True})
        for text, code in [
            ("a,a\nx,y\n", "duplicate-header"),
            ("a, \nx,y\n", "empty-header"),
            ("", "empty-header"),
        ]:
            with self.subTest(code=code):
                result = validate(self.csv(text), rules)
                self.assertEqual(result["findings"][0]["code"], code)
                self.assertFalse(result["complete"])

    def test_missing_columns_in_conditional_branch_are_configured_upfront(self):
        rules = book({"column": "b", "equals_column": "c"}, {"column": "never", "equals": "yes"})
        result = validate(self.csv("a\nx\n"), rules)
        self.assertEqual(result["findings"][0]["columns"], ["b", "c", "never"])

    def test_ragged_and_blank_records_are_not_silently_skipped(self):
        report = validate(
            self.csv("a,b\nx\n\nx,y,z\nok,ok\n"), book({"column": "a", "not_empty": True})
        )
        self.assertEqual(report["records_read"], 4)
        self.assertEqual(report["error_count"], 3)
        self.assertEqual(report["rules"][0]["evaluated"], 1)
        self.assertTrue(report["complete"])

    def test_header_only(self):
        report = validate(self.csv("a\n"), book({"column": "a", "not_empty": True}))
        self.assertEqual(report["findings"][0]["code"], "empty-data")

    def test_malformed_csv_and_invalid_utf8(self):
        rules = book({"column": "a", "not_empty": True})
        for raw in (b'a\n"unfinished\n', b"a\n\xff\n"):
            path = self.root / "bad.csv"
            path.write_bytes(raw)
            report = validate(path, rules)
            self.assertFalse(report["ok"])
            self.assertFalse(report["complete"])
            self.assertEqual(report["findings"][0]["code"], "unreadable-csv")

    def test_missing_and_nonfile(self):
        rules = book({"column": "a", "not_empty": True})
        for path in (self.root, self.root / "missing.csv"):
            self.assertEqual(validate(path, rules)["error_count"], 1)

    def test_bounded_storage_keeps_exact_counts(self):
        rules = book({"column": "a", "equals": "ok"})
        report = validate(self.csv("a\n" + "bad\n" * 2000), rules, max_findings=3)
        self.assertEqual(report["error_count"], 2000)
        self.assertEqual(len(report["findings"]), 3)
        self.assertTrue(report["findings_truncated"])
        self.assertTrue(report["complete"])

    def test_record_and_byte_limits_never_pass_partial_validation(self):
        path = self.csv("a\nx\ny\n")
        rules = book({"column": "a", "not_empty": True})
        for options in ({"max_rows": 1}, {"max_bytes": 4}):
            report = validate(path, rules, **options)
            self.assertFalse(report["ok"])
            self.assertFalse(report["complete"])
            self.assertEqual(report["findings"][-1]["code"], "input-limit")
        self.assertTrue(validate(path, rules, max_bytes=len(path.read_bytes()))["ok"])

    def test_strict_rule_validation(self):
        valid = book({"column": "a", "equals": "ok"})
        invalid = []
        for key, value in [("version", True), ("version", 2), ("rules", []), ("extra", 1)]:
            item = copy.deepcopy(valid)
            item[key] = value
            invalid.append(item)
        for key, value in [
            ("id", "bad id"),
            ("check", {"column": "a", "eq": "ok"}),
            ("check", {"all": []}),
            ("severity", "fatal"),
        ]:
            item = copy.deepcopy(valid)
            item["rules"][0][key] = value
            invalid.append(item)
        invalid.append({"version": 1, "rules": valid["rules"] * 2})
        for item in invalid:
            with self.subTest(item=item), self.assertRaises(RuleError):
                parse_rules(item)

    def test_invalid_leaf_types_and_ambiguous_keys(self):
        for check in [
            {"column": "a", "equals": 1},
            {"column": "a", "not_empty": 1},
            {"column": "a", "in": []},
            {"column": "a", "in": [1]},
            {"column": "", "equals": "x"},
            {"column": "a", "equals_column": ""},
            {"column": "a", "equals": "x", "not_equals": "y"},
            {"all": [], "column": "a"},
            {"column": "a", "each_in": ["a"], "separator": ""},
            {"column": "a", "equals": "a", "separator": ";"},
        ]:
            with self.subTest(check=check), self.assertRaises(RuleError):
                parse_rules(book(check))

    def test_depth_rule_and_input_option_limits(self):
        predicate = {"column": "a", "not_empty": True}
        for _ in range(18):
            predicate = {"not": predicate}
        with self.assertRaises(RuleError):
            parse_rules(book(predicate))
        rules = book({"column": "a", "not_empty": True})
        for options in ({"max_rows": 0}, {"max_findings": -1}, {"delimiter": "xx"}):
            with self.assertRaises(RuleError):
                validate(self.csv("a\nx\n"), rules, **options)

    def test_load_rules_rejects_duplicate_json_keys(self):
        path = self.root / "rules.json"
        path.write_text('{"version":1,"version":2,"rules":[]}', encoding="utf-8")
        with self.assertRaises(RuleError):
            load_rules(path)
        path.write_bytes(b"x" * 1_048_577)
        with self.assertRaises(RuleError):
            load_rules(path)

    def test_cli_no_values_no_input_modification_and_exit_codes(self):
        path = self.csv("a\nPRIVATE_SOURCE_CELL\n")
        rules_path = self.root / "rules.json"
        rules_path.write_text(json.dumps(book({"column": "a", "equals": "SECRET_EXPECTED"})))
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "csv_branch_check",
                str(path),
                "--rules",
                str(rules_path),
                "--json",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["error_count"], 1)
        self.assertNotIn("PRIVATE_SOURCE_CELL", proc.stdout + proc.stderr)
        self.assertNotIn("SECRET_EXPECTED", proc.stdout + proc.stderr)
        self.assertEqual(before, hashlib.sha256(path.read_bytes()).hexdigest())
        rules_path.write_text('{"version": 1, "rules": []}')
        bad = subprocess.run(
            [sys.executable, "-m", "csv_branch_check", str(path), "--rules", str(rules_path)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(bad.returncode, 2)

    def test_examples(self):
        examples = Path(__file__).resolve().parents[1] / "examples"
        rules = load_rules(examples / "rules.json")
        valid = validate(examples / "valid.csv", rules)
        invalid = validate(examples / "invalid.csv", rules)
        self.assertTrue(valid["ok"])
        self.assertEqual(valid["warning_count"], 1)
        self.assertEqual(invalid["error_count"], 3)
        self.assertEqual(invalid["warning_count"], 1)


if __name__ == "__main__":
    unittest.main()
