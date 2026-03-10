"""Evaluate parsed Wolfy expressions."""

from __future__ import annotations

from decimal import Decimal, DivisionByZero, InvalidOperation

from .ast_nodes import BinaryOpNode, ExpressionNode, NumberNode, UnaryOpNode
from .exceptions import EvaluationError


def evaluate(node: ExpressionNode) -> Decimal:
    """Evaluate an AST into a Decimal value."""
    if isinstance(node, NumberNode):
        return node.value

    if isinstance(node, UnaryOpNode):
        value = evaluate(node.operand)
        if node.operator == "+":
            return value
        if node.operator == "-":
            return -value
        raise EvaluationError(f"Unsupported unary operator: {node.operator}")

    if isinstance(node, BinaryOpNode):
        left = evaluate(node.left)
        right = evaluate(node.right)

        try:
            if node.operator == "+":
                return left + right
            if node.operator == "-":
                return left - right
            if node.operator == "*":
                return left * right
            if node.operator == "/":
                return left / right
            if node.operator == "%":
                return left % right
            if node.operator in {"^", "**"}:
                return _power(left, right)
        except (DivisionByZero, InvalidOperation, ZeroDivisionError) as exc:
            raise EvaluationError(str(exc)) from exc

        raise EvaluationError(f"Unsupported operator: {node.operator}")

    raise EvaluationError(f"Unsupported AST node: {type(node).__name__}")


def _power(base: Decimal, exponent: Decimal) -> Decimal:
    integral_exponent = exponent.to_integral_value()
    if exponent == integral_exponent:
        return base ** int(integral_exponent)
    return Decimal(str(float(base) ** float(exponent)))
