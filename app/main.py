from fastapi.responses import FileResponse
from fastapi import FastAPI

app = FastAPI(
    title="Free World Crypto",
    description="Our crypto trading platform API",
    version="0.1.0",
)


@app.get("/")
def home():
    return {
        "message": "Welcome to Free World Crypto!",
        "status": "under development",
    }


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
            {"symbol": "BTC", "name": "Bitcoin", "price": 65000.00},
            {"symbol": "ETH", "name": "Ethereum", "price": 3200.00},
            {"symbol": "SOL", "name": "Solana", "price": 150.00},
            {"symbol": "FREE", "name": "Free World", "price": 0.01}
        ],
        "notice": "Sample prices for practice only."
    }
@app.get("/dashboard")
def dashboard():
    return FileResponse("static/index.html")


@app.get("/wallet")
def demo_wallet():
    return {
        "wallet_name": "Ghost Demo Wallet",
        "currency": "USD",
        "starting_balance": 10000.00,
        "available_balance": 10000.00,
        "holdings": [],
        "mode": "simulation",
        "notice": "Demo funds only. No real money is held."
    }

