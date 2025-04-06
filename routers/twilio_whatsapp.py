"""
Router for handling incoming WhatsApp messages via Twilio webhook.
"""
import logging
from fastapi import APIRouter, Request, Response, Form, Depends, HTTPException
from twilio.twiml.messaging_response import MessagingResponse
from twilio.request_validator import RequestValidator # For signature validation
from typing import Annotated, Optional

import config # To access Twilio settings and command prefixes
import database # To query user based on WhatsApp number

logger = logging.getLogger(__name__)

router = APIRouter()

# Optional: Initialize RequestValidator globally if preferred
# validator = RequestValidator(config.TWILIO_AUTH_TOKEN) if config.TWILIO_AUTH_TOKEN else None

async def validate_twilio_request(request: Request):
    """Dependency to validate incoming Twilio request signature."""
    if not config.TWILIO_AUTH_TOKEN:
        logger.warning("TWILIO_AUTH_TOKEN not set, skipping Twilio request validation (INSECURE!).")
        return # Allow requests during local dev without token, but log warning

    validator = RequestValidator(config.TWILIO_AUTH_TOKEN)
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
        if 'X-Forwarded-Proto' in request.headers and ':443' in url:
            url = url.replace(':443', '')

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

        # Check for commands (Link, Card Add) - Although LINK shouldn't happen here ideally
        if message_body.upper().startswith(config.WHATSAPP_LINK_COMMAND_PREFIX + " "):
            # User is already linked, shouldn't send link code again
             twiml_response.message(f"¡Hola! Your WhatsApp number is already linked to the account {user_email}. You don't need to link it again. Let's chat!")
             logger.warning(f"User {user_id} sent LINK command but is already linked.")

        elif message_body.startswith(config.WHATSAPP_CARD_COMMAND_PREFIX):
            # Handle Card Creation command (Placeholder for now)
            term_to_add = message_body[len(config.WHATSAPP_CARD_COMMAND_PREFIX):].strip()
            if term_to_add:
                logger.info(f"User {user_id} requested card creation for: '{term_to_add}'")
                # TODO: Implement card creation logic using reusable functions
                #       Call functions extracted from routers/cards.py
                #       e.g., propose, validate, save
                twiml_response.message(f"Okay, I'll try to create a flashcard for '{term_to_add}'. (Feature coming soon!)")
            else:
                twiml_response.message(f"To add a card, use {config.WHATSAPP_CARD_COMMAND_PREFIX} followed by the word or phrase (e.g., '{config.WHATSAPP_CARD_COMMAND_PREFIX} hola').")

        else:
            # Handle regular chat message (Placeholder for now)
            logger.info(f"Passing message from User {user_id} to chat handler...")
            # TODO: Implement chat logic using reusable functions
            #       Call function extracted from routers/chat.py (needs user_id, message)
            #       Inject user's card context
            chatbot_reply = f"Received: '{message_body}'. Chat response coming soon!" # Placeholder reply
            twiml_response.message(chatbot_reply)

    else:
        # --- SCENARIO B: User is Unlinked ---
        logger.info(f"Sender {sender_id} is not linked to any user account.")

        # Check for LINK command
        if message_body.upper().startswith(config.WHATSAPP_LINK_COMMAND_PREFIX + " "):
            link_code = message_body[len(config.WHATSAPP_LINK_COMMAND_PREFIX):].strip().upper()
            logger.info(f"Received LINK command from {sender_id} with code: '{link_code}'")

            # TODO: Implement Link Code Verification
            #       1. Check the code against temporary storage (config.TEMP_CODE_STORAGE)
            #       2. If valid & not expired:
            #          - Get user_id associated with the code.
            #          - Call database.update_user_whatsapp_number(user_id, sender_id)
            #          - Remove code from storage.
            #          - Send success message.
            #       3. If invalid/expired:
            #          - Send error message.
            twiml_response.message(f"Received link code '{link_code}'. Verification coming soon!") # Placeholder

        else:
            # Initial Engagement / Prompt to Link
            # Simple version for now:
            welcome_message = (
                "¡Hola! Welcome to your AI Spanish learning partner. 🇪🇸\n\n"
                "I can help you practice conversations and explain grammar.\n\n"
                "To save flashcards and your progress, please link this chat to your free account:\n"
                f"1. Go to: [Your Web App URL - Add this to config later]\n" # Replace with actual URL
                "2. Login or Sign up (using your email).\n"
                "3. Go to your Profile/Settings page.\n"
                "4. Click 'Link WhatsApp' and get a code.\n"
                f"5. Send the code back here like this: `{config.WHATSAPP_LINK_COMMAND_PREFIX} 123456`\n\n"
                "Ready to chat a bit first?"
            )
            twiml_response.message(welcome_message)


    # Return the TwiML response
    # Make sure the content type is 'text/xml' as required by Twilio
    return Response(content=str(twiml_response), media_type="text/xml")