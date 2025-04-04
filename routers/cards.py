import json
import logging
import time
import sqlite3 # Import sqlite3 for specific error handling
# import math # Not used in the current grading logic, keep if needed later
from typing import List # Ensure List is imported

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse, Response # Added Response for 204

import database
from llm_handler import GeminiHandler # Assuming this exists and is correct
from models import (
    ProposeSentenceRequest, ValidateTranslateRequest, SaveCardRequest,
    DueCardsResponse, CardGradeRequest, CardPublic, CardUpdate # Import CardUpdate
)
from dependencies import get_current_active_user, get_llm, get_prompt
import config # Import config to access SRS constants

logger = logging.getLogger(__name__)
router = APIRouter()

# --- SRS Constants (from config) ---
LEARNING_STEPS_MINUTES = getattr(config, 'LEARNING_STEPS_MINUTES', [1, 10]) # Default: 1 min, 10 min
DEFAULT_EASY_INTERVAL_DAYS = getattr(config, 'DEFAULT_EASY_INTERVAL_DAYS', 4.0) # Default: 4 days
MIN_EASE_FACTOR = getattr(config, 'MIN_EASE_FACTOR', 1.3) # Anki default min
LAPSE_INTERVAL_MULTIPLIER = getattr(config, 'LAPSE_INTERVAL_MULTIPLIER', 0.0) # Anki default: 0 (relearn from scratch)
DEFAULT_INTERVAL_MODIFIER = getattr(config, 'DEFAULT_INTERVAL_MODIFIER', 1.0) # Multiplier for 'good'
DEFAULT_EASE_FACTOR = getattr(config, 'DEFAULT_EASE_FACTOR', 2.5) # Default starting ease
EASY_BONUS = getattr(config, 'EASY_BONUS', 1.3) # Bonus multiplier for 'easy' reviews

# --- Card Creation Endpoints ---

@router.post("/propose_sentence", response_class=JSONResponse)
async def propose_sentence_endpoint(
    # ... (implementation as before) ...
    request_data: ProposeSentenceRequest,
    current_user: dict = Depends(get_current_active_user),
    llm_handler: GeminiHandler = Depends(get_llm),
    sentence_proposer_prompt: str = Depends(get_prompt("sentence_proposer_prompt"))
):
    # ... (implementation as before) ...
    user_id = current_user.get("id")
    logger.info(f"--- Entering /propose_sentence endpoint by User ID: {user_id} ---")
    logger.info(f"Received sentence proposal request for word: '{request_data.target_word}'")
    target_word = request_data.target_word
    formatted_prompt = sentence_proposer_prompt.format(target_word=target_word)
    try:
        logger.info(f"Sending proposal request to LLM for '{target_word}'...")
        response_text = await llm_handler.generate_one_off(formatted_prompt)
        logger.info(f"Received proposal response from LLM.")
        if not response_text or response_text.startswith("(Response blocked"):
             logger.error(f"LLM returned empty/blocked response for sentence proposal. Response: {response_text}")
             raise HTTPException(status_code=500, detail=f"AI returned an empty or blocked response: {response_text}")
        try:
            response_text_cleaned = response_text.strip()
            if response_text_cleaned.startswith("```json"):
                response_text_cleaned = response_text_cleaned[7:-3].strip()
            elif response_text_cleaned.startswith("```"):
                 response_text_cleaned = response_text_cleaned[3:-3].strip()
            start_brace = response_text_cleaned.find('{')
            end_brace = response_text_cleaned.rfind('}')
            if start_brace != -1 and end_brace != -1 and end_brace > start_brace:
                response_text_cleaned = response_text_cleaned[start_brace:end_brace+1]
            else:
                 logger.warning(f"Proposal response might not be clean JSON after initial cleaning. Raw: {response_text}")
                 pass
            response_data = json.loads(response_text_cleaned)
            if "proposed_spanish" not in response_data or "proposed_english" not in response_data:
                 logger.error(f"LLM response missing required keys (propose). Raw: {response_text}")
                 raise ValueError("LLM response missing required keys (proposed_spanish, proposed_english).")
            response_data["target_word"] = target_word
            return JSONResponse(content=response_data)
        except json.JSONDecodeError as json_err:
            logger.error(f"Failed to parse JSON (propose): {json_err}. Raw: {response_text}")
            raise HTTPException(status_code=500, detail="Failed to parse sentence proposal from AI.")
        except ValueError as val_err:
             logger.error(f"LLM response validation error (propose): {val_err}. Raw: {response_text}")
             raise HTTPException(status_code=500, detail=f"Invalid sentence proposal format from AI: {val_err}")
    except HTTPException as http_exc: raise http_exc
    except Exception as e:
        logger.error(f"Error during LLM call (propose): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error proposing sentence: {e}")


