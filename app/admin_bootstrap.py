import hashlib
import getpass
import re
import secrets

from app.core.database import initialize_database, get_connection


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode(),
        salt.encode(),
        180_000,
    ).hex()
    return f"pbkdf2_sha256${salt}${digest}"


def main():
    initialize_database()

    email = input("Super Admin email: ").strip().lower()

    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        print("Invalid email address.")
        return

    with get_connection() as connection:
        existing = connection.execute(
            "SELECT COUNT(*) FROM admin_users"
        ).fetchone()[0]

    if existing:
        print("An admin account already exists. Bootstrap is disabled.")
        return

    password = getpass.getpass("Create Super Admin password: ")
    confirmation = getpass.getpass("Confirm password: ")

    if password != confirmation:
        print("Passwords do not match.")
        return

    if len(password) < 14:
        print("Password must contain at least 14 characters.")
        return

    if len(password) > 128:
        print("Password must not exceed 128 characters.")
        return

    password_hash = hash_password(password)

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO admin_users (email, password_hash, role)
            VALUES (?, ?, 'super_admin')
            """,
            (email, password_hash),
        )

    print("Super Admin account created successfully.")
    print("Keep your credentials secure.")


if __name__ == "__main__":
    main()
