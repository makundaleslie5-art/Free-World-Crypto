"""CoinGecko-backed spot market data with a small in-memory cache.

FREE is a project-specific demo asset and is intentionally kept at its
configured simulated reference price; it is not represented as a listed coin.
"""
import json
import os
import time
from pathlib import Path
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.services.trading import PRICES

BASE_URL = "https://api.coingecko.com/api/v3/simple/price"

def _load_local_env():
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))

_load_local_env()
COIN_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "BNB": "binancecoin",
    "XRP": "ripple",
    "LINK": "chainlink",
    "DOGE": "dogecoin",
    "ADA": "cardano",
    "AVAX": "avalanche-2",
    "HYPE": "hyperliquid",
    "DOT": "polkadot",
    "LTC": "litecoin",
    "TRX": "tron",
}
CACHE_SECONDS = 300
STALE_SECONDS = 300
_cache = {"updated_at": 0.0, "prices": {}, "source": None}


def _fetch_coingecko():
    params = urlencode({"ids": ",".join(COIN_IDS.values()), "vs_currencies": "usd"})
    url = f"{BASE_URL}?{params}"
    headers = {"Accept": "application/json", "User-Agent": "FreeWorldCrypto/0.4"}
    api_key = os.getenv("COINGECKO_DEMO_API_KEY", "").strip()
    if api_key:
        headers["x-cg-demo-api-key"] = api_key
    request = Request(url, headers=headers)
    with urlopen(request, timeout=12) as response:
        payload = json.loads(response.read().decode("utf-8"))
    result = {}
    for symbol, coin_id in COIN_IDS.items():
        value = payload.get(coin_id, {}).get("usd")
        if isinstance(value, (int, float)) and value > 0:
            result[symbol] = float(value)
    if len(result) != len(COIN_IDS):
        raise ValueError("Market provider returned incomplete price data.")
    return result


def get_market_snapshot(force_refresh=False):
    now = time.time()
    age = now - _cache["updated_at"]
    if _cache["prices"] and age < CACHE_SECONDS and not force_refresh:
        live_prices = dict(_cache["prices"])
        status = "live" if age < STALE_SECONDS else "stale"
        return _snapshot(live_prices, status, age)

    try:
        live_prices = _fetch_coingecko()
        _cache.update(prices=live_prices, updated_at=now, source="CoinGecko")
        return _snapshot(live_prices, "live", 0)
    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError, OSError) as error:
        if _cache["prices"] and age <= STALE_SECONDS:
            return _snapshot(dict(_cache["prices"]), "stale", age, str(error))
        return _snapshot({}, "sample_fallback", None, str(error))


def _snapshot(live_prices, status, age, error=None):
    prices = {**PRICES, **live_prices}
    return {
        "market": "Free World Crypto",
        "mode": status,
        "source": "CoinGecko" if live_prices else "Configured demo prices",
        "updated_at": datetime.fromtimestamp(_cache["updated_at"], timezone.utc).isoformat() if live_prices else None,
        "cache_age_seconds": round(age, 1) if age is not None else None,
        "prices": [
            {"symbol": symbol, "price": price,
             "price_type": "live" if symbol in live_prices else "simulated"}
            for symbol, price in prices.items()
        ],
        "notice": (
            "Live aggregated market reference prices. Trades remain simulated and use the displayed demo price."
            if status == "live" else
            "Market provider unavailable. Displaying configured sample prices; these are not live quotes."
            if status == "sample_fallback" else
            "Showing recently cached market prices because the provider could not be reached."
        ),
        "provider_error": error,
    }


def get_trade_price(symbol):
    symbol = symbol.upper()
    snapshot = get_market_snapshot()
    for item in snapshot["prices"]:
        if item["symbol"] == symbol:
            return float(item["price"]), item["price_type"]
    raise ValueError("No price is currently available for this asset.")


# Historical chart data is cached separately from live spot prices.
HISTORY_CACHE_SECONDS = 300
_history_cache = {}


def get_historical_chart(symbol, period="1H"):
    """Return approximate 5-minute candles built from CoinGecko price samples.

    CoinGecko Demo market_chart volume values are rolling 24-hour snapshots,
    not volume traded during each individual candle.
    """
    symbol = symbol.upper()
    windows = {"1H": 3600, "4H": 14400, "1D": 86400}

    if symbol not in COIN_IDS:
        raise ValueError("Historical charts are available for BTC, ETH and SOL.")
    if period not in windows:
        raise ValueError("Unsupported chart period.")

    now = time.time()
    cached = _history_cache.get(symbol)

    if cached:
        cache_age = now - cached["updated_at"]

        if cached.get("error") and cache_age < 60:
            return {
                "candles": [],
                "source": "CoinGecko",
                "interval_minutes": 5,
                "volume_type": "rolling_24h_snapshot",
                "error": cached["error"],
            }

        if cached.get("payload") is not None and cache_age < HISTORY_CACHE_SECONDS:
            payload = cached["payload"]
        else:
            cached = None

    if not cached:
        coin_id = COIN_IDS[symbol]
        url = (
            f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
            "?vs_currency=usd&days=1"
        )
        headers = {
            "Accept": "application/json",
            "User-Agent": "FreeWorldCrypto/0.4",
        }
        api_key = os.getenv("COINGECKO_DEMO_API_KEY", "").strip()
        if api_key:
            headers["x-cg-demo-api-key"] = api_key

        try:
            request = Request(url, headers=headers)
            with urlopen(request, timeout=12) as response:
                payload = json.loads(response.read().decode("utf-8"))

            if not payload.get("prices"):
                raise ValueError("Historical price data was empty.")

            _history_cache[symbol] = {
                "updated_at": now,
                "payload": payload,
            }
        except (
            HTTPError, URLError, TimeoutError, ValueError,
            json.JSONDecodeError, OSError
        ) as error:
            _history_cache[symbol] = {
                "updated_at": now,
                "payload": None,
                "error": str(error),
            }
            return {
                "candles": [],
                "source": "CoinGecko",
                "interval_minutes": 5,
                "volume_type": "rolling_24h_snapshot",
                "error": str(error),
            }

    cutoff_ms = (now - windows[period]) * 1000
    buckets = {}

    volumes = payload.get("total_volumes", [])

    for timestamp_ms, price in payload.get("prices", []):
        if timestamp_ms < cutoff_ms or price <= 0:
            continue

        bucket = int(timestamp_ms // 300000) * 300000
        candle = buckets.get(bucket)

        if candle is None:
            buckets[bucket] = {
                "timestamp": int(bucket / 1000),
                "open": float(price),
                "high": float(price),
                "low": float(price),
                "close": float(price),
            }
        else:
            candle["high"] = max(candle["high"], float(price))
            candle["low"] = min(candle["low"], float(price))
            candle["close"] = float(price)

    volume_by_bucket = {}
    for timestamp_ms, volume in volumes:
        if timestamp_ms >= cutoff_ms:
            bucket = int(timestamp_ms // 300000) * 300000
            volume_by_bucket[bucket] = float(volume)

    candles = []
    for bucket in sorted(buckets):
        candle = buckets[bucket]
        candle["volume_24h"] = volume_by_bucket.get(bucket, 0.0)
        candles.append(candle)

    return {
        "candles": candles,
        "source": "CoinGecko",
        "interval_minutes": 5,
        "volume_type": "rolling_24h_snapshot",
        "error": None if candles else "No historical candles were returned for this period.",
    }