@router.post("/validate_translate_sentence", response_class=JSONResponse)
async def validate_translate_sentence_endpoint(
    # ... (implementation as before) ...
    request_data: ValidateTranslateRequest,
    current_user: dict = Depends(get_current_active_user),
    llm_handler: GeminiHandler = Depends(get_llm),
    sentence_validator_prompt: str = Depends(get_prompt("sentence_validator_prompt"))
):
    # ... (implementation as before) ...
    user_id = current_user.get("id")
    logger.info(f"--- Entering /validate_translate_sentence endpoint by User ID: {user_id} ---")
    logger.info(f"Received validation/translation request for word: '{request_data.target_word}'")
    formatted_prompt = sentence_validator_prompt.format(
        target_word=request_data.target_word,
        user_sentence=request_data.user_sentence,
        language=request_data.language
    )
    try:
        logger.info(f"Sending validation/translation request to LLM...")
        response_text = await llm_handler.generate_one_off(formatted_prompt)
        logger.info(f"Received validation/translation response from LLM.")
        if not response_text or response_text.startswith("(Response blocked"):
             logger.error(f"LLM returned empty/blocked response for validation/translation. Response: {response_text}")
             raise HTTPException(status_code=500, detail=f"AI returned an empty or blocked response: {response_text}")
        try:
            response_text_cleaned = response_text.strip()
            if response_text_cleaned.startswith("```json"):
                response_text_cleaned = response_text_cleaned[7:-3].strip()
            elif response_text_cleaned.startswith("```"):
                 response_text_cleaned = response_text_cleaned[3:-3].strip()
            start_brace = response_text_cleaned.find('{')
            end_brace = response_text_cleaned.rfind('}')
            if start_brace != -1 and end_brace != -1 and end_brace > start_brace:
                response_text_cleaned = response_text_cleaned[start_brace:end_brace+1]
            else:
                 logger.warning(f"Validation response might not be clean JSON after initial cleaning. Raw: {response_text}")
                 pass
            response_data = json.loads(response_text_cleaned)
            required_keys = ["final_spanish", "final_english", "is_valid", "feedback"]
            missing_keys = [key for key in required_keys if key not in response_data]
            if missing_keys:
                logger.error(f"LLM response missing required keys (validate): {missing_keys}. Raw: {response_text}")
                raise ValueError(f"LLM response missing required keys: {missing_keys}")
            is_valid_raw = response_data.get("is_valid")
            if isinstance(is_valid_raw, bool): pass
            elif isinstance(is_valid_raw, str):
                 valid_str = is_valid_raw.lower().strip()
                 if valid_str == 'true': response_data['is_valid'] = True
                 elif valid_str == 'false': response_data['is_valid'] = False
                 else: raise ValueError("LLM response 'is_valid' key is not a recognizable boolean string.")
            else: raise ValueError("LLM response 'is_valid' key is not a boolean or recognizable boolean string.")
            return JSONResponse(content=response_data)
        except json.JSONDecodeError as json_err:
            logger.error(f"Failed to parse JSON (validate): {json_err}. Raw: {response_text}")
            raise HTTPException(status_code=500, detail="Failed to parse sentence validation/translation from AI.")
        except ValueError as val_err:
             logger.error(f"LLM response validation error (validate): {val_err}. Raw: {response_text}")
             raise HTTPException(status_code=500, detail=f"Invalid validation/translation format from AI: {val_err}")
    except HTTPException as http_exc: raise http_exc
    except Exception as e:
        logger.error(f"Error during LLM call (validate): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error validating/translating sentence: {e}")


@router.post("/save_final_card", response_class=JSONResponse)
async def save_final_card_endpoint(
    # ... (implementation as before) ...
    request_data: SaveCardRequest,
    current_user: dict = Depends(get_current_active_user)
):
    # ... (implementation as before) ...
    user_id = current_user.get("id")
    logger.info(f"--- Entering /save_final_card endpoint by User ID: {user_id} ---")
    logger.info(f"Received request to save final card. Front: '{request_data.spanish_front[:30]}...'")
    try:
        card_id = database.add_new_card_to_db(
            user_id=user_id,
            front=request_data.spanish_front,
            back=request_data.english_back,
            tags=request_data.tags
        )
        if card_id:
            logger.info(f"Successfully saved new card to DB with ID: {card_id} for User ID: {user_id}")
            return JSONResponse(content={"success": True, "card_id": card_id, "message": "Card saved to database."})
        else:
            logger.error(f"Failed to save card to database for user {user_id}, add_new_card_to_db returned None.")
            raise HTTPException(status_code=500, detail="Failed to save card to database. Check server logs.")
    except Exception as e:
        logger.error(f"Error saving card to database for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Database error saving card: {e}")


