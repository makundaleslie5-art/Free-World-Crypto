
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Header, HTTPException

from app.core.database import get_connection
def verify_admin_password(password: str, stored: str) -> bool:
    try:
        scheme, salt, digest = stored.split("$", 2)

        if scheme != "pbkdf2_sha256":
            return False

        candidate = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode(),
            salt.encode(),
            180_000,
        ).hex()

        return hmac.compare_digest(candidate, digest)

    except (ValueError, AttributeError):
        return False


def issue_admin_session(admin_id: int) -> str:
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()

    expires_at = (
        datetime.now(timezone.utc) + timedelta(hours=8)
    ).isoformat()

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO admin_sessions
            (token_hash, admin_id, expires_at)
            VALUES (?, ?, ?)
            """,
            (token_hash, admin_id, expires_at),
        )

    return token


def require_admin(
    authorization: str | None = Header(default=None),
) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Administrator login required.",
        )

    token = authorization[7:].strip()

    if not token:
        raise HTTPException(status_code=401, detail="Invalid admin session.")

    token_hash = hashlib.sha256(token.encode()).hexdigest()

    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                admin_users.id,
                admin_users.email,
                admin_users.role
            FROM admin_sessions
            JOIN admin_users
                ON admin_users.id = admin_sessions.admin_id
            WHERE admin_sessions.token_hash = ?
              AND admin_sessions.revoked_at IS NULL
              AND admin_sessions.expires_at > ?
              AND admin_users.is_active = 1
            """,
            (token_hash, datetime.now(timezone.utc).isoformat()),
        ).fetchone()

    if row is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid, expired or revoked admin session.",
        )

    return dict(row)
