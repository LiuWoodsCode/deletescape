"""Tokenizer for arithmetic expressions."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

from .exceptions import TokenizationError
from .tokens import Token, TokenType

_TOKEN_PATTERN = re.compile(
    r"""
    (?P<WHITESPACE>\s+)
    |(?P<NUMBER>(?:\d+(?:\.\d+)?)|(?:\.\d+))
    |(?P<OPERATOR>\*\*|[+\-*/%^])
    |(?P<LEFT_PAREN>\()
    |(?P<RIGHT_PAREN>\))
    |(?P<INVALID>.)
    """,
    re.VERBOSE,
)


def tokenize(text: str) -> list[Token]:
    """Turn normalized text into tokens."""
    tokens: list[Token] = []

    for match in _TOKEN_PATTERN.finditer(text):
        kind = match.lastgroup
        lexeme = match.group()

        if kind == "WHITESPACE":
            continue
        if kind == "NUMBER":
            try:
                value = Decimal(lexeme)
            except InvalidOperation as exc:
                raise TokenizationError(f"Invalid number: {lexeme}") from exc
            tokens.append(Token(TokenType.NUMBER, lexeme, value))
            continue
        if kind == "OPERATOR":
            tokens.append(Token(TokenType.OPERATOR, lexeme))
            continue
        if kind == "LEFT_PAREN":
            tokens.append(Token(TokenType.LEFT_PAREN, lexeme))
            continue
        if kind == "RIGHT_PAREN":
            tokens.append(Token(TokenType.RIGHT_PAREN, lexeme))
            continue
        raise TokenizationError(f"Unexpected token: {lexeme}")

    tokens.append(Token(TokenType.EOF, ""))
    return tokens
