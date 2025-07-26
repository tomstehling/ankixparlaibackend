import json
import logging
import time
import sqlite3 # Import sqlite3 for specific error handling
# import math
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse, Response


import database.crud as crud
import database.session as session
import database.models as models
from sqlalchemy.ext.asyncio import AsyncSession
from services.llm_handler import GeminiHandler
from schemas import (
    ProposeSentenceRequest, ValidateTranslateRequest, SaveCardRequest,
    DueCardsResponse, CardGradeRequest,
    NotePublic, 
    DueCardResponseItem,
    QuickAddRequest, QuickAddResponse, NoteContent,SRS

)
from dependencies import get_current_active_user, get_llm, get_prompt
from core.config import settings


logger = logging.getLogger(__name__)
router = APIRouter()

# --- SRS Constants (from config) ---
LEARNING_STEPS_MINUTES = getattr(settings, 'LEARNING_STEPS_MINUTES', [1, 10])
DEFAULT_EASY_INTERVAL_DAYS = getattr(settings, 'DEFAULT_EASY_INTERVAL_DAYS', 4.0)
MIN_EASE_FACTOR = getattr(settings, 'MIN_EASE_FACTOR', 1.3)
LAPSE_INTERVAL_MULTIPLIER = getattr(settings, 'LAPSE_INTERVAL_MULTIPLIER', 0.0)
DEFAULT_INTERVAL_MODIFIER = getattr(settings, 'DEFAULT_INTERVAL_MODIFIER', 1.0)
DEFAULT_EASE_FACTOR = getattr(settings, 'DEFAULT_EASE_FACTOR', 2.5)
EASY_BONUS = getattr(settings, 'EASY_BONUS', 1.3)


# --- Card/Note Creation Endpoints ---

@router.post("/propose_sentence", response_class=JSONResponse)
async def propose_sentence_endpoint(
    request_data: ProposeSentenceRequest,
    current_user: models.User = Depends(get_current_active_user),
    llm_handler: GeminiHandler = Depends(get_llm),
    sentence_proposer_prompt: str = Depends(get_prompt("sentence_proposer_prompt"))
):
    user_id = current_user.id
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
    request_data: ValidateTranslateRequest,
    current_user: models.User = Depends(get_current_active_user),
    llm_handler: GeminiHandler = Depends(get_llm),
    sentence_validator_prompt: str = Depends(get_prompt("sentence_validator_prompt"))
):
    # --- No changes needed based on Note/Card schema ---
    user_id = current_user.id
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


@router.post("/save_note", response_class=JSONResponse)
async def save_note(
    request_data: SaveCardRequest, # Keep input model, map fields below
    current_user: models.User= Depends(get_current_active_user),
    db_session: AsyncSession=Depends(session.get_db_session)
):
    """Saves the final Spanish/English pair as a Note with two Cards."""
    user_id = current_user.id
    logger.info(f"--- Entering /save_note endpoint by User ID: {user_id} ---")
    logger.info(f"Received request to save final note. Field1: '{request_data.spanish_front[:30]}...'")

    new_note=NoteContent(
        field1=request_data.spanish_front,  # Spanish front
        field2=request_data.english_back,   # English back
        tags=request_data.tags      # Tags as a space-separated string
    )

    try:
        note = await crud.add_note_with_cards(
            db_session=db_session,
            user_id=user_id,
            note_to_add = new_note
        )
        if note: # Check if note_id is not None
            logger.info(f"Successfully saved new Note to DB with ID: {note} (and its cards) for User ID: {user_id}")
            # Return the note_id instead of card_id
            return JSONResponse(content={"success": True, "note_id": note.id, "message": "Note and cards saved to database."})
        else:
            logger.error(f"Failed to save note to database for user {user_id}, add_note_with_cards returned None.")
            raise HTTPException(status_code=500, detail="Failed to save note to database. Check server logs.")
    except Exception as e:
        logger.error(f"Error saving note to database for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Database error saving note: {e}")


# --- SRS & Card/Note Management Endpoints ---

