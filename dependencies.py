import logging
from typing import Dict, Any
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer

import security # Handles password hashing, JWT
import database # Handles database operations
from llm_handler import GeminiHandler # Type hint for LLM handler
from models import UserPublic # For response model in get_current_user

logger = logging.getLogger(__name__)

# OAuth2 Scheme - points to the /auth/token endpoint (note the prefix)
# The tokenUrl MUST match the path where the login endpoint is mounted
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """
    Dependency: Decodes token, validates user, returns user data (as dict).
    Raises HTTPException 401 if token invalid/expired or user not found.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = security.decode_access_token(token)
    if payload is None:
        logger.warning("Token decoding failed or token is invalid/expired.")
        raise credentials_exception

    user_id_str: str | None = payload.get("sub") # Assumes user_id stored in 'sub'
    if user_id_str is None:
        logger.warning("Token payload missing 'sub' (user ID).")
        raise credentials_exception

    try:
        user_id = int(user_id_str)
    except (ValueError, TypeError):
         logger.warning(f"Invalid user ID format in token 'sub': {user_id_str}")
         raise credentials_exception

    # Fetch user details (excluding password!) from database
    user = database.get_user_by_id(user_id)
    if user is None:
        logger.warning(f"User ID {user_id} from token not found in database.")
        raise credentials_exception

    logger.info(f"Authenticated user ID: {user_id} via get_current_user")
    return user # Return user dict {id, email, created_at, hashed_password} - careful!

async def get_current_active_user(current_user: dict = Depends(get_current_user)):
    """
    Dependency: Gets user from token via get_current_user.
    Placeholder for future 'is_active' checks. Returns user dict.
    NOTE: Consider returning UserPublic model directly if password hash isn't needed downstream.
    """
    # Example: Add check if you add an 'is_active' field later
    # if not current_user.get("is_active", True): # Default to active if field missing
    #     raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
    logger.info(f"Authenticated active user ID: {current_user.get('id')}")
    # Return the full user dictionary fetched by get_current_user for now
    # If you only need public data, fetch/convert to UserPublic here.
    return current_user

# --- Dependencies to access shared resources from app.state ---

def get_llm(request: Request) -> GeminiHandler:
    """Dependency to get the initialized LLM handler from app state."""
    llm_handler = getattr(request.app.state, "llm_handler", None)
    if not llm_handler:
        logger.error("LLM Handler not found in app state.")
        raise HTTPException(status_code=503, detail="Service Unavailable: LLM Handler not ready.")
    return llm_handler

def get_prompt(prompt_name: str):
    """
    Dependency factory: Returns a dependency function that retrieves
    a specific prompt string from app state.
    """
    def _get_prompt(request: Request) -> str:
        prompt = getattr(request.app.state, prompt_name, None)
        if not prompt:
            logger.error(f"Prompt '{prompt_name}' not found in app state.")
            raise HTTPException(status_code=500, detail=f"Server configuration error: Prompt '{prompt_name}' not loaded.")
        return prompt
    return _get_prompt

def get_chat_sessions(request: Request) -> Dict[str, Any]:
    """Dependency to get the chat sessions store from app state."""
    store = getattr(request.app.state, "chat_sessions_store", None)
    if store is None: # Should have been initialized in lifespan
         logger.error("Chat session store not found in app state.")
         raise HTTPException(status_code=500, detail="Server error: Chat session store not initialized.")
    return store

def get_learned_sentences(request: Request) -> list[str]:
    """Dependency to get the list of learned sentences from app state (if used)."""
    sentences = getattr(request.app.state, "learned_sentences", [])
    return sentences