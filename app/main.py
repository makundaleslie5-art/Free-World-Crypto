import hashlib
import hmac
import secrets
from fastapi import FastAPI, HTTPException, Header, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from app.core.database import initialize_database, get_connection
from app.services.trading import PRICES, buy, sell, get_wallet
from app.services.market_data import get_market_snapshot, get_trade_price
from app.services.historical_market import get_historical_chart, get_market_overview
from app.services.live_market import live_market_feed

app = FastAPI(title="Free World Crypto", description="Crypto trading simulation platform API", version="0.5.0")


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 180_000).hex()
    return f"pbkdf2_sha256${salt}${digest}"



def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt, digest = stored.split("$", 2)
        if scheme != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 180_000).hex()
        return hmac.compare_digest(candidate, digest)
    except (ValueError, AttributeError):
        return False



def issue_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with get_connection() as connection:
        connection.execute("INSERT INTO auth_sessions (token_hash, user_id) VALUES (?, ?)", (token_hash, user_id))
    return token



def require_user(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Please log in first.")
    token = authorization[7:].strip()
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with get_connection() as connection:
        row = connection.execute("SELECT users.id, users.email FROM auth_sessions JOIN users ON users.id = auth_sessions.user_id WHERE auth_sessions.token_hash = ? AND auth_sessions.created_at >= datetime('now', '-30 days')", (token_hash,)).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session. Please log in again.")
    return dict(row)



@app.on_event("startup")
def startup():
    initialize_database()



class RegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    login_password: str = Field(min_length=8, max_length=128)
    funds_password: str = Field(min_length=12, max_length=128)



class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    login_password: str = Field(min_length=1, max_length=128)



class TradeRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=10)
    quantity: float = Field(gt=0, le=1_000_000)
    funds_password: str = Field(min_length=1, max_length=128)



@app.get("/")
def home():
    return FileResponse("static/index.html")



@app.get("/health")
def health_check():
    return {"status": "healthy", "trading_mode": "simulation_only"}





@app.websocket("/ws/market")
async def live_market_socket(websocket: WebSocket):
    await live_market_feed.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await live_market_feed.disconnect(websocket)

@app.get("/market/prices")
def market_prices():
    return get_market_snapshot()


@app.get("/market/overview")
def market_overview():
    try:
        return get_market_overview()
    except Exception as error:
        raise HTTPException(status_code=503, detail="Market statistics are temporarily unavailable.") from error


@app.get("/market/chart/{symbol}")
def market_chart(symbol: str):
    try:
        return get_historical_chart(symbol)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=503, detail="Historical market data is temporarily unavailable. Check the CoinGecko API key, plan limits, or network connection.") from error



@app.get("/dashboard")
def dashboard():
    return FileResponse("static/index.html")



@app.post("/auth/register")
def register(request: RegisterRequest):
    email = request.email.strip().lower()
    if "@" not in email or email.startswith("@") or email.endswith("@"):
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    with get_connection() as connection:
        existing = connection.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="An account with this email already exists.")
        cursor = connection.execute("INSERT INTO users (email, login_password_hash, funds_password_hash) VALUES (?, ?, ?)", (email, hash_password(request.login_password), hash_password(request.funds_password)))
        user_id = cursor.lastrowid
        connection.execute("INSERT INTO user_wallets (user_id, available_balance) VALUES (?, 10000.00)", (user_id,))
    token = issue_session(user_id)
    return {"message": "Account created successfully. Your demo wallet is ready.", "token": token, "user": {"id": user_id, "email": email}}



@app.post("/auth/login")
def login(request: LoginRequest):
    email = request.email.strip().lower()
    with get_connection() as connection:
        user = connection.execute("SELECT id, email, login_password_hash FROM users WHERE email = ?", (email,)).fetchone()
    if not user or not verify_password(request.login_password, user["login_password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    token = issue_session(user["id"])
    return {"message": "Login successful.", "token": token, "user": {"id": user["id"], "email": user["email"]}}



@app.get("/auth/me")
def me(user: dict = __import__('fastapi').Depends(require_user)):
    return user



@app.post("/auth/logout")
def logout(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Please log in first.")
    token_hash = hashlib.sha256(authorization[7:].strip().encode()).hexdigest()
    with get_connection() as connection:
        connection.execute("DELETE FROM auth_sessions WHERE token_hash = ?", (token_hash,))
    return {"message": "Logged out successfully."}



@app.get("/wallet")
def wallet(user: dict = __import__('fastapi').Depends(require_user)):
    return get_wallet(user["id"])



@app.post("/trade/buy")
def buy_crypto(request: TradeRequest, user: dict = __import__('fastapi').Depends(require_user)):
    with get_connection() as connection:
        row = connection.execute("SELECT funds_password_hash FROM users WHERE id = ?", (user["id"],)).fetchone()
    if not row or not verify_password(request.funds_password, row["funds_password_hash"]):
        raise HTTPException(status_code=403, detail="Incorrect funds password.")
    try:
        price, price_type = get_trade_price(request.symbol)
        return {"message": "Demo purchase successful", "price_type": price_type, "transaction": buy(request.symbol, request.quantity, user["id"], price=price), "wallet": get_wallet(user["id"])}
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))



@app.post("/trade/sell")
def sell_crypto(request: TradeRequest, user: dict = __import__('fastapi').Depends(require_user)):
    with get_connection() as connection:
        row = connection.execute("SELECT funds_password_hash FROM users WHERE id = ?", (user["id"],)).fetchone()
    if not row or not verify_password(request.funds_password, row["funds_password_hash"]):
        raise HTTPException(status_code=403, detail="Incorrect funds password.")
    try:
        price, price_type = get_trade_price(request.symbol)
        return {"message": "Demo sale successful", "price_type": price_type, "transaction": sell(request.symbol, request.quantity, user["id"], price=price), "wallet": get_wallet(user["id"])}
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
