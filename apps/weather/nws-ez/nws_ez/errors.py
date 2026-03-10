from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


class NWSError(Exception):
    """Base error for nws_ez."""


@dataclass
class NWSProblemDetail(NWSError):
    """
    RFC7807 Problem Details payload (weather.gov uses application/problem+json).
    """
    type: str = "about:blank"
    title: str = "NWS API Error"
    status: Optional[int] = None
    detail: Optional[str] = None
    instance: Optional[str] = None
    correlationId: Optional[str] = None
    raw: Optional[dict[str, Any]] = None

    def __str__(self) -> str:
        bits = [self.title]
        if self.status is not None:
            bits.append(f"(HTTP {self.status})")
        if self.detail:
            bits.append(f"- {self.detail}")
        if self.correlationId:
            bits.append(f"[correlationId={self.correlationId}]")
        return " ".join(bits)


@dataclass
class NWSHTTPError(NWSError):
    status_code: int
    url: str
    message: str
    problem: Optional[NWSProblemDetail] = None
    response_text: Optional[str] = None

    def __str__(self) -> str:
        if self.problem:
            return str(self.problem)
        return f"HTTP {self.status_code} for {self.url}: {self.message}"
