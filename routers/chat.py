# routers/chat.py
import logging
import uuid
import json
from typing import Dict, Any, Optional,List
import pprint
import os


from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
import database.crud as crud
import database.models as models
from core.config import settings
# Import the corrected utility function
from utils import load_prompt_from_template
from services.llm_handler import GeminiHandler
from schemas import ChatMessage, ExplainRequest, ExplainResponse, ExamplePair, ChatMessageCreate
# Import get_prompt ONLY if needed for /explain (or load explain prompt directly too)
from dependencies import get_current_active_user, get_llm, get_prompt
from sqlalchemy.ext.asyncio import AsyncSession
from database.session import get_db_session

import database.models as models

logger = logging.getLogger(__name__)
router = APIRouter()

HISTORY_LOOKBACK = 10 


@router.get("/chat-history", response_model=list[ChatMessage])
async def get_chat_history(
    db_session: AsyncSession = Depends(get_db_session),
    current_user: models.User = Depends(get_current_active_user),
    session_id: str = None,
    limit: int = HISTORY_LOOKBACK,
):
    """
    Fetches chat history for the authenticated user.
    Returns a structured response with chat messages.
    """
    user_id = current_user.id
    if not user_id: raise HTTPException(status_code=403, detail="Could not identify user.")
    logger.info(f"Fetching chat history for User ID {user_id} with session ID {session_id}")

    if session_id is None:
        # If no session ID provided, generate a new one
        session_id = str(uuid.uuid4())
        logger.info(f"No session ID provided. Generated new session ID: {session_id}")
    # Fetch chat history from the database

    chat_history = await crud.get_chat_history(db_session=db_session,user_id=user_id, session_id=session_id, limit=limit)
    if chat_history is None:
        logger.error(f"Failed to fetch chat history for User ID {user_id}.")
        raise HTTPException(status_code=500, detail="Failed to fetch chat history.")
    return chat_history


