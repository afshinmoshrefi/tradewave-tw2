"""
get_price_EOD.py
================
Retrieve current stock price from EODHD API.

Usage:
    from get_price_EOD import get_current_price
    price = get_current_price("MSFT", "US")
"""

import sys
sys.path.insert(0, '/home/flask')
import config

import requests
from typing import Optional, Dict, Any


def get_current_price(symbol: str, exchange: str = "US") -> Optional[float]:
    """
    Get the current/latest stock price from EODHD.
    
    Args:
        symbol: Stock ticker (e.g., "MSFT", "AAPL")
        exchange: Exchange code (e.g., "US", "LSE", "TO")
    
    Returns:
        Current price as float, or None if error
    """
    # EODHD real-time endpoint
    url = f"https://eodhd.com/api/real-time/{symbol}.{exchange}"
    
    params = {
        "api_token": config.EOD_token,
        "fmt": "json"
    }
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # The 'close' field contains the latest price — may be 'NA' when market is closed
        return _safe_float(data.get("close"))

    except requests.RequestException as e:
        print(f"[EODHD] Request error: {e}")
        return None
    except (ValueError, KeyError) as e:
        print(f"[EODHD] Parse error: {e}")
        return None


def _safe_float(val) -> Optional[float]:
    """Convert a value to float, returning None for 'NA', None, or unparseable values."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _try_realtime_service(symbol: str, exchange: str) -> Optional[Dict[str, Any]]:
    """Try to get quote from the realtime price service (fast, no EODHD token cost)."""
    rt_url = getattr(config, 'realtime_service_url', None)
    if not rt_url:
        return None
    # Realtime service caches US equities by symbol name only.
    # COMM (commodities/futures) symbols can collide with stock tickers
    # (e.g. ES = Eversource Energy vs E-mini S&P 500 futures).
    # Always go direct to EODHD for COMM so the exchange qualifier is used.
    if exchange == "COMM":
        return None
    try:
        resp = requests.get(f"{rt_url.rstrip('/')}/prices/{symbol}", timeout=5)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if 'error' in data:
            return None
        return {
            "symbol": symbol,
            "exchange": exchange,
            "open":          _safe_float(data.get("open")),
            "high":          _safe_float(data.get("high")),
            "low":           _safe_float(data.get("low")),
            "close":         _safe_float(data.get("price")),
            "volume":        _safe_float(data.get("volume")),
            "previousClose": _safe_float(data.get("previous_close")),
            "change":        _safe_float(data.get("change")),
            "change_p":      _safe_float(data.get("change_p")),
            "timestamp":     data.get("timestamp"),
        }
    except Exception:
        return None


def get_quote_details(symbol: str, exchange: str = "US") -> Optional[Dict[str, Any]]:
    """
    Get full quote details. Tries the realtime service first (no EODHD token cost),
    falls back to EODHD direct API if the realtime service is unavailable.

    Args:
        symbol: Stock ticker (e.g., "MSFT", "AAPL")
        exchange: Exchange code (e.g., "US", "LSE", "TO")

    Returns:
        Dictionary with quote data, or None if error.
        Numeric fields are returned as float or None — never the string 'NA'.
    """
    # Try realtime service first (free, fast)
    result = _try_realtime_service(symbol, exchange)
    if result and result.get("close") is not None:
        return result

    # Fallback to EODHD direct API
    url = f"https://eodhd.com/api/real-time/{symbol}.{exchange}"

    params = {
        "api_token": config.EOD_token,
        "fmt": "json"
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        return {
            "symbol": symbol,
            "exchange": exchange,
            "open":          _safe_float(data.get("open")),
            "high":          _safe_float(data.get("high")),
            "low":           _safe_float(data.get("low")),
            "close":         _safe_float(data.get("close")),
            "volume":        _safe_float(data.get("volume")),
            "previousClose": _safe_float(data.get("previousClose")),
            "change":        _safe_float(data.get("change")),
            "change_p":      _safe_float(data.get("change_p")),
            "timestamp":     data.get("timestamp"),
        }

    except requests.RequestException as e:
        print(f"[EODHD] Request error: {e}")
        return None
    except (ValueError, KeyError) as e:
        print(f"[EODHD] Parse error: {e}")
        return None


# ============================================================
# SMOKE TEST
# ============================================================
if __name__ == "__main__":
    print("=" * 50)
    print("EODHD Price Retrieval - Smoke Test")
    print("=" * 50)
    
    # Test 1: Get simple price for MSFT
    print("\n[Test 1] Get current price for MSFT (US)...")
    price = get_current_price("MSFT", "US")
    if price:
        print(f"  ✓ MSFT current price: ${price:.2f}")
    else:
        print(f"  ✗ Failed to get price")
    
    # Test 2: Get full quote details for MSFT
    print("\n[Test 2] Get full quote details for MSFT (US)...")
    quote = get_quote_details("MSFT", "US")
    if quote:
        print(f"  ✓ Quote details:")
        print(f"      Symbol:    {quote['symbol']}.{quote['exchange']}")
        print(f"      Open:      ${quote['open']}")
        print(f"      High:      ${quote['high']}")
        print(f"      Low:       ${quote['low']}")
        print(f"      Close:     ${quote['close']}")
        print(f"      Volume:    {quote['volume']:,}" if quote['volume'] else "      Volume:    N/A")
        print(f"      Prev Close: ${quote['previousClose']}")
        print(f"      Change:    {quote['change']} ({quote['change_p']}%)")
    else:
        print(f"  ✗ Failed to get quote details")
    
    # Test 3: Test with another symbol
    print("\n[Test 3] Get current price for AAPL (US)...")
    price_aapl = get_current_price("AAPL", "US")
    if price_aapl:
        print(f"  ✓ AAPL current price: ${price_aapl:.2f}")
    else:
        print(f"  ✗ Failed to get price")
    
    print("\n" + "=" * 50)
    print("Smoke test complete!")
    print("=" * 50)