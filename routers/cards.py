import json
import logging
import time
# import math # Not used in the current grading logic, keep if needed later

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

import database
from llm_handler import GeminiHandler
from models import (
    ProposeSentenceRequest, ValidateTranslateRequest, SaveCardRequest,
    DueCardsResponse, CardGradeRequest, CardPublic
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

# --- Card Creation Endpoints ---

@router.post("/propose_sentence", response_class=JSONResponse)
async def propose_sentence_endpoint(
    request_data: ProposeSentenceRequest,
    current_user: dict = Depends(get_current_active_user),
    llm_handler: GeminiHandler = Depends(get_llm),
    sentence_proposer_prompt: str = Depends(get_prompt("sentence_proposer_prompt"))
):
    """Proposes a simple Spanish sentence using the target word. Requires authentication."""
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
            elif response_text_cleaned.startswith("{") and response_text_cleaned.endswith("}"):
                 pass
            else:
                 logger.warning(f"Proposal response might not be clean JSON. Raw: {response_text}")

            response_data = json.loads(response_text_cleaned)

            if "proposed_spanish" not in response_data or "proposed_english" not in response_data:
                 logger.error(f"LLM response missing required keys (propose). Raw: {response_text}")
                 raise ValueError("LLM response missing required keys (proposed_spanish, proposed_english).")

            response_data["target_word"] = target_word # Add target word back for context if needed
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
    request_data: ValidateTranslateRequest,
    current_user: dict = Depends(get_current_active_user),
    llm_handler: GeminiHandler = Depends(get_llm),
    sentence_validator_prompt: str = Depends(get_prompt("sentence_validator_prompt"))
):
    """Validates/corrects ('es') or translates ('en') the sentence. Requires authentication."""
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
            elif response_text_cleaned.startswith("{") and response_text_cleaned.endswith("}"):
                 pass
            else:
                 logger.warning(f"Validation response might not be clean JSON. Raw: {response_text}")

            response_data = json.loads(response_text_cleaned)

            required_keys = ["final_spanish", "final_english", "is_valid", "feedback"]
            missing_keys = [key for key in required_keys if key not in response_data]
            if missing_keys:
                logger.error(f"LLM response missing required keys (validate): {missing_keys}. Raw: {response_text}")
                raise ValueError(f"LLM response missing required keys: {missing_keys}")

            # Handle boolean conversion robustly
            is_valid_raw = response_data.get("is_valid")
            if isinstance(is_valid_raw, bool):
                pass # Already a boolean
            elif isinstance(is_valid_raw, str):
                 valid_str = is_valid_raw.lower()
                 if valid_str == 'true': response_data['is_valid'] = True
                 elif valid_str == 'false': response_data['is_valid'] = False
                 else: raise ValueError("LLM response 'is_valid' key is not a recognizable boolean string.")
            else:
                 raise ValueError("LLM response 'is_valid' key is not a boolean or recognizable boolean string.")

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
    request_data: SaveCardRequest,
    current_user: dict = Depends(get_current_active_user)
):
    """Saves the final card to the database for the logged-in user. Requires authentication."""
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


# --- SRS Endpoints ---

@router.get("/due", response_model=DueCardsResponse)
async def get_due_cards_for_user(
    limit: int = 20, # Optional query parameter for max cards
    current_user: dict = Depends(get_current_active_user)
):
    """Retrieves cards due for review for the current user."""
    user_id = current_user.get("id")
    logger.info(f"Fetching due cards for User ID {user_id} (limit {limit})...")
    try:
        due_cards_data = database.get_due_cards(user_id, limit=limit)
        due_cards = [CardPublic(**card) for card in due_cards_data]
        return DueCardsResponse(cards=due_cards)
    except Exception as e:
        logger.exception(f"Error retrieving due cards for User ID {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve due cards.")