# --- SRS & Card Management Endpoints ---

@router.get("/due", response_model=DueCardsResponse)
async def get_due_cards_for_user(
    # ... (implementation as before) ...
    limit: int = 20,
    current_user: dict = Depends(get_current_active_user)
):
    # ... (implementation as before) ...
    user_id = current_user.get("id")
    logger.info(f"Fetching due cards for User ID {user_id} (limit {limit})...")
    try:
        due_cards_data = database.get_due_cards(user_id, limit=limit)
        return DueCardsResponse(cards=due_cards_data)
    except Exception as e:
        logger.exception(f"Error retrieving due cards for User ID {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve due cards.")

@router.post("/{card_id}/grade", status_code=status.HTTP_204_NO_CONTENT)
async def grade_card(
    # ... (implementation as before) ...
    card_id: int,
    grade_data: CardGradeRequest,
    current_user: dict = Depends(get_current_active_user)
):
    # ... (implementation as before) ...
    user_id = current_user.get("id")
    grade = grade_data.grade
    logger.info(f"Received grade '{grade}' for Card ID {card_id} from User ID {user_id}")
    card_data = database.get_card_by_id(card_id, user_id)
    if not card_data:
        logger.warning(f"Grade attempt failed: Card ID {card_id} not found or doesn't belong to User ID {user_id}.")
        raise HTTPException(status_code=404, detail="Card not found or access denied.")
    current_status = card_data.get("status", "new")
    current_interval = float(card_data.get("interval_days", 0.0))
    current_ease = float(card_data.get("ease_factor", DEFAULT_EASE_FACTOR))
    learning_step_index = int(card_data.get("learning_step", 0))
    now = int(time.time())
    seconds_per_day = 86400
    seconds_per_minute = 60
    new_status = current_status
    new_interval = current_interval
    new_ease = current_ease
    next_due = now
    new_learning_step = learning_step_index
    if current_status in ('new', 'learning', 'lapsed'):
        if grade == 'again':
            new_learning_step = 0
            step_minutes = LEARNING_STEPS_MINUTES[new_learning_step]
            next_due = now + step_minutes * seconds_per_minute
            new_status = 'learning'
        elif grade == 'good':
            new_learning_step = learning_step_index + 1
            if new_learning_step >= len(LEARNING_STEPS_MINUTES):
                new_status = 'review'
                new_interval = 1.0
                next_due = now + int(new_interval * seconds_per_day)
                new_learning_step = 0
            else:
                step_minutes = LEARNING_STEPS_MINUTES[new_learning_step]
                next_due = now + step_minutes * seconds_per_minute
                new_status = 'learning'
        elif grade == 'easy':
            new_status = 'review'
            new_interval = DEFAULT_EASY_INTERVAL_DAYS
            next_due = now + int(new_interval * seconds_per_day)
            new_learning_step = 0
    elif current_status == 'review':
        if grade == 'again':
            new_status = 'learning'
            new_ease = max(MIN_EASE_FACTOR, current_ease - 0.20)
            new_interval = current_interval * LAPSE_INTERVAL_MULTIPLIER
            new_learning_step = 0
            step_minutes = LEARNING_STEPS_MINUTES[new_learning_step]
            next_due = now + step_minutes * seconds_per_minute
        elif grade == 'good':
            new_status = 'review'
            new_interval = current_interval * current_ease * DEFAULT_INTERVAL_MODIFIER
            next_due = now + int(new_interval * seconds_per_day)
            new_learning_step = 0
        elif grade == 'easy':
            new_status = 'review'
            new_interval = current_interval * current_ease * DEFAULT_INTERVAL_MODIFIER * EASY_BONUS
            new_ease = current_ease + 0.15
            next_due = now + int(new_interval * seconds_per_day)
            new_learning_step = 0
    new_interval = max(0.01, new_interval)
    new_ease = max(MIN_EASE_FACTOR, new_ease)
    success = database.update_card_srs(
        card_id=card_id, user_id=user_id, new_status=new_status, new_due_timestamp=next_due,
        new_interval_days=new_interval, new_ease_factor=new_ease, new_learning_step=new_learning_step
    )
    if not success:
        logger.error(f"Failed to update SRS state for Card ID {card_id} in database.")
        raise HTTPException(status_code=500, detail="Failed to update card state.")
    logger.info(f"Successfully updated Card ID {card_id}. New state: Status='{new_status}', Due='{next_due}', Interval='{new_interval:.2f}', Ease='{new_ease:.2f}', Step='{new_learning_step}'")
    return Response(status_code=status.HTTP_204_NO_CONTENT)

