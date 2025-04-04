# routers/chat.py
import logging
import uuid
import json
from typing import Dict, Any
import pprint
import os

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse

import database
import config
# Import the corrected utility function
from utils import load_prompt_from_template
from llm_handler import GeminiHandler
from models import ChatMessage, ChatResponse, ExplainRequest, ExplainResponse
# Import get_prompt ONLY if needed for /explain (or load explain prompt directly too)
from dependencies import get_current_active_user, get_llm, get_prompt

logger = logging.getLogger(__name__)
router = APIRouter()

# MAX_HISTORY_LENGTH = 10 # Uncomment and use if re-implementing history later

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    request_data: ChatMessage,
    current_user: dict = Depends(get_current_active_user),
    llm_handler: GeminiHandler = Depends(get_llm),
    # No prompt dependency needed here anymore
):
    """
    Handles chatbot conversation, incorporating user's flashcards into the system prompt.
    Requires authentication. Sends context + user message for each turn.
    """
    user_id = current_user.get("id")
    user_message = request_data.message
    if not user_id: raise HTTPException(status_code=403, detail="Could not identify user.")
    logger.info(f"Received chat message from User ID {user_id}: '{user_message[:50]}...'")

    # --- Load System Prompt Template Directly ---
    system_prompt_template_content = "(Error: Template not loaded)"
    try:
        system_prompt_template_path = config.SYSTEM_PROMPT_TEMPLATE
        logger.debug(f"Attempting to load template from: {system_prompt_template_path}")
        # Call the simple load function from utils
        system_prompt_template_content = load_prompt_from_template(system_prompt_template_path)
        if not system_prompt_template_content:
             raise ValueError("Loaded system prompt template is empty.")
        logger.debug(f"Successfully loaded template content (first 100 chars): {system_prompt_template_content[:100]}")
        # Check placeholder presence
        if "{learned_content}" not in system_prompt_template_content:
             logger.error("!!! Template file seems to be missing the {learned_content} placeholder !!!")
        else:
             logger.debug("Placeholder {learned_content} found in loaded template.")

    except FileNotFoundError:
        logger.error(f"System prompt template file not found at: {system_prompt_template_path}")
        raise HTTPException(status_code=500, detail="Internal server error: Chat template missing.")
    except Exception as e:
        logger.error(f"Failed to load system_prompt_template: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error: Cannot load chat configuration.")

    # --- Fetch User's Flashcards ---
    formatted_card_list = "(Error fetching flashcards)"
    try:
        user_cards = database.get_all_cards_for_user(user_id)
        learned_sentences = [card.get('front', '').strip() for card in user_cards if card.get('front') and card.get('front').strip()]
        logger.debug(f"Extracted learned_sentences list for user {user_id}: {learned_sentences}")

        MAX_LEARNED_SENTENCES = 50 # Limit number of cards sent in context
        if learned_sentences:
             sentences_to_use = learned_sentences[:MAX_LEARNED_SENTENCES]
             # Format the list clearly for the prompt
             formatted_card_list = "START OF MY KNOWN SENTENCES:\n" + "\n".join(f"- {s}" for s in sentences_to_use) + "\nEND OF MY KNOWN SENTENCES."
             logger.info(f"User {user_id} has {len(user_cards)} cards total. Formatted {len(sentences_to_use)} sentences.")
             logger.debug(f"Generated formatted_card_list: {formatted_card_list[:100]}...")
        else:
             formatted_card_list = "(No flashcards with content found)" # Correct fallback
             logger.warning(f"User {user_id} has {len(user_cards)} cards, but no non-empty 'front' fields found.")

    except Exception as db_err:
        logger.error(f"Failed to fetch/format flashcards for user {user_id}: {db_err}", exc_info=True)
        # formatted_card_list remains "(Error fetching flashcards)"

    # --- Format the final System Prompt ---
    final_system_prompt = "(Error: Formatting failed)"
    try:
        logger.debug("Attempting to format system prompt...")
        # Format the loaded template content with the generated card list string
        format_args = {"learned_content": formatted_card_list}
        logger.debug(f"Formatting with args: {format_args}")
        final_system_prompt = system_prompt_template_content.format(**format_args)
        logger.debug(f"Result of .format() (final_system_prompt, first 200 chars): {final_system_prompt[:200]}...")
        if "{learned_content}" in final_system_prompt:
             # This should not happen if format worked, but check anyway
             logger.error("!!! CRITICAL: Placeholder {learned_content} still present after .format() call!")
        else:
             logger.debug("Placeholder correctly replaced in final_system_prompt.")
    except KeyError as ke:
        logger.error(f"KeyError formatting system prompt. Check placeholder '{ke}'. Template was: {system_prompt_template_content[:100]}...")
        final_system_prompt = system_prompt_template_content # Fallback to unformatted
    except Exception as format_err:
         logger.error(f"Unexpected error formatting system prompt: {format_err}", exc_info=True)
         final_system_prompt = system_prompt_template_content # Fallback

    # --- Interact with LLM ---
    try:
        model = llm_handler.get_model()
        # Construct context as list of dicts
        conversation_context = [
            {'role': 'user', 'parts': [ {'text': final_system_prompt} ]}, # Send combined prompt+cards
            {'role': 'model', 'parts': [ {'text': "¡Claro! Entendido. Estoy listo para practicar contigo. ¿Qué quieres decir?"} ]}, # Simulate model ack
            {'role': 'user', 'parts': [ {'text': user_message} ]}, # Send current user message
        ]

        logger.debug(f"Sending the following context structure to Gemini for user {user_id}:")
        logger.debug(pprint.pformat(conversation_context)) # Log final context

        response = await model.generate_content_async(contents=conversation_context)

        # --- Safety Check & Response Extraction ---
        ai_reply = ""
        try:
            if not response.candidates:
                reason = "Unknown"; prompt_feedback = getattr(response, 'prompt_feedback', None)
                if prompt_feedback: reason = f"Reason: {prompt_feedback.block_reason}"
                logger.warning(f"Gemini response blocked for user {user_id}. {reason}")
                raise HTTPException(status_code=400, detail=f"Response blocked by safety filter. {reason}")
            # Ensure response.text exists before accessing
            ai_reply = response.text
        except ValueError as e: # Catch specific errors like blocked content
             logger.warning(f"Gemini value error for user {user_id}. Maybe blocked? Error: {e}")
             reason = "Blocked by safety filter (ValueError)"; prompt_feedback = getattr(response, 'prompt_feedback', None)
             if prompt_feedback: reason = f"Blocked by safety filter: {prompt_feedback.block_reason}"
             raise HTTPException(status_code=400, detail=reason)
        except AttributeError:
             logger.error(f"Gemini response structure unexpected. No 'text' attribute found. Response: {response}")
             raise HTTPException(status_code=500, detail="Received unexpected AI response structure.")


        logger.info(f"LLM Reply for User ID {user_id}: '{ai_reply[:50]}...'")
        # Return session_id as user_id string for potential client use (though not strictly needed now)
        return ChatResponse(reply=ai_reply, session_id=str(user_id))

    except HTTPException as http_exc:
        raise http_exc # Re-raise specific HTTP exceptions
    except Exception as e:
        logger.error(f"Error during LLM chat interaction for User ID {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An error occurred communicating with the AI: {e}")


