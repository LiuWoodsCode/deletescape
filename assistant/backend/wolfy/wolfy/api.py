"""Public API for the first Wolfy syntax implementation."""

from __future__ import annotations

from decimal import Decimal

from .ast_nodes import ExpressionNode
from .evaluator import evaluate
from .lexer import tokenize
from .normalizer import normalize_expression
from .parser import Parser


def parse_expression(text: str) -> ExpressionNode:
    """Parse user input into an AST.

    Supported today:
    - numbers and decimals
    - parentheses
    - +, -, *, /, %, ^, **
    - simple phrases like "plus", "minus", "times", and "divided by"
    """
    normalized = normalize_expression(text)
    tokens = tokenize(normalized)
    return Parser(tokens).parse()


def evaluate_expression(text: str) -> Decimal:
    """Evaluate a basic Wolfy expression into a Decimal."""
    return evaluate(parse_expression(text))
