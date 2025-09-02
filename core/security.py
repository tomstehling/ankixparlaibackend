 #security.py
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Any

from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import ValidationError

from core.config import settings

import schemas
logger = logging.getLogger(__name__)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against a stored hash."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Hashes a plain password."""
    return pwd_context.hash(password)



def create_access_token(data: dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Creates a JWT access token.
    The 'sub' key in the data dict is expected to be the user_id.
    """
    to_encode = data.copy()
    
    # CRITICAL FIX: Ensure the user_id (UUID) is a string before encoding
    if 'sub' in to_encode and isinstance(to_encode['sub'], uuid.UUID):
        to_encode['sub'] = str(to_encode['sub'])
        
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    if settings.AUTH_MASTER_KEY is None:
        raise ValueError("AUTH_MASTER_KEY is not set in the environment variables")
    encoded_jwt = jwt.encode(to_encode, settings.AUTH_MASTER_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> Optional[schemas.TokenPayload]:
    """

    Decodes a JWT access token.
    Returns a TokenPayload object if valid, otherwise None.
    """
    try:
        if settings.AUTH_MASTER_KEY is None:
            raise ValueError("AUTH_MASTER_KEY is not set in the environment variables")
        # The library automatically checks the expiration date.
        # No need for a manual check. It will raise ExpiredSignatureError.
        payload = jwt.decode(
            token, settings.AUTH_MASTER_KEY, algorithms=[settings.ALGORITHM]
        )
        
        # Parse the decoded payload into our Pydantic model.
        # This validates that 'sub' and 'exp' exist and have the correct types.
        token_data = schemas.TokenPayload(**payload)
        
        return token_data

    except (JWTError, ValidationError) as e:
        # Catch errors from the JWT library (e.g., bad signature, expired)
        # and errors from Pydantic (e.g., missing 'sub' field).
        logger.warning(f"Token validation error: {e}")
        return None