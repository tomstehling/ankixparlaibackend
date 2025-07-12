"""
Router for handling incoming WhatsApp messages via Twilio webhook.
"""
import logging
import time # Added for expiry check
from fastapi import APIRouter, Request, Response, Form, Depends, HTTPException
from twilio.twiml.messaging_response import MessagingResponse
from twilio.request_validator import RequestValidator # For signature validation
from typing import Annotated, Optional

from core.config import settings
import database.database as database # To query user based on WhatsApp number

logger = logging.getLogger(__name__)

router = APIRouter()

# Optional: Initialize RequestValidator globally if preferred
# validator = RequestValidator(config.TWILIO_AUTH_TOKEN) if config.TWILIO_AUTH_TOKEN else None

async def validate_twilio_request(request: Request):
    """Dependency to validate incoming Twilio request signature."""
    if not settings.TWILIO_AUTH_TOKEN:
        logger.warning("TWILIO_AUTH_TOKEN not set, skipping Twilio request validation (INSECURE!).")
        return # Allow requests during local dev without token, but log warning

    validator = RequestValidator(settings.TWILIO_AUTH_TOKEN)
    try:
        form_ = await request.form()
        # Convert form_ MultiDict to simple Dict for validation
        form_dict = {k: v for k, v in form_.items()}
        url = str(request.url)
        # Twilio sends X-Twilio-Signature header
        signature = request.headers.get("X-Twilio-Signature", None)

        if not signature:
             logger.error("Missing X-Twilio-Signature header.")
             raise HTTPException(status_code=400, detail="Missing Twilio signature.")

        # Remove port for validation if running behind proxy like ngrok default behavior
        # Check both http and https common proxy headers
        forwarded_proto = request.headers.get('X-Forwarded-Proto')
        if forwarded_proto == 'https' and ':443' in url:
            url = url.replace(':443', '')
        elif forwarded_proto == 'http' and ':80' in url:
             url = url.replace(':80', '')

        logger.debug(f"Validating Twilio request: URL='{url}', Params='{form_dict}', Signature='{signature}'")

        if not validator.validate(url, form_dict, signature):
            logger.error("Twilio request signature validation failed.")
            raise HTTPException(status_code=403, detail="Invalid Twilio signature.")
        logger.debug("Twilio request signature validated successfully.")

    except Exception as e:
        logger.exception(f"Error during Twilio request validation: {e}")
        raise HTTPException(status_code=500, detail="Webhook validation error.")


