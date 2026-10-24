"""Compile an intentionally small predicate language; never execute source code."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class RuleError(ValueError):
    """Invalid rulebook; messages never include rule literal values."""


@dataclass(frozen=True)
class Predicate:
    op: str
    column: str = ""
    value: Any = None
    children: tuple[Predicate, ...] = ()
    separator: str = ";"

    @property
    def columns(self) -> frozenset[str]:
        result = {self.column} if self.column else set()
        if self.op in {"equals_column", "not_equals_column"}:
            result.add(self.value)
        for child in self.children:
            result.update(child.columns)
        return frozenset(result)

    def matches(self, row: dict[str, str]) -> bool:
        if self.op == "all":
            return all(child.matches(row) for child in self.children)
        if self.op == "any":
            return any(child.matches(row) for child in self.children)
        if self.op == "not":
            return not self.children[0].matches(row)
        actual = row[self.column]
        if self.op == "equals":
            return actual == self.value
        if self.op == "not_equals":
            return actual != self.value
        if self.op == "in":
            return actual in self.value
        if self.op == "not_in":
            return actual not in self.value
        if self.op == "not_empty":
            return bool(actual) == self.value
        if self.op == "equals_column":
            return actual == row[self.value]
        if self.op == "not_equals_column":
            return actual != row[self.value]
        if self.op == "each_in":
            return all(token and token in self.value for token in actual.split(self.separator))
        raise AssertionError("Uncompiled predicate")


@dataclass(frozen=True)
class Rule:
    id: str
    check: Predicate
    when: Predicate | None = None
    severity: str = "error"

    @property
    def columns(self) -> frozenset[str]:
        return self.check.columns | (self.when.columns if self.when else frozenset())


@dataclass(frozen=True)
class RuleBook:
    rules: tuple[Rule, ...]

    @property
    def columns(self) -> frozenset[str]:
        return frozenset(column for rule in self.rules for column in rule.columns)


def parse_rules(data: dict[str, Any]) -> RuleBook:
    """Validate and compile version 1 rules. Unknown keys are always errors."""
    if not isinstance(data, dict) or set(data) != {"version", "rules"}:
        raise RuleError("Rulebook requires exactly version and rules")
    if type(data["version"]) is not int or data["version"] != 1:
        raise RuleError("Only integer rulebook version 1 is supported")
    if not isinstance(data["rules"], list) or not 1 <= len(data["rules"]) <= 1000:
        raise RuleError("Rulebook requires 1 to 1000 rules")
    nodes = 0

    def predicate(source: Any, depth: int = 0) -> Predicate:
        nonlocal nodes
        nodes += 1
        if depth > 16 or nodes > 10_000:
            raise RuleError("Predicate depth or node limit exceeded")
        if not isinstance(source, dict) or not source:
            raise RuleError("Predicate must be a nonempty object")
        for boolean_op in ("all", "any", "not"):
            if boolean_op not in source:
                continue
            if set(source) != {boolean_op}:
                raise RuleError("Boolean predicate cannot contain other keys")
            value = source[boolean_op]
            if boolean_op == "not":
                children = (predicate(value, depth + 1),)
            else:
                if not isinstance(value, list) or not value:
                    raise RuleError("all/any requires a nonempty predicate list")
                children = tuple(predicate(item, depth + 1) for item in value)
            return Predicate(boolean_op, children=children)
        column = source.get("column")
        if not isinstance(column, str) or not column.strip():
            raise RuleError("Leaf predicate requires a nonblank column")
        ops = set(source) - {"column", "separator"}
        if len(ops) != 1:
            raise RuleError("Leaf predicate requires exactly one operator")
        op = ops.pop()
        value = source[op]
        string_ops = {"equals", "not_equals", "equals_column", "not_equals_column"}
        list_ops = {"in", "not_in", "each_in"}
        if op in string_ops:
            if not isinstance(value, str):
                raise RuleError("String operator requires a string argument")
            if op.endswith("_column") and not value.strip():
                raise RuleError("Column comparison requires a nonblank column")
        elif op in list_ops:
            if (
                not isinstance(value, list)
                or not value
                or not all(isinstance(x, str) for x in value)
            ):
                raise RuleError("Membership operator requires a nonempty string list")
            value = frozenset(value)
        elif op == "not_empty":
            if type(value) is not bool:
                raise RuleError("not_empty requires true or false")
        else:
            raise RuleError("Unknown predicate operator")
        separator = source.get("separator", ";")
        if "separator" in source and op != "each_in":
            raise RuleError("separator is only supported with each_in")
        if not isinstance(separator, str) or not separator or len(separator) > 16:
            raise RuleError("separator must contain 1 to 16 characters")
        return Predicate(op, column, value, separator=separator)

    result = []
    identifiers = set()
    for source in data["rules"]:
        if not isinstance(source, dict) or set(source) - {"id", "check", "when", "severity"}:
            raise RuleError("Rule contains unknown keys or is not an object")
        identifier = source.get("id")
        if not isinstance(identifier, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", identifier
        ):
            raise RuleError("Rule id must be 1 to 64 letters, digits, dots, underscores or hyphens")
        if identifier in identifiers:
            raise RuleError("Rule ids must be unique")
        identifiers.add(identifier)
        severity = source.get("severity", "error")
        if severity not in ("error", "warning"):
            raise RuleError("Severity must be error or warning")
        check = predicate(source.get("check"))
        when = predicate(source["when"]) if "when" in source else None
        result.append(Rule(identifier, check, when, severity))
    return RuleBook(tuple(result))


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RuleError("Duplicate JSON object keys are not accepted")
        result[key] = value
    return result


def load_rules(path: str | Path) -> RuleBook:
    try:
        source = Path(path)
        if not source.is_file():
            raise RuleError("Rulebook must be a regular file")
        with source.open("rb") as stream:
            raw = stream.read(1_048_577)
        if len(raw) > 1_048_576:
            raise RuleError("Rulebook exceeds 1 MiB")
        data = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique_object)
        return parse_rules(data)
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise RuleError("Rulebook must be readable UTF-8 JSON within nesting limits") from exc