@router.post("/chat", response_model=ChatMessage)
async def chat_endpoint(
    request_data: ChatMessage,
    current_user: models.User = Depends(get_current_active_user),
    llm_handler: GeminiHandler = Depends(get_llm),
    db_session: AsyncSession = Depends(get_db_session)
    
):
# --- 1. Stores incoming messages in the database.
# --- 2. Constructs a promt consisting of the latest user message, the system prompt, and the user's flashcards.
# --- 2. Sends the prompt to the LLM and receives a response.
# --- 3. Stores the LLM response or an Error in the database.
# --- 4. Fetches the LLM response from the database to have the timestamp and return it to the user.


    #---get user
    user_id = current_user.id  
    user_message = request_data.content
    role= "user" # Default role for user messages
    session_id= request_data.session_id
    if not user_id: raise HTTPException(status_code=403, detail="Could not identify user.")
    logger.info(f"Received chat message from User ID {user_id}: '{user_message[:50]}...'")
    
    # --- Store User Message ---
    chat_message = ChatMessageCreate(
    user_id=user_id,
    session_id=session_id,
    role=role,
    content=user_message)

    store_user_message = await crud.add_chat_message(chat_message=chat_message, db_session=db_session)

    logger.debug(f"Stored user message for User ID {user_id}: {store_user_message}")

    if store_user_message is None: 
        logger.error(f"Failed to store user message for User ID {user_id}.")
        raise HTTPException(status_code=500, detail="Failed to store user message.")
    
    # --- Fetch Chat History amd extract role and message content to build prompt ---
    chat_history: list[models.ChatMessage] = await crud.get_chat_history(db_session=db_session,user_id=user_id, session_id=session_id, limit=HISTORY_LOOKBACK)
    formatted_history= []
    
    logger.debug(f"Fetched chat history for User ID {user_id}: {chat_history}")
    for message in chat_history:
        formatted_history.append({
            'role': message.role,
            'parts': [{'text': message.content}]
        })



    # --- Load System Prompt Template Directly ---
    system_prompt_template_content = "(Error: Template not loaded)"
    try:
        system_prompt_template_path = settings.SYSTEM_PROMPT_TEMPLATE
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
        user_notes: list[models.Note] = await crud.get_all_notes_for_user(user_id,db_session=db_session)
        learned_sentences = [note.field1.strip() for note in user_notes ]
        logger.debug(f"Extracted learned_sentences list for user {user_id}: {learned_sentences}")

        MAX_LEARNED_SENTENCES = 50 # Limit number of cards sent in context
        if learned_sentences:
             sentences_to_use = learned_sentences[:MAX_LEARNED_SENTENCES]
             # Format the list clearly for the prompt
             formatted_card_list = "START OF MY KNOWN SENTENCES:\n" + "\n".join(f"- {s}" for s in sentences_to_use) + "\nEND OF MY KNOWN SENTENCES."
             logger.info(f"User {user_id} has {len(user_notes)} cards total. Formatted {len(sentences_to_use)} sentences.")
             logger.debug(f"Generated formatted_card_list: {formatted_card_list[:100]}...")
        else:
             formatted_card_list = "(No flashcards with content found)" # Correct fallback
             logger.warning(f"User {user_id} has {len(user_notes)} cards, but no non-empty 'front' fields found.")

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
              ]
        complete_constructed_message=conversation_context+formatted_history


        logger.debug(f"Sending the following context structure to Gemini for user {user_id}:")
        logger.debug(pprint.pformat(complete_constructed_message)) # Log final context

        response = await model.generate_content_async(contents=complete_constructed_message)

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


        # --- Store AI Response ---
        ai_message=ChatMessageCreate(
            user_id=user_id,
            session_id=session_id,
            role="model", # Role for AI response
            content=ai_reply,
            message_type="chat" # Type of message)
        )
        reply = await crud.add_chat_message(chat_message=ai_message, db_session=db_session)
        logger.debug(f"Stored AI message for User ID {user_id}: {ai_message}")

        
        return reply

    except HTTPException as http_exc:
        raise http_exc # Re-raise specific HTTP exceptions
    except Exception as e:
        logger.error(f"Error during LLM chat interaction for User ID {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An error occurred communicating with the AI: {e}")


