import asyncio
import json
import logging

import websockets
from fastapi import WebSocket

logger = logging.getLogger(__name__)

SYMBOLS = [
    "BTC", "ETH", "SOL", "BNB", "XRP", "LINK", "DOGE",
    "ADA", "AVAX", "HYPE", "DOT", "LTC", "TRX",
]

STREAMS = "/".join(f"{symbol.lower()}usdt@trade" for symbol in SYMBOLS)
BINANCE_URL = f"wss://stream.binance.com:9443/stream?streams={STREAMS}"


class LiveMarketFeed:
    def __init__(self):
        self.clients: set[WebSocket] = set()
        self.latest: dict[str, dict] = {}
        self.task: asyncio.Task | None = None

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.clients.add(websocket)

        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self.run())

        for item in self.latest.values():
            try:
                await websocket.send_json(item)
            except Exception:
                break

    async def disconnect(self, websocket: WebSocket):
        self.clients.discard(websocket)

        if not self.clients and self.task and not self.task.done():
            task = self.task
            self.task = None
            task.cancel()

    async def broadcast(self, message: dict):
        self.latest[message["symbol"]] = message
        disconnected = []

        for client in list(self.clients):
            try:
                await client.send_json(message)
            except Exception:
                disconnected.append(client)

        for client in disconnected:
            self.clients.discard(client)

    async def run(self):
        while self.clients:
            try:
                logger.info("Connecting to Binance public market stream")

                async with websockets.connect(
                    BINANCE_URL,
                    ping_interval=20,
                    ping_timeout=20,
                    close_timeout=5,
                    open_timeout=15,
                    max_queue=1000,
                ) as connection:
                    logger.info("Binance market stream connected")

                    async for raw_message in connection:
                        payload = json.loads(raw_message)
                        trade = payload.get("data", payload)

                        symbol = trade.get("s", "").removesuffix("USDT")
                        if symbol not in SYMBOLS:
                            continue

                        price = float(trade["p"])
                        trade_time = int(trade["T"])

                        if price <= 0:
                            continue

                        await self.broadcast({
                            "type": "trade",
                            "symbol": symbol,
                            "price": price,
                            "trade_time": trade_time,
                            "source": "Binance",
                        })

            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Binance stream disconnected; reconnecting")
                await asyncio.sleep(3)


live_market_feed = LiveMarketFeed()
