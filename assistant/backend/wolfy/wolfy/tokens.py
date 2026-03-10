"""Token definitions for Wolfy."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class TokenType(str, Enum):
    NUMBER = "NUMBER"
    OPERATOR = "OPERATOR"
    LEFT_PAREN = "LEFT_PAREN"
    RIGHT_PAREN = "RIGHT_PAREN"
    EOF = "EOF"


@dataclass(frozen=True)
class Token:
    token_type: TokenType
    lexeme: str
    value: Decimal | None = None
