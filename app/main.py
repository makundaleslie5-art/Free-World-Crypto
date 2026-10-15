from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.core.database import initialize_database
from app.services.trading import PRICES, buy, sell, get_wallet, load_wallet

app = FastAPI(
    title="Free World Crypto",
    description="Our crypto trading platform API",
    version="0.2.0",
)


@app.on_event("startup")
def startup():
    initialize_database()
    load_wallet()


class TradeRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=10)
    quantity: float = Field(gt=0, le=1_000_000)


@app.get("/")
def home():
    return FileResponse("static/index.html")

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "trading_mode": "simulation_only",
    }


@app.get("/market/prices")
def market_prices():
    return {
        "market": "Free World Crypto",
        "mode": "simulation",
        "prices": [
            {"symbol": symbol, "price": price}
            for symbol, price in PRICES.items()
        ],
        "notice": "Sample prices for practice only.",
    }


@app.get("/dashboard")
def dashboard():
    return FileResponse("static/index.html")


@app.get("/wallet")
def demo_wallet():
    return get_wallet()


@app.post("/trade/buy")
def buy_crypto(request: TradeRequest):
    try:
        return {
            "message": "Demo purchase successful",
            "transaction": buy(request.symbol, request.quantity),
            "wallet": get_wallet(),
        }
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


@app.post("/trade/sell")
def sell_crypto(request: TradeRequest):
    try:
        return {
            "message": "Demo sale successful",
            "transaction": sell(request.symbol, request.quantity),
            "wallet": get_wallet(),
        }
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