@router.get("/due", response_model=DueCardsResponse) # Use the new response model
async def get_due_cards_for_user(
    db_session: AsyncSession=Depends(session.get_db_session),
    limit: int = 20,
    current_user: models.User = Depends(get_current_active_user)
):
    """Fetches due cards for the user, including necessary note content for review."""
    user_id = current_user.id
    logger.info(f"Fetching due cards for User ID {user_id} (limit {limit})...")
    try:
        # Use the updated DB function which joins notes and cards
        due_cards_data: list[models.Card] = await crud.get_due_cards(db_session=db_session,user_id=user_id, limit=limit)
        # The data should now match the structure of DueCardResponseItem

        due_cards_response:DueCardsResponse=DueCardsResponse(cards=[])
        for card in due_cards_data:
            mapped_card=DueCardResponseItem(
                card_id=card.id,
                note_id=card.note_id,
                user_id=card.id,
                direction=card.direction,
                srs=SRS(
                    status=card.status,
                    due_timestamp=card.due,
                    interval_days=card.ivl,
                    ease_factor=card.ease,
                    learning_step=card.reps
                ),
                note_content=NoteContent(
                    field1=card.note.field1,
                    field2=card.note.field2,
                    tags=card.note.tags.split(" "),
                    created_at=card.note.created_at
                )
            )
            due_cards_response.cards.append(mapped_card)


        return due_cards_response
    except Exception as e:
        logger.exception(f"Unexpected error retrieving due cards for User ID {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve due cards.")


@router.post("/{card_id}/grade", status_code=status.HTTP_204_NO_CONTENT)
async def grade_card(
    card_id: int, 
    grade_data: CardGradeRequest,
    current_user: models.User = Depends(get_current_active_user),
    db_session: AsyncSession = Depends(session.get_db_session)
):
    """Grades a specific card instance after review."""
    user_id = current_user.id
    grade = grade_data.grade
    logger.info(f"Received grade '{grade}' for Card ID {card_id} from User ID {user_id}")

    # Get the specific card's data (includes SRS fields and note info now, but we only need SRS)
    card_data = await crud.get_card_by_id(db_session=db_session, card_id=card_id, user_id=user_id)
    if not card_data:
        logger.warning(f"Grade attempt failed: Card ID {card_id} not found or doesn't belong to User ID {user_id}.")
        raise HTTPException(status_code=404, detail="Card not found or access denied.")

    # --- SRS Calculation Logic 
    current_status =getattr( card_data,"status", "new")
    current_interval = float(getattr(card_data,"interval_days", 0.0))
    current_ease = float(getattr(card_data,"ease_factor", DEFAULT_EASE_FACTOR))
    learning_step_index = int(getattr(card_data,"learning_step", 0))
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
            new_status = 'learning' # Explicitly set to learning
        elif grade == 'good':
            new_learning_step = learning_step_index + 1
            if new_learning_step >= len(LEARNING_STEPS_MINUTES):
                # Graduate from learning
                new_status = 'review'
                new_interval = 1.0 # First review interval (days)
                next_due = now + int(new_interval * seconds_per_day)
                new_learning_step = 0 # Reset learning step
            else:
                # Advance learning step
                step_minutes = LEARNING_STEPS_MINUTES[new_learning_step]
                next_due = now + step_minutes * seconds_per_minute
                new_status = 'learning' # Stay in learning
        elif grade == 'easy':
            # Graduate immediately to review with easy interval
            new_status = 'review'
            new_interval = DEFAULT_EASY_INTERVAL_DAYS
            next_due = now + int(new_interval * seconds_per_day)
            new_learning_step = 0 # Reset learning step

    elif current_status == 'review':
        if grade == 'again':
            # Lapse
            new_status = 'learning' # Revert to learning
            new_ease = max(MIN_EASE_FACTOR, current_ease - 0.20)
            new_interval = current_interval * LAPSE_INTERVAL_MULTIPLIER # Typically 0, meaning reset
            new_learning_step = 0 # Start relearning steps
            step_minutes = LEARNING_STEPS_MINUTES[new_learning_step]
            next_due = now + step_minutes * seconds_per_minute
        elif grade == 'good':
            # Standard review interval calculation
            new_status = 'review'
            new_interval = current_interval * current_ease * DEFAULT_INTERVAL_MODIFIER
            # Consider adding fuzz factor here if desired
            next_due = now + int(new_interval * seconds_per_day)
            new_learning_step = 0 # Ensure learning step is 0 for review cards
        elif grade == 'easy':
            # Easy review calculation
            new_status = 'review'
            new_interval = current_interval * current_ease * DEFAULT_INTERVAL_MODIFIER * EASY_BONUS
            new_ease = current_ease + 0.15 # Increase ease
            next_due = now + int(new_interval * seconds_per_day)
            new_learning_step = 0 # Ensure learning step is 0

    # Apply bounds and floors
    new_interval = max(0.01, new_interval) # Ensure interval is positive
    new_ease = max(MIN_EASE_FACTOR, new_ease)

    # Update the specific card's SRS state
    success = await crud.update_card_srs(
        db_session=db_session,
        card_id=card_id, 
        user_id=user_id, 
        card_srs=SRS(
            status=new_status,
            due_timestamp=next_due,
            interval_days=new_interval,
            ease_factor=new_ease,
            learning_step=new_learning_step
        )
    )

    if not success:
        logger.error(f"Failed to update SRS state for Card ID {card_id} in database.")
        raise HTTPException(status_code=500, detail="Failed to update card state.")

    logger.info(f"Successfully updated Card ID {card_id}. New state: Status='{new_status}', Due='{next_due}', Interval='{new_interval:.2f}', Ease='{new_ease:.2f}', Step='{new_learning_step}'")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/my-notes", response_model=List[NotePublic]) # Changed path and response model
