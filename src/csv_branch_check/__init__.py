"""Declarative cross-field validation for local CSV files."""

from .core import validate
from .rules import RuleError, load_rules, parse_rules

__version__ = "0.1.0"
__all__ = ["RuleError", "load_rules", "parse_rules", "validate"]
