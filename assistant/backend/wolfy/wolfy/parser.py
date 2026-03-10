"""Recursive-descent parser for basic Wolfy expressions."""

from __future__ import annotations

from .ast_nodes import BinaryOpNode, ExpressionNode, NumberNode, UnaryOpNode
from .exceptions import ParseError
from .tokens import Token, TokenType


class Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self._tokens = tokens
        self._index = 0

    def parse(self) -> ExpressionNode:
        expression = self._parse_expression()
        if self._current().token_type is not TokenType.EOF:
            raise ParseError(f"Unexpected token: {self._current().lexeme}")
        return expression

    def _parse_expression(self) -> ExpressionNode:
        node = self._parse_term()
        while self._match_operator("+", "-"):
            operator = self._previous().lexeme
            right = self._parse_term()
            node = BinaryOpNode(left=node, operator=operator, right=right)
        return node

    def _parse_term(self) -> ExpressionNode:
        node = self._parse_power()
        while self._match_operator("*", "/", "%"):
            operator = self._previous().lexeme
            right = self._parse_power()
            node = BinaryOpNode(left=node, operator=operator, right=right)
        return node

    def _parse_power(self) -> ExpressionNode:
        node = self._parse_unary()
        if self._match_operator("^", "**"):
            operator = self._previous().lexeme
            right = self._parse_power()
            node = BinaryOpNode(left=node, operator=operator, right=right)
        return node

    def _parse_unary(self) -> ExpressionNode:
        if self._match_operator("+", "-"):
            return UnaryOpNode(operator=self._previous().lexeme, operand=self._parse_unary())
        return self._parse_primary()

    def _parse_primary(self) -> ExpressionNode:
        if self._match(TokenType.NUMBER):
            token = self._previous()
            if token.value is None:
                raise ParseError("Number token is missing a value")
            return NumberNode(token.value)

        if self._match(TokenType.LEFT_PAREN):
            expression = self._parse_expression()
            self._consume(TokenType.RIGHT_PAREN, "Expected ')' after expression")
            return expression

        raise ParseError(f"Expected a number or '(', got: {self._current().lexeme or 'end of input'}")

    def _match(self, *token_types: TokenType) -> bool:
        if self._current().token_type in token_types:
            self._advance()
            return True
        return False

    def _match_operator(self, *operators: str) -> bool:
        current = self._current()
        if current.token_type is TokenType.OPERATOR and current.lexeme in operators:
            self._advance()
            return True
        return False

    def _consume(self, token_type: TokenType, message: str) -> Token:
        if self._current().token_type is token_type:
            return self._advance()
        raise ParseError(message)

    def _advance(self) -> Token:
        token = self._current()
        self._index += 1
        return token

    def _current(self) -> Token:
        return self._tokens[self._index]

    def _previous(self) -> Token:
        return self._tokens[self._index - 1]