async def get_my_notes( # Renamed function
    current_user: models.User = Depends(get_current_active_user),
    db_session: AsyncSession = Depends(session.get_db_session) # Added db_session dependency
)->list[NotePublic]:
    """Fetches all notes owned by the current user."""
    user_id = current_user.id
    logger.info(f"Fetching all notes for User ID {user_id} via /my-notes endpoint.")
    try:
        # Call the function to get notes
        notes = await crud.get_all_notes_for_user(user_id=user_id, db_session=db_session)
        # Validate data against NotePublic model
        user_notes:list[NotePublic]=[]
        for note in notes:
            mapped=NotePublic(
                id=note.id,
                user_id=note.user_id,
                note_content=NoteContent(
                    field1=note.field1,
                    field2=note.field2,
                    tags=note.tags.split(" ") if note.tags else [],
                    created_at=note.created_at
                )
            )
            user_notes.append(mapped)

        return user_notes
    except sqlite3.Error as db_err:
        logger.exception(f"Database error retrieving all notes for User ID {user_id}: {db_err}")
        raise HTTPException(status_code=500, detail="Database error retrieving your notes.")
    except Exception as e:
        logger.exception(f"Unexpected error retrieving all notes for User ID {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve your notes.")


@router.delete("/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT) # Changed path
async def delete_note_endpoint( # Renamed function
    note_id: int, # Changed parameter name
    current_user: models.User = Depends(get_current_active_user),
    db_session: AsyncSession = Depends(session.get_db_session) # Added db_session dependency
):
    """Deletes a specific note (and its associated cards) owned by the user."""
    user_id = current_user.id
    logger.info(f"Received request to delete Note ID {note_id} from User ID {user_id}")
   
    # Call the database function to delete the note
    deleted = await crud.delete_note(db_session=db_session,note_id=note_id, user_id=user_id)
    if not deleted:
        # Check if the note existed before claiming failure
        logger.warning(f"Delete failed for Note ID {note_id} by User ID {user_id}: Note not found.")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found.")
    

# update note
@router.put("/notes/{note_id}", response_model=NotePublic) 
async def update_note_endpoint( 
    note_id: int, 
    note_update_data: NoteContent, 
    current_user: models.User = Depends(get_current_active_user),
    db_session: AsyncSession = Depends(session.get_db_session) 
):
    user_id = current_user.id
    logger.info(f"Received request to update Note ID {note_id} from User ID {user_id}")

    # Check if at least one field is being updated
    update_values = note_update_data.model_dump(exclude_unset=True)
    if not update_values:
         raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields provided for update. Please provide 'front', 'back', or 'tags'.",
        )
    try:
        # Attempt to update the note details in the database
        updated_note: NotePublic | None = await crud.update_note_details(
            db_session=db_session,
            note_id=note_id,
            user_id=user_id,
            note_details=note_update_data
        )

        if not updated_note:
            # Check if the note exists 
            existing_note: NotePublic | None = await crud.get_note_by_id(db_session=db_session,user_id=user_id,note_id=note_id) 
            if not existing_note:
                 logger.warning(f"Update failed for Note ID {note_id} by User ID {user_id}: Note not found.")
                 raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found.")
            else:
                 logger.error(f"Update attempt failed for Note ID {note_id} by User ID {user_id}, but note exists. DB function issue?")
                 raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update note details.")

        # If update was successful, fetch the updated note data to return
        updated_note_data: NotePublic | None = await crud.get_note_by_id(db_session=db_session,user_id=user_id,note_id=note_id)
        if not updated_note_data:
             logger.error(f"Failed to retrieve Note ID {note_id} immediately after successful update.")
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Note updated but could not be retrieved.")
        else:
            logger.info(f"Successfully updated Note ID {note_id} for User ID {user_id}.")
            # Validate and return the updated note using NotePublic model
            return updated_note_data

    except sqlite3.Error as db_err:
        logger.exception(f"Database error updating Note ID {note_id} for User ID {user_id}: {db_err}")
        raise HTTPException(status_code=500, detail="Database error updating note details.")
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.exception(f"Unexpected error updating Note ID {note_id} for User ID {user_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to update note due to a server error.")
    