@router.post(
    "/webhook",
    # dependencies=[Depends(validate_twilio_request)] # UNCOMMENT for production/when testing validation
)
async def handle_whatsapp_webhook(
    request: Request, # Needed for logging or potentially validation later
    From: Annotated[str, Form()], # User's WhatsApp number (e.g., whatsapp:+1...)
    Body: Annotated[str, Form()], # The message text
    # ProfileName: Annotated[Optional[str], Form()] = None, # Optional: User's WhatsApp profile name
    # Add other fields from Twilio if needed: https://www.twilio.com/docs/messaging/guides/webhook-request
):
    """
    Handles incoming WhatsApp messages from Twilio.
    Identifies the user, processes commands, or passes to chat logic.
    """
    twiml_response = MessagingResponse()
    message_body = Body.strip()
    sender_id = From # e.g., "whatsapp:+14155238886"

    logger.info(f"Received WhatsApp message from {sender_id}: '{message_body}'")

    # --- 1. Identify User ---
    user = database.get_user_by_whatsapp_number(sender_id)

    # --- 2. Process Message ---
    if user:
        # --- SCENARIO A: User is Linked ---
        user_id = user['id']
        user_email = user.get('email', 'Unknown Email')
        logger.info(f"User identified: ID={user_id}, Email={user_email}")

        # Check for LINK command (edge case, user already linked)
        if message_body.upper().startswith(settings.WHATSAPP_LINK_COMMAND_PREFIX + " "):
             twiml_response.message(f"¡Hola! Your WhatsApp number is already linked to the account {user_email}. You don't need to link it again. Let's chat!")
             logger.warning(f"User {user_id} ({sender_id}) sent LINK command but is already linked.")

        elif message_body.startswith(settings.WHATSAPP_CARD_COMMAND_PREFIX):
            # Handle Card Creation command (Placeholder)
            term_to_add = message_body[len(settings.WHATSAPP_CARD_COMMAND_PREFIX):].strip()
            if term_to_add:
                logger.info(f"User {user_id} requested card creation for: '{term_to_add}'")
                # TODO: Implement card creation logic using reusable functions
                twiml_response.message(f"Okay, I'll try to create a flashcard for '{term_to_add}'. (Feature coming soon!)")
            else:
                twiml_response.message(f"To add a card, use {settings.WHATSAPP_CARD_COMMAND_PREFIX} followed by the word or phrase (e.g., '{settings.WHATSAPP_CARD_COMMAND_PREFIX} hola').")

        else:
            # Handle regular chat message (Placeholder)
            logger.info(f"Passing message from User {user_id} to chat handler...")
            # TODO: Implement chat logic using reusable functions
            chatbot_reply = f"Received: '{message_body}'. Chat response coming soon!" # Placeholder reply
            twiml_response.message(chatbot_reply)

    else:
        # --- SCENARIO B: User is Unlinked ---
        logger.info(f"Sender {sender_id} is not linked to any user account.")

        # Check for LINK command
        link_prefix_upper = settings.WHATSAPP_LINK_COMMAND_PREFIX.upper() + " "
        if message_body.upper().startswith(link_prefix_upper):
            # Extract only the numeric code part
            code_part = message_body[len(link_prefix_upper):].strip()
            logger.info(f"Received LINK command from {sender_id} with code part: '{code_part}'")

            # Validate if it looks like our code format (e.g., 6 digits)
            if not code_part.isdigit() or len(code_part) != getattr(settings, 'LINK_CODE_LENGTH', 6):
                 logger.warning(f"Invalid code format received from {sender_id}: '{code_part}'")
                 twiml_response.message(f"Hmm, that code doesn't look right. Please make sure you enter the command '{settings.WHATSAPP_LINK_COMMAND_PREFIX}' followed by the {getattr(settings, 'LINK_CODE_LENGTH', 6)}-digit code from the website.")
            else:
                # --- Link Code Verification Logic ---
                code_info = settings.TEMP_CODE_STORAGE.get(code_part)
                current_time = time.time()

                if code_info and current_time < code_info.get("expires_at", 0):
                    user_id_to_link = code_info.get("user_id")
                    if not user_id_to_link:
                         logger.error(f"Valid code '{code_part}' found but missing user_id in storage.")
                         twiml_response.message("Sorry, there was an internal error processing your code. Please try requesting a new one.")
                    else:
                        logger.info(f"Valid code '{code_part}' found for User ID {user_id_to_link}. Attempting to link number {sender_id}.")
                        # Attempt to link the number in the database
                        success = database.update_user_whatsapp_number(user_id_to_link, sender_id)

                        if success:
                            # Remove code upon successful use
                            try:
                                del settings.TEMP_CODE_STORAGE[code_part]
                                logger.info(f"Removed used link code '{code_part}' from temporary storage.")
                            except KeyError:
                                logger.warning(f"Attempted to remove code '{code_part}' but it was already gone.") # Should not happen often

                            # Fetch user email for confirmation message
                            linked_user_info = database.get_user_by_id(user_id_to_link)
                            user_email = linked_user_info.get('email', 'your account') if linked_user_info else 'your account'

                            twiml_response.message(f"¡Perfecto! ✨ Your WhatsApp number is now linked to {user_email}. Let's start practicing!")
                            logger.info(f"Successfully linked {sender_id} to User ID {user_id_to_link}.")
                        else:
                            # DB update failed (e.g., number already linked to *another* account, caught by UNIQUE constraint)
                            logger.warning(f"Failed to link {sender_id} to User ID {user_id_to_link} in database (likely number already exists).")
                            twiml_response.message("Sorry, I couldn't link this number. It might already be linked to a different account. Please contact support if you need help.")
                            # Note: We don't remove the code here, maybe the user tries again from the correct account? Or maybe we should? Let's leave it for now.

                elif code_info: # Code exists but expired
                     logger.warning(f"Expired code '{code_part}' received from {sender_id}.")
                     twiml_response.message("This link code has expired. Please request a new one from your Profile page on the website.")
                     # Optionally remove expired code here
                     # try: del config.TEMP_CODE_STORAGE[code_part] except KeyError: pass
                else: # Code not found
                     logger.warning(f"Invalid code '{code_part}' received from {sender_id}.")
                     twiml_response.message(f"That code wasn't found or is incorrect. Please double-check the code from the website or request a new one. Remember to include '{settings.WHATSAPP_LINK_COMMAND_PREFIX}'.")

        else:
            # --- Initial Engagement / Prompt to Link ---
            # Use WEB_APP_BASE_URL from config
            base_url = settings.WEB_APP_BASE_URL
            profile_path = "/app/profile" # Assuming this will be the path to the profile page in Vue app

            welcome_message = (
                "¡Hola! Welcome to your AI Spanish learning partner. 🇪🇸\n\n"
                "I can help you practice conversations and explain grammar.\n\n"
                "To save flashcards and your progress, please link this chat to your free account:\n"
                f"1. Go to: {base_url}\n"
                "2. Login or Sign up (using your email).\n"
                f"3. Go to your Profile page (usually at {base_url}{profile_path}).\n"
                "4. Click 'Link WhatsApp' and get a code.\n"
                f"5. Send the code back here like this: `{settings.WHATSAPP_LINK_COMMAND_PREFIX} 123456`\n\n"
                "You can start chatting with me now, but linking is needed to save anything!"
            )
            twiml_response.message(welcome_message)


    # Return the TwiML response
    return Response(content=str(twiml_response), media_type="text/xml")