"""Custom exceptions for the Wolfy expression engine."""


class WolfyError(Exception):
    """Base exception for Wolfy."""


class TokenizationError(WolfyError):
    """Raised when text cannot be tokenized."""


class ParseError(WolfyError):
    """Raised when tokens do not match the supported grammar."""


class EvaluationError(WolfyError):
    """Raised when a parsed expression cannot be evaluated."""