@router.post('/quick_add', response_model=QuickAddResponse)
async def quick_add_from_word_endpoint(
    request_data: QuickAddRequest,
    current_user: models.User = Depends(get_current_active_user),
    llm_handler: GeminiHandler = Depends(get_llm),
    sentence_proposer_prompt: str = Depends(get_prompt("sentence_proposer_prompt")),
    db_session: AsyncSession = Depends(session.get_db_session)
    ):

    user_id = current_user.get("id")
    logger.info(f"--- Entering /quick_add_from word endpoint by User ID: {user_id} ---")
    logger.info(f"Received quick add request for word: '{request_data.topic}'")
    target_word = request_data.topic
    formatted_prompt = sentence_proposer_prompt.format(target_word=target_word)
    proposed_english = ''
    proposed_spanish = ''

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
            proposed_spanish = response_data.get("proposed_spanish", "").strip()
            proposed_english = response_data.get("proposed_english", "").strip()
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
    


    if not proposed_spanish or not proposed_english:
        logger.error(f"LLM returned empty proposal for word: {target_word}")
        raise HTTPException(status_code=500, detail="AI returned an empty proposal.")
    try:
        note: models.Note = await crud.add_note_with_cards(
            db_session=db_session,
            user_id=user_id,
            note_to_add= NoteContent(
                field1=proposed_spanish,  # Spanish front
                field2=proposed_english,   # English back
                tags=["quick_add"] # Tags as a space-separated string
            ))
        
        if note: # Check if note_id is not None
            logger.info(f"Successfully saved new Note to DB with ID: {note.id} (and its cards) for User ID: {user_id}")
            # Return the note_id instead of card_id
            return QuickAddResponse(
            success=True,
            message="Quick Add was sucessfully added",
            note_id=note.id,    
            user_id=user_id,
            field1=proposed_spanish,
            field2=proposed_english
            
        )
        else:
            logger.error(f"Failed to save note to database for user {user_id}, add_note_with_cards returned None.")
            raise HTTPException(status_code=500, detail="Failed to save note to database. Check server logs.")
        
    except sqlite3.Error as db_err:
            logger.exception(f"Database error saving note to database for user {user_id}: {db_err}")
            raise HTTPException(status_code=500, detail="Database error saving note.")
       





       