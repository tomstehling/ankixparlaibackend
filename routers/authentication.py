import logging
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

import database
import security
from models import UserCreate, UserPublic, Token
from dependencies import get_current_active_user # Import the shared dependency

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
async def register_user(user_data: UserCreate):
    """Registers a new user in the database."""
    logger.info(f"Registration attempt for email: {user_data.email}")
    existing_user = database.get_user_by_email(user_data.email)
    if existing_user:
        logger.warning(f"Registration failed: Email '{user_data.email}' already exists.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    hashed_password = security.get_password_hash(user_data.password)
    user_id = database.add_user_to_db(email=user_data.email, hashed_password=hashed_password)
    if user_id is None:
        logger.error(f"Failed to add user '{user_data.email}' to DB.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create user due to a server error."
        )

    created_user = database.get_user_by_id(user_id)
    if not created_user:
         logger.error(f"Could not retrieve user {user_id} immediately after creation.")
         raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve created user."
        )
    logger.info(f"User '{user_data.email}' registered successfully with ID: {user_id}")
    return UserPublic(**created_user)


@router.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """Provides a JWT token for valid username (email) and password."""
    logger.info(f"Login attempt for user: {form_data.username}")
    user = database.get_user_by_email(form_data.username)
    # Important: get_user_by_email MUST return the hashed_password
    if not user or not user.get("hashed_password") or not security.verify_password(form_data.password, user["hashed_password"]):
        logger.warning(f"Login failed for user: {form_data.username} - Incorrect email or password.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_data = {"sub": str(user["id"])}
    access_token = security.create_access_token(data=access_token_data)
    logger.info(f"Login successful for user: {form_data.username}. Token issued.")
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/users/me", response_model=UserPublic)
async def read_users_me(current_user: dict = Depends(get_current_active_user)):
    """Returns the public data for the currently authenticated user."""
    logger.info(f"Access to /users/me by user ID: {current_user.get('id')}")
    # The dependency already fetched the user dict. We use UserPublic model for response.
    return UserPublic(**current_user)