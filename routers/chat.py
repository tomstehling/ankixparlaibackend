import uuid
import json
import logging
from typing import Dict, Any, List

from fastapi import APIRouter, HTTPException, Depends

from llm_handler import GeminiHandler
from models import ChatMessage, ChatResponse, ExplainRequest, ExplainResponse
from dependencies import get_llm, get_prompt, get_chat_sessions, get_learned_sentences # Import dependencies

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    payload: ChatMessage,
    llm_handler: GeminiHandler = Depends(get_llm),
    system_prompt: str = Depends(get_prompt("system_prompt")),
    chat_sessions_store: Dict[str, Any] = Depends(get_chat_sessions),
    learned_sentences: List[str] = Depends(get_learned_sentences) # Get learned sentences if needed
):
    """Handles receiving a chat message and returning the AI's reply."""
    logger.info(f"--- Entering /chat endpoint ---")
    logger.info(f"Received chat message for session: {payload.session_id}")

    session_id = payload.session_id
    user_message = payload.message

    chat_session = None
    if session_id and session_id in chat_sessions_store:
        logger.info(f"Using existing chat session: {session_id}")
        chat_session = chat_sessions_store[session_id]
    else:
        logger.info("No valid session ID provided or found, creating new session.")
        session_id = str(uuid.uuid4())
        try:
            # Decide if/how learned_sentences should influence the initial prompt
            # Maybe use only recent ones or none at all if context is sufficient
            formatted_system_prompt = system_prompt.format(
                 learned_vocabulary="\n".join(learned_sentences[-20:]) # Example usage
            )
            chat_session = llm_handler.create_chat_session(formatted_system_prompt)
            if not chat_session:
                 raise Exception("LLM Handler failed to return a valid chat session object.")
            chat_sessions_store[session_id] = chat_session
            logger.info(f"New chat session created with ID: {session_id}")
        except Exception as e:
            logger.error(f"Failed to create new chat session: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Server error: Could not create chat session.")

    if chat_session is None:
         logger.error(f"Critical: chat_session is None for session {session_id} before sending message.")
         raise HTTPException(status_code=500, detail="Internal Server Error: Chat session invalid")

    try:
        logger.info(f"Sending message to LLM for session {session_id}...")
        ai_reply = await llm_handler.send_chat_message(chat_session, user_message)
        logger.info(f"Received reply from LLM for session {session_id}")

        if ai_reply is None or ai_reply.startswith("(Response blocked"):
            logger.warning(f"LLM Handler returned None/blocked for session: {session_id}. Reply: {ai_reply}")
            ai_reply = ai_reply or "(Sorry, the AI did not provide a response. Please try again.)"

        return ChatResponse(reply=ai_reply, session_id=session_id)

    except Exception as e:
        logger.error(f"Error during LLM call in /chat for session {session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error generating chat response: {e}")


@router.post("/explain", response_model=ExplainResponse)
async def explain_endpoint(
    explain_request: ExplainRequest,
    llm_handler: GeminiHandler = Depends(get_llm),
    teacher_prompt: str = Depends(get_prompt("teacher_prompt"))
):
    """Handles receiving a query for explanation. Returns structured JSON."""
    logger.info(f"--- Entering /explain endpoint ---")
    topic_requested = explain_request.topic
    logger.info(f"Received explanation request for topic: '{topic_requested}'")

    try:
        formatted_prompt = teacher_prompt.format(
            topic=topic_requested,
            context=explain_request.context or "No specific chat context provided."
        )
        logger.info("Formatted prompt prepared for LLM.")
    except KeyError as e:
         logger.error(f"KeyError during teacher_prompt.format(): Missing key {e}.")
         raise HTTPException(status_code=500, detail=f"Server config error: Prompt key error {e}")
    except Exception as e:
         logger.error(f"Error during prompt formatting: {e}", exc_info=True)
         raise HTTPException(status_code=500, detail="Server error formatting prompt.")

    try:
        logger.info(f"Sending explanation request to LLM for '{topic_requested}'...")
        llm_response_text = await llm_handler.generate_one_off(formatted_prompt)
        logger.info(f"Received raw explanation response from LLM Handler.")

        if not llm_response_text or llm_response_text.startswith("(Response blocked"):
            logger.warning(f"LLM response empty or blocked for topic '{topic_requested}'. Response: {llm_response_text}")
            raise HTTPException(status_code=502, detail=f"AI response was empty or blocked: {llm_response_text}")

        try:
            response_text_cleaned = llm_response_text.strip()
            # Standardize JSON cleaning
            if response_text_cleaned.startswith("```json"):
                response_text_cleaned = response_text_cleaned[7:-3].strip()
            elif response_text_cleaned.startswith("```"):
                 response_text_cleaned = response_text_cleaned[3:-3].strip()
            elif response_text_cleaned.startswith("{") and response_text_cleaned.endswith("}"):
                 pass # Looks like valid JSON already
            else:
                 logger.warning(f"LLM response might not be clean JSON. Raw: {llm_response_text}")
                 # Attempt parsing anyway, might fail

            parsed_data = json.loads(response_text_cleaned)
            logger.info("Successfully parsed JSON response from LLM.")

            if "explanation_text" not in parsed_data:
                logger.error(f"LLM JSON response missing 'explanation_text'. Raw: {llm_response_text}")
                raise ValueError("LLM response missing required 'explanation_text' key.")

            explanation_text = parsed_data["explanation_text"]
            examples = parsed_data.get("examples", [])

            first_example_spanish = None
            first_example_english = None

            if isinstance(examples, list) and len(examples) > 0:
                first_example = examples[0]
                if isinstance(first_example, dict) and "spanish" in first_example and "english" in first_example:
                    first_example_spanish = first_example["spanish"]
                    first_example_english = first_example["english"]
                    logger.info("Extracted first example sentence pair.")
                else:
                    logger.warning(f"First item in 'examples' list has incorrect format: {first_example}. Raw: {llm_response_text}")
            else:
                 logger.info("No valid examples provided in 'examples' list.")

            return ExplainResponse(
                explanation_text=explanation_text,
                topic=topic_requested,
                example_spanish=first_example_spanish,
                example_english=first_example_english
            )

        except json.JSONDecodeError as json_err:
            logger.error(f"Failed to parse JSON from LLM response in /explain: {json_err}")
            logger.error(f"LLM Raw Response was: {llm_response_text}")
            raise HTTPException(status_code=500, detail="Failed to parse explanation structure from AI.")
        except ValueError as val_err:
             logger.error(f"LLM JSON response validation error in /explain: {val_err}")
             logger.error(f"LLM Raw Response was: {llm_response_text}")
             raise HTTPException(status_code=500, detail=f"Invalid explanation structure from AI: {val_err}")
        except Exception as e:
             logger.error(f"Unexpected error processing LLM response: {e}", exc_info=True)
             raise HTTPException(status_code=500, detail="Server error processing AI response.")

    except HTTPException as http_exc: raise http_exc
    except Exception as e:
        logger.error(f"Error during LLM call in /explain for topic '{topic_requested}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error generating explanation: {e}")