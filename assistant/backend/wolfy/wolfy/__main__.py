"""Tiny command-line entrypoint for quick manual testing."""

from __future__ import annotations

import sys

from .api import evaluate_expression


def main() -> int:
    expression = " ".join(sys.argv[1:]).strip()
    if not expression:
        print("Usage: python -m wolfy <expression>")
        return 1

    print(evaluate_expression(expression))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
