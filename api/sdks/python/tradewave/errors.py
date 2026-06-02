"""Exception hierarchy for the TradeWave SDK.

Non-2xx responses from the API carry a JSON error envelope of the shape
``{"error": {"code": "...", "message": "..."}}``. These are surfaced as a
typed exception hierarchy so callers can branch on the failure mode without
parsing strings.

Note: the graceful ML "upgrade nudge" (HTTP 200 with a ``requires:"upgrade"``
body, or an ``ml: null`` card) is NOT an error and is never raised here - it is
returned as data. See :class:`tradewave.client.Client`.
"""

from __future__ import annotations

from typing import Optional


class TradeWaveError(Exception):
    """Base class for every error raised by the SDK.

    Attributes:
        message: Human-readable error message.
        status: The HTTP status code, when the error came from a response.
        code: The machine-readable error code from the API error envelope.
        response: The parsed JSON body, when available (dict) - useful for
            inspecting fields the SDK has not modeled yet.
    """

    def __init__(
        self,
        message: str,
        *,
        status: Optional[int] = None,
        code: Optional[str] = None,
        response: Optional[dict] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.code = code
        self.response = response

    def __str__(self) -> str:
        parts = []
        if self.status is not None:
            parts.append(f"HTTP {self.status}")
        if self.code:
            parts.append(self.code)
        prefix = " ".join(parts)
        return f"[{prefix}] {self.message}" if prefix else self.message


class AuthError(TradeWaveError):
    """Authentication or authorization failure (HTTP 401 or 403).

    Usually a missing, malformed, or revoked API key, or a key whose tier does
    not have access to the requested resource.
    """


class NotFoundError(TradeWaveError):
    """The requested resource does not exist (HTTP 404)."""


class RateLimitError(TradeWaveError):
    """Rate limit exceeded (HTTP 429).

    Attributes:
        retry_after: Seconds to wait before retrying, parsed from the
            ``Retry-After`` header when present, else ``None``.
    """

    def __init__(
        self,
        message: str,
        *,
        status: Optional[int] = None,
        code: Optional[str] = None,
        response: Optional[dict] = None,
        retry_after: Optional[float] = None,
    ) -> None:
        super().__init__(message, status=status, code=code, response=response)
        self.retry_after = retry_after


class ServerError(TradeWaveError):
    """The API returned a 5xx server error."""


class TimeoutError(TradeWaveError):
    """The request timed out before a response was received."""


class ConnectionError(TradeWaveError):
    """A network-level error occurred while contacting the API."""


def error_for_status(
    status: int,
    *,
    message: str,
    code: Optional[str] = None,
    response: Optional[dict] = None,
    retry_after: Optional[float] = None,
) -> TradeWaveError:
    """Build the most specific :class:`TradeWaveError` for an HTTP status."""
    if status in (401, 403):
        return AuthError(message, status=status, code=code, response=response)
    if status == 404:
        return NotFoundError(message, status=status, code=code, response=response)
    if status == 429:
        return RateLimitError(
            message,
            status=status,
            code=code,
            response=response,
            retry_after=retry_after,
        )
    if 500 <= status < 600:
        return ServerError(message, status=status, code=code, response=response)
    return TradeWaveError(message, status=status, code=code, response=response)
