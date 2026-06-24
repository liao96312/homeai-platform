from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import os
import uuid

from jose import JWTError, jwt

from backend.app.core.config import settings

LEGACY_PBKDF2_ITERATIONS = 120_000


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or os.urandom(16).hex()
    iterations = max(int(settings.password_pbkdf2_iterations or 0), 600_000)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
    return f"pbkdf2_sha256${iterations}${salt}${digest.hex()}"


def verify_password(password: str, hashed_password: str) -> bool:
    parts = hashed_password.split("$")
    if len(parts) == 3:
        algorithm, salt, digest_hex = parts
        iterations = LEGACY_PBKDF2_ITERATIONS
    elif len(parts) == 4:
        algorithm, iterations_text, salt, digest_hex = parts
        try:
            iterations = int(iterations_text)
        except ValueError:
            return False
    else:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
    return hmac.compare_digest(digest.hex(), digest_hex)


def create_access_token(subject: str, role_key: str) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": subject,
        "role": role_key,
        # iat (issued-at) and jti (JWT id) make tokens uniquely identifiable,
        # enabling future revocation/rotate-out without waiting for expiry.
        "iat": int(now.timestamp()),
        "jti": uuid.uuid4().hex,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError as exc:
        raise ValueError("Invalid token") from exc
