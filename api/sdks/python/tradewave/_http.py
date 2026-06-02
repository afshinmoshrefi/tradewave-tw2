"""HTTP transport for the TradeWave SDK.

A thin wrapper over a ``requests.Session`` that:
  - attaches the ``Authorization: Bearer <api_key>`` header and a User-Agent,
  - parses the JSON error envelope into the typed exception hierarchy,
  - retries automatically on 429 and 5xx with exponential backoff + jitter,
    honoring ``Retry-After`` when present,
  - exposes any ``X-RateLimit-*`` headers from the last response.

Only ``requests`` is used - no other third-party dependency.
"""

from __future__ import annotations

import random
import time
from typing import Any, Dict, Mapping, Optional

import requests

from . import __version__
from .errors import (
    ConnectionError as TWConnectionError,
    RateLimitError,
    TimeoutError as TWTimeoutError,
    TradeWaveError,
    error_for_status,
)

DEFAULT_BASE_URL = "https://api.tradewave.ai/v1"
DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_RETRIES = 3
_BACKOFF_BASE = 0.5  # seconds; doubled each attempt
_BACKOFF_CAP = 30.0  # never sleep longer than this between retries
_USER_AGENT = f"tradewave-python/{__version__}"


def _parse_retry_after(value: Optional[str]) -> Optional[float]:
    """Parse a Retry-After header (seconds form) into a float, else None."""
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        # HTTP-date form is allowed by the spec but the API uses seconds; if we
        # can't parse it, fall back to the computed backoff.
        return None


class HTTPClient:
    """Owns the ``requests.Session`` and the request/retry loop."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        session: Optional[requests.Session] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self._owns_session = session is None
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {api_key}",
                "User-Agent": user_agent or _USER_AGENT,
                "Accept": "application/json",
            }
        )
        # Rate-limit headers from the most recent response (X-RateLimit-*).
        self.last_rate_limit: Dict[str, str] = {}

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        if self._owns_session:
            self.session.close()

    def __enter__(self) -> "HTTPClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- core request loop -------------------------------------------------

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        json: Optional[Any] = None,
    ) -> Any:
        """Send a request and return the parsed JSON body.

        Retries on 429 and 5xx (and on transient network errors) up to
        ``max_retries``; raises a :class:`TradeWaveError` subclass on a
        terminal non-2xx response. Non-retryable 4xx (other than 429) raise
        immediately.
        """
        url = f"{self.base_url}/{path.lstrip('/')}"
        clean_params = (
            {k: v for k, v in params.items() if v is not None} if params else None
        )

        attempt = 0
        while True:
            try:
                resp = self.session.request(
                    method,
                    url,
                    params=clean_params,
                    json=json,
                    timeout=self.timeout,
                )
            except requests.Timeout as exc:
                if attempt < self.max_retries:
                    self._sleep_backoff(attempt, None)
                    attempt += 1
                    continue
                raise TWTimeoutError(f"Request to {url} timed out") from exc
            except requests.ConnectionError as exc:
                if attempt < self.max_retries:
                    self._sleep_backoff(attempt, None)
                    attempt += 1
                    continue
                raise TWConnectionError(
                    f"Failed to connect to {url}: {exc}"
                ) from exc
            except requests.RequestException as exc:
                raise TradeWaveError(f"Request to {url} failed: {exc}") from exc

            self._capture_rate_limit(resp.headers)

            if 200 <= resp.status_code < 300:
                return self._parse_json(resp)

            # Decide whether to retry.
            retry_after = _parse_retry_after(resp.headers.get("Retry-After"))
            retryable = resp.status_code == 429 or 500 <= resp.status_code < 600
            if retryable and attempt < self.max_retries:
                self._sleep_backoff(attempt, retry_after)
                attempt += 1
                continue

            # Terminal: build and raise the typed error.
            raise self._error_from_response(resp, retry_after)

    # -- helpers -----------------------------------------------------------

    def _sleep_backoff(self, attempt: int, retry_after: Optional[float]) -> None:
        """Sleep before the next retry: honor Retry-After, else exp backoff."""
        if retry_after is not None:
            delay = retry_after
        else:
            delay = min(_BACKOFF_CAP, _BACKOFF_BASE * (2 ** attempt))
        # Full jitter on top of the computed delay to avoid thundering herds.
        delay += random.uniform(0, _BACKOFF_BASE)
        time.sleep(delay)

    def _capture_rate_limit(self, headers: Mapping[str, str]) -> None:
        captured = {
            k: v for k, v in headers.items() if k.lower().startswith("x-ratelimit")
        }
        if captured:
            self.last_rate_limit = captured

    @staticmethod
    def _parse_json(resp: requests.Response) -> Any:
        if not resp.content:
            return {}
        try:
            return resp.json()
        except ValueError as exc:
            raise TradeWaveError(
                f"Expected JSON but got non-JSON response (HTTP {resp.status_code})",
                status=resp.status_code,
            ) from exc

    def _error_from_response(
        self, resp: requests.Response, retry_after: Optional[float]
    ) -> TradeWaveError:
        body: Optional[Dict[str, Any]] = None
        code: Optional[str] = None
        message = f"HTTP {resp.status_code}"
        try:
            parsed = resp.json()
            if isinstance(parsed, dict):
                body = parsed
                envelope = parsed.get("error")
                if isinstance(envelope, dict):
                    code = envelope.get("code")
                    message = envelope.get("message") or message
                elif isinstance(parsed.get("message"), str):
                    message = parsed["message"]
        except ValueError:
            text = (resp.text or "").strip()
            if text:
                message = text[:500]

        return error_for_status(
            resp.status_code,
            message=message,
            code=code,
            response=body,
            retry_after=retry_after,
        )
