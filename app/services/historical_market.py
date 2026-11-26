"""Historical CoinGecko OHLC candles and rolling 24-hour volume snapshots."""
import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.services.market_data import COIN_IDS

API_ROOT = "https://api.coingecko.com/api/v3"
CACHE_SECONDS = 300
_cache = {}


def _headers():
    headers = {"Accept": "application/json", "User-Agent": "FreeWorldCrypto/0.5"}
    key = os.getenv("COINGECKO_DEMO_API_KEY", "").strip()
    if key:
        headers["x-cg-demo-api-key"] = key
    return headers


def _get_json(url):
    request = Request(url, headers=_headers())
    with urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def _coin_url(coin_id, endpoint, params):
    return f"{API_ROOT}/coins/{coin_id}/{endpoint}?{urlencode(params)}"


def get_historical_chart(symbol, force_refresh=False):
    symbol = symbol.upper()
    if symbol not in COIN_IDS:
        raise ValueError("Historical charts are available for listed CoinGecko assets. FREE is a simulated project asset.")

    now = time.time()
    cached = _cache.get(symbol)
    if cached and not force_refresh and now - cached["fetched_at"] < CACHE_SECONDS:
        return {**cached["data"], "cache": "hit"}

    coin_id = COIN_IDS[symbol]
    # CoinGecko Demo automatically supplies 30-minute OHLC candles for days=1.
    ohlc_payload = _get_json(_coin_url(coin_id, "ohlc", {"vs_currency": "usd", "days": 1}))
    # market_chart returns historical price, market-cap and rolling 24h-volume snapshots.
    market_payload = _get_json(_coin_url(coin_id, "market_chart", {"vs_currency": "usd", "days": 1}))

    candles = []
    for row in ohlc_payload:
        if not isinstance(row, list) or len(row) < 5:
            continue
        timestamp, open_price, high, low, close = row[:5]
        values = [open_price, high, low, close]
        if not all(isinstance(value, (int, float)) for value in values):
            continue
        candles.append({
            "time": int(timestamp // 1000),
            "open": float(open_price),
            "high": float(high),
            "low": float(low),
            "close": float(close),
        })

    candles.sort(key=lambda item: item["time"])
    if len(candles) < 2:
        raise ValueError("CoinGecko did not return enough historical candles for this asset.")

    volume_snapshots = []
    for row in market_payload.get("total_volumes", []):
        if isinstance(row, list) and len(row) >= 2 and isinstance(row[1], (int, float)):
            volume_snapshots.append({"time": int(row[0] // 1000), "volume_24h": float(row[1])})

    result = {
        "symbol": symbol,
        "source": "CoinGecko",
        "granularity": "30m",
        "candles": candles,
        "volume_snapshots": volume_snapshots,
        "volume_description": "CoinGecko's historical rolling 24-hour volume snapshots (not exchange-specific per-candle volume).",
        "notice": "Candles are aggregated CoinGecko OHLC reference data. Trades in FREE WORLD remain simulated.",
        "fetched_at": int(now),
    }
    _cache[symbol] = {"fetched_at": now, "data": result}
    return {**result, "cache": "miss"}


def clear_chart_cache():
    _cache.clear()
    _overview_cache.update(fetched_at=0.0, data={})

_overview_cache = {"fetched_at": 0.0, "data": {}}


def get_market_overview(force_refresh=False):
    now = time.time()
    if _overview_cache["data"] and not force_refresh and now - _overview_cache["fetched_at"] < CACHE_SECONDS:
        return {"source": "CoinGecko", "assets": _overview_cache["data"], "cache": "hit"}
    ids = ",".join(COIN_IDS.values())
    params = {"vs_currency": "usd", "ids": ids, "price_change_percentage": "24h"}
    payload = _get_json(f"{API_ROOT}/coins/markets?{urlencode(params)}")
    id_to_symbol = {coin_id: symbol for symbol, coin_id in COIN_IDS.items()}
    assets = {}
    for item in payload:
        symbol = id_to_symbol.get(item.get("id"))
        if not symbol:
            continue
        assets[symbol] = {
            "price": item.get("current_price"),
            "price_change_24h_pct": item.get("price_change_percentage_24h"),
            "market_cap": item.get("market_cap"),
            "volume_24h": item.get("total_volume"),
            "market_cap_rank": item.get("market_cap_rank"),
        }
    _overview_cache.update(fetched_at=now, data=assets)
    return {"source": "CoinGecko", "assets": assets, "cache": "miss"}
