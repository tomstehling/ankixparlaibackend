# security.py
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from core.config import settings


# Password Hashing Context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against a stored hash."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Hashes a plain password."""
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Creates a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.AUTH_MASTER_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> Optional[dict]:
    """Decodes a JWT access token. Returns payload or None if invalid/expired."""
    try:
        payload = jwt.decode(token, settings.AUTH_MASTER_KEY, algorithms=[settings.ALGORITHM])
        # Optionally check for specific claims like 'sub' here if needed
        # Check expiration manually just to be explicit (though decode should handle it)
        if payload.get("exp") is None or datetime.fromtimestamp(payload["exp"], timezone.utc) < datetime.now(timezone.utc):
             raise JWTError("Token has expired")
        return payload
    except JWTError as e:
        print(f"JWT Error: {e}") # Log this properly in production
        return None