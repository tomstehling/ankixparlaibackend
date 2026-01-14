import logging
from typing import Dict, Any, Optional
from fastapi import Depends, HTTPException, status, Request, Header
from fastapi.security import OAuth2PasswordBearer
import database.models as models
import database.crud as crud  # CRUD operations for database
from sqlalchemy.ext.asyncio import AsyncSession
from database.session import get_db_session
import core.security as security  # Handles password hashing, JWT
import database.crud as crud
from services.llm_handler import GeminiHandler, OpenRouterHandler  # Type hint for LLM handler
import schemas
import uuid


logger = logging.getLogger(__name__)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db_session: AsyncSession = Depends(get_db_session),
) -> models.User:
    """
    Dependency: Decodes token, validates user, and returns the User ORM object.
    Raises HTTPException 401 if token is invalid, expired, or user not found.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload: Optional[schemas.TokenPayload] = security.decode_access_token(token)
    if payload is None:
        logger.warning("Token decoding failed or token is invalid/expired.")
        raise credentials_exception

    user_id_from_token = payload.sub
    try:
        user_id = uuid.UUID(user_id_from_token)
    except ValueError:

        logger.warning(f"Invalid UUID format in token 'sub': {user_id_from_token}")
        raise credentials_exception

    user = await crud.get_user_by_id(db_session=db_session, user_id=user_id)
    if user is None:
        logger.warning(f"User with UUID {user_id} from token not found in database.")
        raise credentials_exception

    logger.info(f"Authenticated user ID: {user.id} via get_current_user")
    return user


async def get_current_active_user(
    current_user: models.User = Depends(get_current_user),
    db_session: AsyncSession = Depends(get_db_session),
    timezone_from_header: str = Header(
        "Europe/Berlin",
        alias="X-User-Timezone",
        description="User's timezone from request header",
    ),
):
    logger.info(f"Authenticated active user ID: {current_user.id}")

    # make sure streak is up-to-date
    await crud.get_streak(
        db_session=db_session, user=current_user, timezone=timezone_from_header
    )
    return current_user


# --- Dependencies to access shared resources from app.state ---


def get_llm(request: Request) -> Any:
    """Dependency to get the initialized LLM handler from app state."""
    llm_handler = getattr(request.app.state, "llm_handler", None)
    if not llm_handler:
        logger.error("LLM Handler not found in app state.")
        raise HTTPException(
            status_code=503, detail="Service Unavailable: LLM Handler not ready."
        )
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
            raise HTTPException(
                status_code=500,
                detail=f"Server configuration error: Prompt '{prompt_name}' not loaded.",
            )
        return prompt

    return _get_prompt


def get_chat_sessions(request: Request) -> Dict[str, Any]:
    """Dependency to get the chat sessions store from app state."""
    store = getattr(request.app.state, "chat_sessions_store", None)
    if store is None:  # Should have been initialized in lifespan
        logger.error("Chat session store not found in app state.")
        raise HTTPException(
            status_code=500, detail="Server error: Chat session store not initialized."
        )
    return store


def get_learned_sentences(request: Request) -> list[str]:
    """Dependency to get the list of learned sentences from app state (if used)."""
    sentences = getattr(request.app.state, "learned_sentences", [])
    return sentences