# --- Explain Endpoint ---
# Use the *new* ExplainResponse for the response_model
@router.post("/explain", response_model=ExplainResponse)
async def explain_endpoint(
    request_data: ExplainRequest,
    current_user: dict = Depends(get_current_active_user),
    llm_handler: GeminiHandler = Depends(get_llm),
    teacher_prompt: str = Depends(get_prompt("teacher_prompt"))
):
    """
    Explains a topic using the LLM. Parses the LLM response to extract
    explanation text and structured examples. Requires authentication.
    """
    user_id = current_user.id
    topic = request_data.topic
    context = request_data.context
    if not user_id: raise HTTPException(status_code=403, detail="Could not identify user.")
    logger.info(f"Received explanation request from User ID {user_id} for topic: '{topic}'")

    # Format the prompt (no changes needed here)
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
        logger.debug(f"LLM Raw Explanation for User ID {user_id}, Topic '{topic}': '{response_text}'") # Log full raw response for debug

        if not response_text or response_text.startswith("(Response blocked"):
             logger.error(f"LLM returned empty/blocked response for explanation. Topic: {topic}. Response: {response_text}")
             raise HTTPException(status_code=500, detail=f"AI returned an empty or blocked response.") # Simplified detail

        # --- PARSING AND STRUCTURING LOGIC ---
        explanation_content: Optional[str] = None
        example_list: Optional[List[ExamplePair]] = None
        parsed_successfully = False

        try:
            # 1. Clean the response text (remove markdown fences, etc.)
            response_text_cleaned = response_text.strip()
            # Handle ```json ... ``` and ``` ... ```
            if response_text_cleaned.startswith("```json"):
                response_text_cleaned = response_text_cleaned[7:-3].strip()
            elif response_text_cleaned.startswith("```"):
                 response_text_cleaned = response_text_cleaned[3:-3].strip()

            # Attempt to find JSON object boundaries (more robust than just first/last brace)
            # Look for the first '{' and the last '}'
            start_brace = response_text_cleaned.find('{')
            end_brace = response_text_cleaned.rfind('}')

            if start_brace != -1 and end_brace != -1 and end_brace > start_brace:
                json_string = response_text_cleaned[start_brace : end_brace + 1]
            else:
                # If no clear braces, maybe the whole thing is JSON? Or maybe it's just text.
                json_string = response_text_cleaned # Assume it might be the whole string

            # 2. Attempt to parse the cleaned string as JSON
            parsed_data = json.loads(json_string)

            # 3. Validate the PARSED structure (check types)
            if isinstance(parsed_data, dict):
                explanation_content = parsed_data.get("explanation_text")
                raw_examples = parsed_data.get("examples")

                if isinstance(explanation_content, str):
                    # Explanation text looks valid
                    if isinstance(raw_examples, list):
                        # Examples key exists and is a list, try to build ExamplePair list
                        valid_examples = []
                        for item in raw_examples:
                            if isinstance(item, dict) and "spanish" in item and "english" in item:
                                try:
                                    # Validate/create ExamplePair to ensure types
                                    valid_examples.append(ExamplePair(**item))
                                except Exception as pair_exc:
                                     logger.warning(f"Skipping invalid example item during parsing: {item}. Error: {pair_exc}")
                                     continue # Skip this invalid example item
                            else:
                                logger.warning(f"Skipping non-dict or incomplete example item: {item}")
                        example_list = valid_examples if valid_examples else None # Assign if list isn't empty after validation
                        parsed_successfully = True # We got text and potentially valid examples
                    elif raw_examples is None:
                         # Examples key is explicitly null or missing, which is fine
                         example_list = None
                         parsed_successfully = True # We got the text part
                    else:
                        # Examples key exists but isn't a list - invalid format
                         logger.warning(f"Parsed 'examples' field is not a list. Type: {type(raw_examples)}. Raw: {response_text}")
                else:
                    # explanation_text key missing or not a string
                    logger.warning(f"Parsed JSON missing 'explanation_text' string. Raw: {response_text}")
            else:
                 # The parsed data wasn't even a dictionary
                 logger.warning(f"Parsed JSON is not a dictionary. Type: {type(parsed_data)}. Raw: {response_text}")

        except json.JSONDecodeError:
            logger.warning(f"Failed to parse LLM explanation as JSON. Raw: {response_text}")
            # Keep explanation_content as None, handled by fallback below
        except Exception as parse_exc:
             logger.error(f"Unexpected error during explanation parsing/validation: {parse_exc}", exc_info=True)
             # Keep explanation_content as None, handled by fallback below

        # --- Fallback Logic ---
        if not parsed_successfully:
            # Parsing failed or structure was invalid.
            # Use the ORIGINAL, unprocessed response_text as the explanation.
            # Set examples to None.
            logger.warning(f"Explanation structure parsing failed or incomplete. Returning raw text for topic '{topic}'.")
            explanation_content = response_text # Fallback to the raw LLM output
            example_list = None

        # Ensure we always have some explanation text (even if it's the raw fallback)
        if not explanation_content:
            logger.error(f"Failed to extract any explanation content for topic '{topic}'. Raw: {response_text}")
            raise HTTPException(status_code=500, detail="Failed to process the explanation response from AI.")

        # 4. Construct and return the structured response
        return ExplainResponse(
            topic=topic,
            explanation_text=explanation_content,
            examples=example_list
        )

    except HTTPException as http_exc:
         # Re-raise specific HTTP exceptions (like from LLM safety blocks)
         raise http_exc
    except Exception as e:
        # Catch any other unexpected errors during the process
        logger.error(f"Error during LLM explanation generation for User ID {user_id}, Topic '{topic}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An error occurred generating the explanation.")