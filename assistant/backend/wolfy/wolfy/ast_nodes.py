"""AST node types used by the parser."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class NumberNode:
    value: Decimal


@dataclass(frozen=True)
class UnaryOpNode:
    operator: str
    operand: "ExpressionNode"


@dataclass(frozen=True)
class BinaryOpNode:
    left: "ExpressionNode"
    operator: str
    right: "ExpressionNode"


ExpressionNode = NumberNode | UnaryOpNode | BinaryOpNode