# --- Explain Endpoint ---
@router.post("/explain", response_model=ExplainResponse)
async def explain_endpoint(
    request_data: ExplainRequest,
    current_user: dict = Depends(get_current_active_user),
    llm_handler: GeminiHandler = Depends(get_llm),
    # Use Depends(get_prompt(...)) for teacher prompt
    teacher_prompt: str = Depends(get_prompt("teacher_prompt"))
):
    """Explains a topic using the LLM. Requires authentication."""
    user_id = current_user.get("id")
    topic = request_data.topic
    context = request_data.context
    if not user_id: raise HTTPException(status_code=403, detail="Could not identify user.")
    logger.info(f"Received explanation request from User ID {user_id} for topic: '{topic}'")

    # Format the prompt (assuming teacher_prompt is the loaded template string)
    try:
        full_prompt = teacher_prompt.format(topic=topic, context=context or "N/A")
    except KeyError as e:
         logger.error(f"KeyError formatting teacher prompt. Check placeholder '{e}'.")
         raise HTTPException(status_code=500, detail="Server configuration error (explanation prompt).")
    except Exception as e:
         logger.error(f"Error formatting teacher prompt: {e}", exc_info=True)
         raise HTTPException(status_code=500, detail="Server error processing explanation request.")

    try:
        response_text = await llm_handler.generate_one_off(full_prompt)
        logger.info(f"LLM Explanation for User ID {user_id}, Topic '{topic}': '{response_text[:100]}...'")

        if not response_text or response_text.startswith("(Response blocked"):
             logger.error(f"LLM returned empty/blocked response for explanation. Topic: {topic}. Response: {response_text}")
             raise HTTPException(status_code=500, detail=f"AI returned an empty or blocked response: {response_text}")

        # Attempt to parse the structured JSON response expected
        try:
            response_text_cleaned = response_text.strip()
            if response_text_cleaned.startswith("```json"): response_text_cleaned = response_text_cleaned[7:-3].strip()
            elif response_text_cleaned.startswith("```"): response_text_cleaned = response_text_cleaned[3:-3].strip()
            start_brace = response_text_cleaned.find('{'); end_brace = response_text_cleaned.rfind('}')
            if start_brace != -1 and end_brace != -1 and end_brace > start_brace:
                response_text_cleaned = response_text_cleaned[start_brace:end_brace+1]
            else: logger.warning(f"Explanation response might not be clean JSON. Raw: {response_text}")

            parsed_response = json.loads(response_text_cleaned)

            # Basic validation of expected keys
            required_keys = ["explanation_text", "example_spanish", "example_english"]
            if not all(k in parsed_response for k in required_keys):
                 logger.warning(f"LLM explanation missing expected keys {required_keys}. Raw: {response_text}. Returning raw text.")
                 return ExplainResponse(explanation_text=response_text, topic=topic, example_spanish=None, example_english=None)

            parsed_response['topic'] = topic # Ensure topic is included
            return ExplainResponse(**parsed_response)

        except json.JSONDecodeError:
            logger.warning(f"Failed to parse LLM explanation as JSON. Topic: {topic}. Raw: {response_text}. Returning raw text.")
            return ExplainResponse(explanation_text=response_text, topic=topic, example_spanish=None, example_english=None)

    except HTTPException as http_exc:
         raise http_exc # Re-raise HTTP exceptions (e.g., from LLM block)
    except Exception as e:
        logger.error(f"Error during LLM explanation generation for User ID {user_id}, Topic '{topic}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An error occurred generating the explanation: {e}")