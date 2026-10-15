"""Cached EODHD US exchange-symbol catalog for watchlist CSV validation."""

import json


CACHE_KEY = "eodhd_active_us_exchange_symbols_v1"
CACHE_TTL_SECONDS = 60 * 60
REQUEST_TIMEOUT = (3, 15)


class USCatalogUnavailable(Exception):
    """The US symbol catalog could not be loaded or validated."""


def _is_valid_code(code):
    return (
        isinstance(code, str)
        and bool(code)
        and code == code.strip()
        and not any(character.isspace() or character == "," for character in code)
        and len(code) <= 64
    )


def load_us_symbol_codes(http_client, api_token, cache_client):
    """Return exact active US ticker codes, using the one-hour Redis cache."""
    try:
        cached = cache_client.get(CACHE_KEY)
        if cached is not None:
            if isinstance(cached, bytes):
                cached = cached.decode("utf-8")
            codes = json.loads(cached)
            if isinstance(codes, list) and codes and all(
                _is_valid_code(code) for code in codes
            ):
                return {code.strip().upper() for code in codes}
    except Exception:
        # A cache read/parse issue is recoverable by fetching a fresh catalog.
        pass

    if not api_token:
        raise USCatalogUnavailable("US symbol catalog unavailable")

    try:
        response = http_client.get(
            "https://eodhd.com/api/exchange-symbol-list/US",
            params={"api_token": api_token, "fmt": "json"},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        rows = response.json()
        if not isinstance(rows, list) or not rows:
            raise ValueError("invalid US symbol catalog")
        codes = set()
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("invalid US symbol catalog row")
            code = row.get("Code")
            if not _is_valid_code(code):
                raise ValueError("invalid US symbol catalog code")
            codes.add(code.upper())
        if not codes:
            raise ValueError("US symbol catalog has no ticker codes")
    except Exception as exc:
        raise USCatalogUnavailable("US symbol catalog unavailable") from exc

    try:
        cache_client.set(CACHE_KEY, json.dumps(sorted(codes)), ex=CACHE_TTL_SECONDS)
    except Exception:
        # A cache write failure does not invalidate a successful provider result.
        pass
    return codes


def supplement_us_symbols(symbols, csv_valid_symbols, exchange, load_catalog):
    """Add exact US-catalog matches only for unmatched US-resource symbols."""
    if exchange != "US" or len(csv_valid_symbols) == len(symbols):
        return csv_valid_symbols

    catalog_codes = load_catalog()
    accepted = set(csv_valid_symbols) | catalog_codes
    return [symbol for symbol in symbols if symbol in accepted]
