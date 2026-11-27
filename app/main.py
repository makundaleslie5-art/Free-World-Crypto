import json
import hashlib
import hmac
import secrets
from fastapi import FastAPI, HTTPException, Header, WebSocket, WebSocketDisconnect, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from app.core.database import initialize_database, get_connection
from app.services.trading import PRICES, buy, sell, get_wallet
from app.services.market_data import get_market_snapshot, get_trade_price
from app.services.historical_market import get_historical_chart, get_market_overview
from app.services.live_market import live_market_feed
from app.services.admin_auth import (
    verify_admin_password,
    issue_admin_session,
    require_admin,
)

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
        row = connection.execute(
            """
            SELECT users.id, users.email, users.is_suspended
            FROM auth_sessions
            JOIN users ON users.id = auth_sessions.user_id
            WHERE auth_sessions.token_hash = ?
              AND auth_sessions.created_at >= datetime('now', '-30 days')
            """,
            (token_hash,),
        ).fetchone()

    if row is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired session. Please log in again.",
        )

    if row["is_suspended"]:
        raise HTTPException(
            status_code=403,
            detail="Your account has been suspended. Contact support.",
        )

    return {"id": row["id"], "email": row["email"]}



@app.on_event("startup")
def startup():
    initialize_database()



class RegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    login_password: str = Field(min_length=6, max_length=128)
    funds_password: str = Field(min_length=6, max_length=128)


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    login_password: str = Field(min_length=1, max_length=128)



class AdminLoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=1, max_length=128)



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
        user = connection.execute(
            """
            SELECT id, email, login_password_hash, is_suspended
            FROM users
            WHERE email = ?
            """,
            (email,),
        ).fetchone()

    if not user or not verify_password(
        request.login_password, user["login_password_hash"]
    ):
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password.",
        )

    if user["is_suspended"]:
        raise HTTPException(
            status_code=403,
            detail="Your account has been suspended. Contact support.",
        )

    token = issue_session(user["id"])

    return {
        "message": "Login successful.",
        "token": token,
        "user": {
            "id": user["id"],
            "email": user["email"],
        },
    }



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


@app.get("/admin")
def admin_portal():
    return FileResponse("static/admin.html")


@app.post("/admin/auth/login")
def admin_login(request: AdminLoginRequest):
    email = request.email.strip().lower()

    with get_connection() as connection:
        admin = connection.execute(
            """
            SELECT id, email, password_hash, role
            FROM admin_users
            WHERE email = ? AND is_active = 1
            """,
            (email,),
        ).fetchone()

    if not admin or not verify_admin_password(
        request.password, admin["password_hash"]
    ):
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password.",
        )

    token = issue_admin_session(admin["id"])

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE admin_users
            SET last_login_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (admin["id"],),
        )

        connection.execute(
            """
            INSERT INTO admin_audit_logs
            (actor_admin_id, action, target_type, target_id, details_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                admin["id"],
                "admin_login",
                "admin",
                str(admin["id"]),
                '{"result":"success"}',
            ),
        )

    return {
        "message": "Administrator login successful.",
        "token": token,
        "admin": {
            "id": admin["id"],
            "email": admin["email"],
            "role": admin["role"],
        },
    }


@app.get("/admin/auth/me")
def admin_me(admin: dict = Depends(require_admin)):
    return admin


@app.post("/admin/auth/logout")
def admin_logout(
    authorization: str | None = Header(default=None),
    admin: dict = Depends(require_admin),
):
    token = authorization[7:].strip()
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    with get_connection() as connection:
        connection.execute(
            """
            UPDATE admin_sessions
            SET revoked_at = CURRENT_TIMESTAMP
            WHERE token_hash = ? AND admin_id = ?
            """,
            (token_hash, admin["id"]),
        )

    return {"message": "Administrator logged out successfully."}


@app.get("/admin/users")
def admin_list_users(
    search: str = "",
    limit: int = 25,
    offset: int = 0,
    admin: dict = Depends(require_admin),
):
    if limit < 1 or limit > 100:
        raise HTTPException(
            status_code=400,
            detail="Limit must be between 1 and 100.",
        )

    if offset < 0:
        raise HTTPException(
            status_code=400,
            detail="Offset cannot be negative.",
        )

    search = search.strip()

    with get_connection() as connection:
        total = connection.execute(
            """
            SELECT COUNT(*) AS total
            FROM users
            WHERE email LIKE ?
            """,
            (f"%{search}%",),
        ).fetchone()["total"]

        users = connection.execute(
            """
            SELECT
                u.id,
                u.email,
                u.created_at,
                u.is_suspended,
                COALESCE(w.available_balance, 0) AS available_balance,
                COALESCE(w.currency, 'USD') AS currency,
                (
                    SELECT COUNT(*)
                    FROM user_holdings h
                    WHERE h.user_id = u.id AND h.quantity > 0
                ) AS asset_count,
                (
                    SELECT COUNT(*)
                    FROM user_transactions t
                    WHERE t.user_id = u.id
                ) AS transaction_count
            FROM users u
            LEFT JOIN user_wallets w ON w.user_id = u.id
            WHERE u.email LIKE ?
            ORDER BY u.id DESC
            LIMIT ? OFFSET ?
            """,
            (f"%{search}%", limit, offset),
        ).fetchall()

    return {
        "users": [dict(user) for user in users],
        "pagination": {
            "total": total,
            "limit": limit,
            "offset": offset,
        },
    }



@app.post("/admin/users/{user_id}/suspend")
def admin_suspend_user(
    user_id: int,
    admin: dict = Depends(require_admin),
):
    if admin["role"] != "super_admin":
        raise HTTPException(
            status_code=403,
            detail="Only Super Admin can suspend accounts.",
        )

    if user_id == 1:
        raise HTTPException(
            status_code=403,
            detail="The reserved demo account cannot be suspended.",
        )

    with get_connection() as connection:
        connection.execute("BEGIN IMMEDIATE")

        user = connection.execute(
            """
            SELECT id, email, is_suspended
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        ).fetchone()

        if user is None:
            raise HTTPException(
                status_code=404,
                detail="User not found.",
            )

        if user["is_suspended"]:
            raise HTTPException(
                status_code=409,
                detail="This account is already suspended.",
            )

        connection.execute(
            "UPDATE users SET is_suspended = 1 WHERE id = ?",
            (user_id,),
        )

        revoked = connection.execute(
            """
            UPDATE auth_sessions
            SET created_at = '2000-01-01 00:00:00'
            WHERE user_id = ?
              AND created_at >= datetime('now', '-30 days')
            """,
            (user_id,),
        )

        revoked_sessions = revoked.rowcount

        connection.execute(
            """
            INSERT INTO admin_audit_logs
            (actor_admin_id, action, target_type, target_id, details_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                admin["id"],
                "user_suspended",
                "user",
                str(user_id),
json.dumps({
    "email": user["email"],
    "sessions_revoked": revoked_sessions,
}),
            ),
        )

    return {
        "message": "User account suspended successfully.",
        "user_id": user_id,
        "sessions_revoked": revoked_sessions,
    }
