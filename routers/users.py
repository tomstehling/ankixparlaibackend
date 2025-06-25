"""
Router for user-related operations (e.g., profile, settings).
"""
import logging
import secrets
import time
from fastapi import APIRouter, Depends, HTTPException, status

import core.config as config
from schemas import UserPublic, WhatsappLinkCodeResponse
from dependencies import get_current_active_user

logger = logging.getLogger(__name__)
router = APIRouter()

def _generate_link_code() -> str:
    """Generates a secure random numeric code of configured length."""
    code_length = getattr(config, 'LINK_CODE_LENGTH', 6)
    if not isinstance(code_length, int) or code_length <= 0:
        code_length = 6 # Fallback to default
        logger.warning(f"Invalid LINK_CODE_LENGTH in config, defaulting to {code_length}.")

    max_value = 10**code_length
    numeric_code = secrets.randbelow(max_value)
    return f"{numeric_code:0{code_length}d}" # Pad with leading zeros if needed


@router.post("/me/whatsapp-link-code", response_model=WhatsappLinkCodeResponse)
async def generate_whatsapp_link_code(
    current_user: dict = Depends(get_current_active_user)
):
    """
    Generates a short-lived code for the authenticated user to link their WhatsApp number.

    The user should send this code via WhatsApp from the number they wish to link.
    """
    user_id = current_user.get("id")
    if not user_id:
        # This should technically be caught by get_current_active_user, but belt and suspenders
        logger.error("User ID missing in authenticated user data.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not identify authenticated user.",
        )

    # Check if already linked
    if current_user.get("whatsapp_number"):
         logger.warning(f"User {user_id} requested link code but is already linked to {current_user['whatsapp_number']}")
         raise HTTPException(
             status_code=status.HTTP_400_BAD_REQUEST,
             detail=f"Your account is already linked to a WhatsApp number ({current_user['whatsapp_number']}). Contact support if you need to change it.",
         )

    # Generate code
    numeric_code = _generate_link_code()
    expiry_timestamp = time.time() + config.LINK_CODE_EXPIRY_SECONDS

    # Store the code (use numeric part as key for easy lookup)
    # WARNING: Overwrites previous code if user requests again quickly. This is generally fine.
    config.TEMP_CODE_STORAGE[numeric_code] = {
        "user_id": user_id,
        "expires_at": expiry_timestamp
    }

    logger.info(f"Generated WhatsApp link code {numeric_code} for User ID {user_id}. Expires at {expiry_timestamp:.0f}.")

    # Construct the full code string for the user
    full_link_code = f"{config.WHATSAPP_LINK_COMMAND_PREFIX} {numeric_code}"

    return WhatsappLinkCodeResponse(
        link_code=full_link_code,
        expires_in_seconds=config.LINK_CODE_EXPIRY_SECONDS
    )

@router.get("/me", response_model=UserPublic)
async def read_users_me(current_user: dict = Depends(get_current_active_user)):
    """
    Returns the details of the currently authenticated user.
    """
    # We already have the user dict from the dependency.
    # Convert it to the UserPublic model to avoid leaking password hash etc.
    # Note: Ensure UserPublic includes all fields returned by get_user_by_id (like whatsapp_number)
    # if they are needed in the frontend profile.
    return UserPublic.model_validate(current_user)