@router.post("/{card_id}/grade", status_code=status.HTTP_204_NO_CONTENT)
async def grade_card(
    card_id: int,
    grade_data: CardGradeRequest,
    current_user: dict = Depends(get_current_active_user)
):
    """Updates the SRS state of a card based on the user's grade. Requires authentication."""
    user_id = current_user.get("id")
    grade = grade_data.grade
    logger.info(f"Received grade '{grade}' for Card ID {card_id} from User ID {user_id}")

    # 1. Fetch the current card state (ensure it belongs to the user)
    # Ensure get_card_by_id fetches necessary SRS fields (status, interval, ease, learning_step)
    card_data = database.get_card_by_id(card_id, user_id)
    if not card_data:
        logger.warning(f"Grade attempt failed: Card ID {card_id} not found or doesn't belong to User ID {user_id}.")
        raise HTTPException(status_code=404, detail="Card not found or access denied.")

    # Extract current SRS parameters (handle potential None or missing values)
    current_status = card_data.get("status", "new") # Default to 'new' if somehow missing
    current_interval = float(card_data.get("interval_days", 0.0))
    current_ease = float(card_data.get("ease_factor", config.DEFAULT_EASE_FACTOR)) # Use default ease from config
    learning_step_index = int(card_data.get("learning_step", 0)) # Assume 0 if not stored

    # --- Simple SRS Logic ---
    now = int(time.time())
    seconds_per_day = 86400
    seconds_per_minute = 60

    new_status = current_status
    new_interval = current_interval
    new_ease = current_ease
    next_due = now # Default to now
    new_learning_step = learning_step_index # Keep track of the new step

    if current_status == 'new' or current_status == 'learning' or current_status == 'lapsed': # Treat lapsed like learning
        if grade == 'again':
            # Repeat first learning step (or stay on current step if preferred)
            new_learning_step = 0
            step_minutes = LEARNING_STEPS_MINUTES[new_learning_step]
            next_due = now + step_minutes * seconds_per_minute
            new_status = 'learning' # Ensure status is learning
        elif grade == 'good':
            new_learning_step = learning_step_index + 1
            if new_learning_step >= len(LEARNING_STEPS_MINUTES):
                # Graduate to review
                new_status = 'review'
                new_interval = 1.0 # Start with 1 day interval (or config.INITIAL_REVIEW_INTERVAL)
                next_due = now + int(new_interval * seconds_per_day)
                new_learning_step = 0 # Reset learning step upon graduation
            else:
                # Next learning step
                step_minutes = LEARNING_STEPS_MINUTES[new_learning_step]
                next_due = now + step_minutes * seconds_per_minute
                new_status = 'learning' # Ensure status is learning
        elif grade == 'easy':
            # Graduate immediately to easy interval
            new_status = 'review'
            new_interval = DEFAULT_EASY_INTERVAL_DAYS
            next_due = now + int(new_interval * seconds_per_day)
            # Optionally increase ease factor here too
            # new_ease = max(new_ease, current_ease + 0.15) # Ensure ease increases or stays same
            new_learning_step = 0 # Reset learning step

    elif current_status == 'review':
        if grade == 'again':
            # Lapse - reset interval based on multiplier, decrease ease, back to learning
            new_status = 'learning' # Mark as learning (lapsed state isn't strictly needed if handled here)
            new_ease = max(MIN_EASE_FACTOR, current_ease - 0.20) # Decrease ease
            new_interval = current_interval * LAPSE_INTERVAL_MULTIPLIER # Often 0, meaning restart
            new_learning_step = 0 # Go back to first learning step
            step_minutes = LEARNING_STEPS_MINUTES[new_learning_step]
            next_due = now + step_minutes * seconds_per_minute
        elif grade == 'good':
            # Correct review - increase interval based on ease and modifier
            new_status = 'review'
            new_interval = current_interval * current_ease * DEFAULT_INTERVAL_MODIFIER
            # Apply fuzz? Optional.
            next_due = now + int(new_interval * seconds_per_day)
            # Small ease bump? Optional.
            # new_ease = current_ease + 0.05
            new_learning_step = 0 # Stays 0 for review cards
        elif grade == 'easy':
            # Easy review - increase interval significantly, increase ease
            new_status = 'review'
            # Use config.EASY_BONUS multiplier (e.g., 1.3)
            easy_bonus = getattr(config, 'EASY_BONUS', 1.3)
            new_interval = current_interval * current_ease * DEFAULT_INTERVAL_MODIFIER * easy_bonus
            new_ease = current_ease + 0.15 # Increase ease more for easy
            next_due = now + int(new_interval * seconds_per_day)
            new_learning_step = 0 # Stays 0 for review cards

    # --- End Simple SRS Logic ---

    # Ensure interval and ease have minimums/maximums if necessary
    new_interval = max(0.01, new_interval) # Prevent zero or negative intervals after graduation
    new_ease = max(MIN_EASE_FACTOR, new_ease) # Ensure ease doesn't drop below minimum

    # Update the card in the database
    success = database.update_card_srs(
        card_id=card_id,
        user_id=user_id,
        new_status=new_status,
        new_due_timestamp=next_due,
        new_interval_days=new_interval,
        new_ease_factor=new_ease,
        new_learning_step=new_learning_step # Pass the updated learning step
    )

    if not success:
        logger.error(f"Failed to update SRS state for Card ID {card_id} in database.")
        raise HTTPException(status_code=500, detail="Failed to update card state.")

    logger.info(f"Successfully updated Card ID {card_id}. New state: Status='{new_status}', Due='{next_due}', Interval='{new_interval:.2f}', Ease='{new_ease:.2f}', Step='{new_learning_step}'")
    # Return 204 No Content on success (FastAPI handles None return for 204)
    return None