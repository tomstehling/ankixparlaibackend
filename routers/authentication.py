import logging
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
import core.security as security
from schemas import UserCreate, UserPublic, Token
from dependencies import get_current_active_user # Import the shared dependency
from sqlalchemy.ext.asyncio import AsyncSession
from database.crud import get_user_by_email, create_user
from database.session import get_db_session
import database.models as models


logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
async def register_user(user_data: UserCreate,db_session:AsyncSession=Depends(get_db_session)):
    """Registers a new user in the database."""
    logger.info(f"Registration attempt for email: {user_data.email}")
    existing_user = await get_user_by_email(db_session,user_data.email)
    if existing_user:
        logger.warning(f"Registration failed: Email '{user_data.email}' already exists.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    new_user = await create_user(db_session, user_data)
    return new_user


@router.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends(),db_session: AsyncSession = Depends(get_db_session)):
    """Provides a JWT token for valid username (email) and password."""
    logger.info(f"Login attempt for user: {form_data.username}")
    user = await get_user_by_email(db_session,form_data.username)
    # Important: get_user_by_email MUST return the hashed_password
    if not user or not user.hashed_password or not security.verify_password(form_data.password, user.hashed_password):
        logger.warning(f"Login failed for user: {form_data.username} - Incorrect email or password.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_data = {"sub": str(user.id)}
    access_token = security.create_access_token(data=access_token_data)
    logger.info(f"Login successful for user: {form_data.username}. Token issued.")
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/users/me", response_model=models.User)
async def read_users_me(current_user: models.User = Depends(get_current_active_user)):
    """Returns the public data for the currently authenticated user."""
    logger.info(f"Access to /users/me by user ID: {current_user.id}")
    # The dependency already fetched the user dict. We use UserPublic model for response.
    return current_user