@router.get("/my-cards", response_model=List[CardPublic])
async def get_my_cards(
    # ... (implementation as before) ...
    current_user: dict = Depends(get_current_active_user)
):
    # ... (implementation as before) ...
    user_id = current_user.get("id")
    logger.info(f"Fetching all cards for User ID {user_id} via /my-cards endpoint.")
    try:
        user_cards_data = database.get_all_cards_for_user(user_id)
        return user_cards_data
    except sqlite3.Error as db_err:
        logger.exception(f"Database error retrieving all cards for User ID {user_id}: {db_err}")
        raise HTTPException(status_code=500, detail="Database error retrieving your cards.")
    except Exception as e:
        logger.exception(f"Unexpected error retrieving all cards for User ID {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve your cards.")

@router.delete("/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_card_endpoint(
    # ... (implementation as before) ...
    card_id: int,
    current_user: dict = Depends(get_current_active_user)
):
    # ... (implementation as before) ...
    user_id = current_user.get("id")
    logger.info(f"Received request to delete Card ID {card_id} from User ID {user_id}")
    try:
        deleted = database.delete_card(card_id=card_id, user_id=user_id)
        if not deleted:
            logger.warning(f"Delete failed for Card ID {card_id} by User ID {user_id}: Not found or not owner.")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card not found or you do not have permission to delete it.")
        else:
            logger.info(f"Successfully deleted Card ID {card_id} for User ID {user_id}.")
            return Response(status_code=status.HTTP_204_NO_CONTENT)
    except sqlite3.Error as db_err:
        logger.exception(f"Database error deleting Card ID {card_id} for User ID {user_id}: {db_err}")
        raise HTTPException(status_code=500, detail="Database error deleting card.")
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.exception(f"Unexpected error deleting Card ID {card_id} for User ID {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete card due to a server error.")


# --- NEW ENDPOINT for Updating a Card ---
@router.put("/{card_id}", response_model=CardPublic)
async def update_card_endpoint(
    card_id: int,
    card_update_data: CardUpdate,
    current_user: dict = Depends(get_current_active_user)
):
    """Updates the front, back, or tags for a specific card owned by the user."""
    user_id = current_user.get("id")
    logger.info(f"Received request to update Card ID {card_id} from User ID {user_id}")

    # Check if at least one field is being updated
    update_values = card_update_data.model_dump(exclude_unset=True) # Pydantic v2
    # For Pydantic v1: update_values = card_update_data.dict(exclude_unset=True)
    if not update_values:
         raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields provided for update. Please provide 'front', 'back', or 'tags'.",
        )

    try:
        # Attempt to update the card details in the database
        updated = database.update_card_details(
            card_id=card_id,
            user_id=user_id,
            front=card_update_data.front, # Pass None if not provided
            back=card_update_data.back,   # Pass None if not provided
            tags=card_update_data.tags    # Pass None if not provided
        )

        if not updated:
            # Check if the card exists at all for this user before returning 404
            existing_card = database.get_card_by_id(card_id, user_id)
            if not existing_card:
                 logger.warning(f"Update failed for Card ID {card_id} by User ID {user_id}: Card not found.")
                 raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Card not found.")
            else:
                 # This case might happen if update_card_details returns False for other reasons
                 logger.error(f"Update attempt failed for Card ID {card_id} by User ID {user_id}, but card exists. DB function issue?")
                 raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update card details.")

        # If update was successful, fetch the updated card data to return
        updated_card_data = database.get_card_by_id(card_id, user_id)
        if not updated_card_data:
             # This should ideally not happen if update succeeded, but handle defensively
             logger.error(f"Failed to retrieve Card ID {card_id} immediately after successful update.")
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Card updated but could not be retrieved.")

        logger.info(f"Successfully updated Card ID {card_id} for User ID {user_id}.")
        return CardPublic(**updated_card_data) # Validate and return the updated card

    except sqlite3.Error as db_err:
        logger.exception(f"Database error updating Card ID {card_id} for User ID {user_id}: {db_err}")
        raise HTTPException(status_code=500, detail="Database error updating card details.")
    except HTTPException as http_exc:
        # Re-raise HTTPExceptions (like 404, 400)
        raise http_exc
    except Exception as e:
        logger.exception(f"Unexpected error updating Card ID {card_id} for User ID {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update card due to a server error.")