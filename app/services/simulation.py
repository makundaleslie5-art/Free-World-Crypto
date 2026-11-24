import math
import random
import threading
import time
from collections import deque


INITIAL_PRICE = 0.01
MIN_PRICE = 0.000001
TICK_SECONDS = 1
MAX_HISTORY = 86400


class FreeMarketSimulator:
    """In-memory, one-second simulated market for the FREE demo asset."""

    def __init__(self, rng=None):
        self._lock = threading.RLock()
        self._rng = rng or random.Random()
        self._price = INITIAL_PRICE
        self._history = deque(maxlen=MAX_HISTORY)
        self._session_volume = 0.0
        self._session_trades = 0
        self._pending_pressure = 0.0
        self._pending_volume = 0.0
        self._pending_trades = 0
        self._stop_event = threading.Event()
        self._thread = None

        now = time.time()
        self._history.append({
            "timestamp": now,
            "open": INITIAL_PRICE,
            "high": INITIAL_PRICE,
            "low": INITIAL_PRICE,
            "close": INITIAL_PRICE,
            "volume": 0.0,
        })

    def record_trade(self, side: str, quantity: float):
        """Apply successful simulated user orders to the next market tick."""
        side = side.upper()
        quantity = float(quantity)

        if side not in {"BUY", "SELL"}:
            raise ValueError("Trade side must be BUY or SELL.")
        if not math.isfinite(quantity) or quantity <= 0:
            raise ValueError("Trade quantity must be greater than zero.")

        # Larger orders have more influence, but impact is capped.
        impact = min(0.01, math.log1p(quantity) * 0.001)
        direction = 1 if side == "BUY" else -1

        with self._lock:
            self._pending_pressure += direction * impact
            self._pending_volume += quantity
            self._pending_trades += 1

    def tick(self):
        """Advance the market by one simulated second."""
        with self._lock:
            old_price = self._price

            # Automatic market movement plus the effect of recent user orders.
            random_movement = self._rng.gauss(0, 0.00025)
            mean_reversion = (
                (INITIAL_PRICE - old_price) / INITIAL_PRICE
            ) * 0.00002

            movement = (
                random_movement
                + mean_reversion
                + self._pending_pressure
            )

            # Prevent one tick from producing an extreme price jump.
            movement = max(-0.01, min(0.01, movement))
            self._price = max(
                MIN_PRICE,
                old_price * (1 + movement)
            )

            # Background activity is simulated, not exchange-reported volume.
            background_volume = self._rng.uniform(0.5, 5.0)
            tick_volume = background_volume + self._pending_volume
            background_trades = self._rng.randint(0, 2)
            tick_trades = background_trades + self._pending_trades

            self._session_volume += tick_volume
            self._session_trades += tick_trades

            now = time.time()
            self._history.append({
                "timestamp": now,
                "open": old_price,
                "high": max(old_price, self._price),
                "low": min(old_price, self._price),
                "close": self._price,
                "volume": tick_volume,
            })

            self._pending_pressure = 0.0
            self._pending_volume = 0.0
            self._pending_trades = 0

            return self._price

    def get_snapshot(self, include_history=True):
        with self._lock:
            history = list(self._history)
            prices = [item["close"] for item in history]

            change_percent = (
                (self._price - INITIAL_PRICE) / INITIAL_PRICE
            ) * 100

            result = {
                "symbol": "FREE",
                "price": self._price,
                "price_type": "simulated",
                "market_mode": "hybrid_simulation",
                "change_percent": change_percent,
                "session_high": max(prices),
                "session_low": min(prices),
                "session_volume": self._session_volume,
                "session_trades": self._session_trades,
                "update_interval_seconds": TICK_SECONDS,
                "history": history if include_history else [],
            }
            return result

    def get_chart_history(self, period="1H"):
        """Aggregate one-second ticks into historical OHLC candles."""
        bucket_sizes = {
            "1H": 60,
            "4H": 240,
            "1D": 1440,
        }

        if period not in bucket_sizes:
            raise ValueError("Unsupported chart period.")

        bucket_seconds = bucket_sizes[period]

        with self._lock:
            ticks = list(self._history)

        candles = {}

        for tick in ticks:
            bucket = int(tick["timestamp"] // bucket_seconds) * bucket_seconds

            if bucket not in candles:
                candles[bucket] = {
                    "timestamp": bucket,
                    "open": tick["open"],
                    "high": tick["high"],
                    "low": tick["low"],
                    "close": tick["close"],
                    "volume": tick["volume"],
                }
            else:
                candle = candles[bucket]
                candle["high"] = max(candle["high"], tick["high"])
                candle["low"] = min(candle["low"], tick["low"])
                candle["close"] = tick["close"]
                candle["volume"] += tick["volume"]

        return list(candles.values())[-60:]

    def _run(self):
        while not self._stop_event.wait(TICK_SECONDS):
            self.tick()

    def start(self):
        with self._lock:
            if self._thread and self._thread.is_alive():
                return

            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="free-market-simulator",
                daemon=True,
            )
            self._thread.start()

    def stop(self):
        self._stop_event.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=2)


free_market = FreeMarketSimulator()


def start_simulation():
    free_market.start()


def stop_simulation():
    free_market.stop()


def get_free_market_snapshot(include_history=True):
    return free_market.get_snapshot(include_history=include_history)


def record_free_trade(side: str, quantity: float):
    free_market.record_trade(side, quantity)


def get_free_chart_history(period="1H"):
    return free_market.get_chart_history(period)


def get_free_price():
    return free_market.get_snapshot(include_history=False)["price"]
