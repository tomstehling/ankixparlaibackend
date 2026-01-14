import json
import logging
import time
import sqlite3  # Import sqlite3 for specific error handling

# import math


from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse


import database.crud as crud
import database.session as session
import database.models as models
from sqlalchemy.ext.asyncio import AsyncSession
from services.llm_handler import GeminiHandler, OpenRouterHandler
import schemas
from dependencies import get_current_active_user, get_llm, get_prompt
from core.config import settings
from typing import List, Optional, Any
from pydantic import ValidationError


logger = logging.getLogger(__name__)
router = APIRouter()

# --- SRS Constants (from config) ---
LEARNING_STEPS_MINUTES = getattr(settings, "LEARNING_STEPS_MINUTES", [1, 10])
DEFAULT_EASY_INTERVAL_DAYS = getattr(settings, "DEFAULT_EASY_INTERVAL_DAYS", 4.0)
MIN_EASE_FACTOR = getattr(settings, "MIN_EASE_FACTOR", 1.3)
LAPSE_INTERVAL_MULTIPLIER = getattr(settings, "LAPSE_INTERVAL_MULTIPLIER", 0.0)
DEFAULT_INTERVAL_MODIFIER = getattr(settings, "DEFAULT_INTERVAL_MODIFIER", 1.0)
DEFAULT_EASE_FACTOR = getattr(settings, "DEFAULT_EASE_FACTOR", 2.5)
EASY_BONUS = getattr(settings, "EASY_BONUS", 1.3)


# --- Card/Note Creation Endpoints ---


@router.post("/propose_sentence", response_class=JSONResponse)
async def propose_sentence_endpoint(
    request_data: schemas.ProposeSentenceRequest,
    current_user: models.User = Depends(get_current_active_user),
    llm_handler: Any = Depends(get_llm),
    sentence_proposer_prompt: str = Depends(get_prompt("sentence_proposer_prompt")),
):
    user_id = current_user.id
    logger.info(f"--- Entering /propose_sentence endpoint by User ID: {user_id} ---")
    logger.info(
        f"Received sentence proposal request for word: '{request_data.target_word}'"
    )
    target_word = request_data.target_word
    formatted_prompt = sentence_proposer_prompt.format(target_word=target_word)
    try:
        logger.info(f"Sending proposal request to LLM for '{target_word}'...")
        response_text = await llm_handler.generate_one_off(formatted_prompt)
        logger.info(f"Received proposal response from LLM.")
        if not response_text or response_text.startswith("(Response blocked"):
            logger.error(
                f"LLM returned empty/blocked response for sentence proposal. Response: {response_text}"
            )
            raise HTTPException(
                status_code=500,
                detail=f"AI returned an empty or blocked response: {response_text}",
            )
        try:
            response_text_cleaned = response_text.strip()
            if response_text_cleaned.startswith("```json"):
                response_text_cleaned = response_text_cleaned[7:-3].strip()
            elif response_text_cleaned.startswith("```"):
                response_text_cleaned = response_text_cleaned[3:-3].strip()
            start_brace = response_text_cleaned.find("{")
            end_brace = response_text_cleaned.rfind("}")
            if start_brace != -1 and end_brace != -1 and end_brace > start_brace:
                response_text_cleaned = response_text_cleaned[
                    start_brace : end_brace + 1
                ]
            else:
                logger.warning(
                    f"Proposal response might not be clean JSON after initial cleaning. Raw: {response_text}"
                )
                pass
            response_data = json.loads(response_text_cleaned)
            if (
                "proposed_spanish" not in response_data
                or "proposed_english" not in response_data
            ):
                logger.error(
                    f"LLM response missing required keys (propose). Raw: {response_text}"
                )
                raise ValueError(
                    "LLM response missing required keys (proposed_spanish, proposed_english)."
                )
            response_data["target_word"] = target_word
            return JSONResponse(content=response_data)
        except json.JSONDecodeError as json_err:
            logger.error(
                f"Failed to parse JSON (propose): {json_err}. Raw: {response_text}"
            )
            raise HTTPException(
                status_code=500, detail="Failed to parse sentence proposal from AI."
            )
        except ValueError as val_err:
            logger.error(
                f"LLM response validation error (propose): {val_err}. Raw: {response_text}"
            )
            raise HTTPException(
                status_code=500,
                detail=f"Invalid sentence proposal format from AI: {val_err}",
            )
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error during LLM call (propose): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error proposing sentence: {e}")


@router.post("/validate_translate_sentence", response_class=JSONResponse)
async def validate_translate_sentence_endpoint(
    request_data: schemas.ValidateTranslateRequest,
    current_user: models.User = Depends(get_current_active_user),
    llm_handler: Any = Depends(get_llm),
    sentence_validator_prompt: str = Depends(get_prompt("sentence_validator_prompt")),
):
    # --- No changes needed based on Note/Card schema ---
    user_id = current_user.id
    logger.info(
        f"--- Entering /validate_translate_sentence endpoint by User ID: {user_id} ---"
    )
    logger.info(
        f"Received validation/translation request for word: '{request_data.target_word}'"
    )
    formatted_prompt = sentence_validator_prompt.format(
        target_word=request_data.target_word,
        user_sentence=request_data.user_sentence,
        language=request_data.language,
    )
    try:
        logger.info(f"Sending validation/translation request to LLM...")
        response_text = await llm_handler.generate_one_off(formatted_prompt)
        logger.info(f"Received validation/translation response from LLM.")
        if not response_text or response_text.startswith("(Response blocked"):
            logger.error(
                f"LLM returned empty/blocked response for validation/translation. Response: {response_text}"
            )
            raise HTTPException(
                status_code=500,
                detail=f"AI returned an empty or blocked response: {response_text}",
            )
        try:
            response_text_cleaned = response_text.strip()
            if response_text_cleaned.startswith("```json"):
                response_text_cleaned = response_text_cleaned[7:-3].strip()
            elif response_text_cleaned.startswith("```"):
                response_text_cleaned = response_text_cleaned[3:-3].strip()
            start_brace = response_text_cleaned.find("{")
            end_brace = response_text_cleaned.rfind("}")
            if start_brace != -1 and end_brace != -1 and end_brace > start_brace:
                response_text_cleaned = response_text_cleaned[
                    start_brace : end_brace + 1
                ]
            else:
                logger.warning(
                    f"Validation response might not be clean JSON after initial cleaning. Raw: {response_text}"
                )
                pass
            response_data = json.loads(response_text_cleaned)
            required_keys = ["final_spanish", "final_english", "is_valid", "feedback"]
            missing_keys = [key for key in required_keys if key not in response_data]
            if missing_keys:
                logger.error(
                    f"LLM response missing required keys (validate): {missing_keys}. Raw: {response_text}"
                )
                raise ValueError(f"LLM response missing required keys: {missing_keys}")
            is_valid_raw = response_data.get("is_valid")
            if isinstance(is_valid_raw, bool):
                pass
            elif isinstance(is_valid_raw, str):
                valid_str = is_valid_raw.lower().strip()
                if valid_str == "true":
                    response_data["is_valid"] = True
                elif valid_str == "false":
                    response_data["is_valid"] = False
                else:
                    raise ValueError(
                        "LLM response 'is_valid' key is not a recognizable boolean string."
                    )
            else:
                raise ValueError(
                    "LLM response 'is_valid' key is not a boolean or recognizable boolean string."
                )
            return JSONResponse(content=response_data)
        except json.JSONDecodeError as json_err:
            logger.error(
                f"Failed to parse JSON (validate): {json_err}. Raw: {response_text}"
            )
            raise HTTPException(
                status_code=500,
                detail="Failed to parse sentence validation/translation from AI.",
            )
        except ValueError as val_err:
            logger.error(
                f"LLM response validation error (validate): {val_err}. Raw: {response_text}"
            )
            raise HTTPException(
                status_code=500,
                detail=f"Invalid validation/translation format from AI: {val_err}",
            )
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error during LLM call (validate): {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Error validating/translating sentence: {e}"
        )


@router.post("/save_note", response_model=schemas.NotePublic)
async def save_note(
    request_data: schemas.SaveCardRequest,  # Keep input model, map fields below
    current_user: models.User = Depends(get_current_active_user),
    db_session: AsyncSession = Depends(session.get_db_session),
):
    """Saves the final Spanish/English pair as a Note with two Cards."""
    user_id = current_user.id
    logger.info(f"--- Entering /save_note endpoint by User ID: {user_id} ---")
    logger.info(
        f"Received request to save final note. Field1: '{request_data.spanish_front[:30]}...'"
    )

    new_note_content = schemas.NoteContent(
        field1=request_data.spanish_front,  # Spanish front
        field2=request_data.english_back,  # English back
        tags=request_data.tags,  # Tags list
    )

    try:
        note_obj = await crud.add_note_with_cards(
            db_session=db_session, user_id=user_id, note_to_add=new_note_content
        )
        
        await db_session.commit()
        
        # Re-fetch with tags loaded to avoid lazy loading issues
        note = await crud.get_note_by_id(db_session, user_id, note_obj.id)

        if note:
            logger.info(
                f"Successfully saved new Note to DB with ID: {note.id} (and its cards) for User ID: {user_id}"
            )
            # Map to NotePublic
            tag_names = [nt.tag.name for nt in note.note_tags if nt.tag]
            return schemas.NotePublic(
                id=note.id,
                user_id=note.user_id,
                created_at=note.created_at,
                note_content=schemas.NoteContent(
                    field1=note.field1,
                    field2=note.field2,
                    tags=tag_names,
                    created_at=note.created_at
                )
            )
        else:
            logger.error(
                f"Failed to save note to database for user {user_id}, add_note_with_cards returned None."
            )
            raise HTTPException(
                status_code=500,
                detail="Failed to save note to database. Check server logs.",
            )
    except Exception as e:
        logger.error(
            f"Error saving note to database for user {user_id}: {e}", exc_info=True
        )
        raise HTTPException(status_code=500, detail=f"Database error saving note: {e}")


# --- SRS & Card/Note Management Endpoints ---


@router.get("/due", response_model=schemas.APIResponse[schemas.DueCardsResponse])
async def get_due_cards_for_user(
    db_session: AsyncSession = Depends(session.get_db_session),
    limit: int = 20,
    current_user: models.User = Depends(get_current_active_user),
) -> schemas.APIResponse[schemas.DueCardsResponse]:
    """Fetches due cards for the user, including necessary note content for review."""
    user_id = current_user.id
    logger.info(f"Fetching due cards for User ID {user_id} (limit {limit})...")
    try:
        # Use the updated DB function which joins notes and cards
        due_cards_data: list[models.Card] = await crud.get_due_cards(
            db_session=db_session, user_id=user_id, limit=limit
        )
        # The data should now match the structure of DueCardResponseItem

        due_cards_response: schemas.DueCardsResponse = schemas.DueCardsResponse(
            cards=[]
        )
        state_to_status = {0: "new", 1: "learning", 2: "review", 3: "lapsed"}
        for card in due_cards_data:
            # Infer direction: 0 if front is field1 (Spanish), 1 if front is field2 (English)
            direction = 0 if card.front == card.note.field1 else 1
            
            # Extract tags from note_tags relationship
            tag_names = [nt.tag.name for nt in card.note.note_tags if nt.tag]

            mapped_card = schemas.DueCardResponseItem(
                card_id=card.id,
                note_id=card.note_id,
                user_id=current_user.id,
                direction=direction,
                created_at=card.note.created_at,
                fsrs=schemas.FSRS(
                    due_date=card.due_date,
                    due_timestamp=int(card.due_date.timestamp()),
                    stability=card.stability or 0.0,
                    difficulty=card.difficulty or 0.0,
                    last_review=card.last_review,
                    state=card.state,
                    status=state_to_status.get(card.state, "review"),
                    review_count=card.review_count,
                    lapse_count=card.lapse_count,
                    learning_step=0, # Missing from model, default to 0
                ),
                note_content=schemas.NoteContent(
                    field1=card.note.field1,
                    field2=card.note.field2,
                    tags=tag_names,
                    created_at=card.note.created_at,
                ),
            )
            due_cards_response.cards.append(mapped_card)
        return schemas.APIResponse(status="success", data=due_cards_response)

    except Exception as e:
        logger.exception(
            f"Unexpected error retrieving due cards for User ID {user_id}: {e}"
        )
        raise HTTPException(status_code=500, detail="Failed to retrieve due cards.")


@router.post(
    "/{card_id}/grade", response_model=schemas.APIResponse[schemas.GradeCardResponse]
)
async def grade_card(
    card_id: int,
    grade_data: schemas.CardGradeRequest,
    current_user: models.User = Depends(get_current_active_user),
    db_session: AsyncSession = Depends(session.get_db_session),
) -> schemas.APIResponse[schemas.GradeCardResponse]:
    """Grades a specific card instance after review."""
    user_id = current_user.id
    grade = grade_data.grade
    logger.info(
        f"Received grade '{grade}' for Card ID {card_id} from User ID {user_id}"
    )

    # Get the specific card's data (includes SRS fields and note info now, but we only need SRS)
    card_data = await crud.get_card_by_id(
        db_session=db_session, card_id=card_id, user_id=user_id
    )
    if not card_data:
        logger.warning(
            f"Grade attempt failed: Card ID {card_id} not found or doesn't belong to User ID {user_id}."
        )
        raise HTTPException(status_code=404, detail="Card not found or access denied.")

    # --- SRS Calculation Logic
    state_to_status = {0: "new", 1: "learning", 2: "review", 3: "lapsed"}
    current_status = state_to_status.get(card_data.state, "review")
    
    current_interval = float(card_data.stability or 0.0)
    current_ease = float(card_data.difficulty or DEFAULT_EASE_FACTOR)
    # learning_step is missing from model, we'll assume it's stored in pedagogical_difficulty for now or just use 0
    learning_step_index = int(card_data.pedagogical_difficulty or 0)
    
    now = int(time.time())
    seconds_per_day = 86400
    seconds_per_minute = 60

    new_status = current_status
    new_interval = current_interval
    new_ease = current_ease
    next_due = now
    new_learning_step = learning_step_index

    if current_status in ("new", "learning", "lapsed"):
        if grade == "again":
            new_learning_step = 0
            step_minutes = LEARNING_STEPS_MINUTES[new_learning_step]
            next_due = now + step_minutes * seconds_per_minute
            new_status = "learning"
        elif grade == "good":
            new_learning_step = learning_step_index + 1
            if new_learning_step >= len(LEARNING_STEPS_MINUTES):
                # Graduate from learning
                new_status = "review"
                new_interval = 1.0  # First review interval (days)
                next_due = now + int(new_interval * seconds_per_day)
                new_learning_step = 0
            else:
                # Advance learning step
                step_minutes = LEARNING_STEPS_MINUTES[new_learning_step]
                next_due = now + step_minutes * seconds_per_minute
                new_status = "learning"
        elif grade == "easy":
            # Graduate immediately to review with easy interval
            new_status = "review"
            new_interval = DEFAULT_EASY_INTERVAL_DAYS
            next_due = now + int(new_interval * seconds_per_day)
            new_learning_step = 0

    elif current_status == "review":
        if grade == "again":
            # Lapse
            new_status = "learning"
            new_ease = max(MIN_EASE_FACTOR, current_ease - 0.20)
            new_interval = (
                current_interval * LAPSE_INTERVAL_MULTIPLIER
            )
            new_learning_step = 0
            step_minutes = LEARNING_STEPS_MINUTES[new_learning_step]
            next_due = now + step_minutes * seconds_per_minute
        elif grade == "good":
            # Standard review interval calculation
            new_status = "review"
            # If it was 0 (new), start at 1.0
            if current_interval < 1.0:
                new_interval = 1.0
            else:
                new_interval = current_interval * current_ease * DEFAULT_INTERVAL_MODIFIER
            
            next_due = now + int(new_interval * seconds_per_day)
            new_learning_step = 0
        elif grade == "easy":
            # Easy review calculation
            if current_interval < 1.0:
                new_interval = DEFAULT_EASY_INTERVAL_DAYS
            else:
                new_interval = (
                    current_interval * current_ease * DEFAULT_INTERVAL_MODIFIER * EASY_BONUS
                )
            new_ease = current_ease + 0.15
            next_due = now + int(new_interval * seconds_per_day)
            new_learning_step = 0

    # Apply bounds and floors
    new_interval = max(0.01, new_interval)
    new_ease = max(MIN_EASE_FACTOR, new_ease)

    # Update the specific card's SRS state
    success = await crud.update_card_srs(
        db_session=db_session,
        card_id=card_id,
        user_id=user_id,
        card_srs=schemas.SRS(
            status=new_status,
            due_timestamp=next_due,
            interval_days=new_interval,
            ease_factor=new_ease,
            learning_step=new_learning_step,
        ),
    )

    if not success:
        logger.error(f"Failed to update SRS state for Card ID {card_id} in database.")
        raise HTTPException(status_code=500, detail="Failed to update card state.")
    logger.info(f"Successfully updated Card ID {card_id}.")
    await db_session.refresh(current_user, attribute_names=["awards"])
    await crud.update_streak_on_grade(
        db_session=db_session, user=current_user, timezone=grade_data.timezone
    )
    await db_session.refresh(current_user, attribute_names=["awards"])

    return schemas.APIResponse(
        status="success",
        data=schemas.GradeCardResponse(
            success=True,
            message="Card graded and SRS updated.",
            current_streak=current_user.awards.current_streak,
            longest_streak=current_user.awards.current_streak,
        ),
    )


@router.get("/my-notes", response_model=schemas.APIResponse[schemas.FetchNotesResponse])
async def fetch_my_notes(  # Renamed function
    current_user: models.User = Depends(get_current_active_user),
    db_session: AsyncSession = Depends(
        session.get_db_session
    ),  # Added db_session dependency
) -> schemas.APIResponse[schemas.FetchNotesResponse]:
    """Fetches all notes owned by the current user."""
    user_id = current_user.id
    logger.info(f"Fetching all notes for User ID {user_id} via /my-notes endpoint.")
    try:
        # Call the function to get notes
        notes = await crud.get_all_notes_for_user(
            user_id=user_id, db_session=db_session
        )
        # Validate data against NotePublic model
        user_notes: list[schemas.NotePublic] = []
        for note in notes:
            tag_names = [nt.tag.name for nt in note.note_tags if nt.tag]
            mapped = schemas.NotePublic(
                id=note.id,
                user_id=note.user_id,
                created_at=note.created_at,
                note_content=schemas.NoteContent(
                    field1=note.field1,
                    field2=note.field2,
                    tags=tag_names,
                ),
            )
            user_notes.append(mapped)

        return schemas.APIResponse(
            status="success", data=schemas.FetchNotesResponse(notes=user_notes)
        )
    except sqlite3.Error as db_err:
        logger.exception(
            f"Database error retrieving all notes for User ID {user_id}: {db_err}"
        )
        raise HTTPException(
            status_code=500, detail="Database error retrieving your notes."
        )
    except Exception as e:
        logger.exception(
            f"Unexpected error retrieving all notes for User ID {user_id}: {e}"
        )
        raise HTTPException(status_code=500, detail="Failed to retrieve your notes.")


@router.delete(
    "/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT
)  # Changed path
async def delete_note_endpoint(  # Renamed function
    note_id: int,  # Changed parameter name
    current_user: models.User = Depends(get_current_active_user),
    db_session: AsyncSession = Depends(
        session.get_db_session
    ),  # Added db_session dependency
):
    """Deletes a specific note (and its associated cards) owned by the user."""
    try:
        user_id = current_user.id
        logger.info(f"--- Entering delete_note_endpoint for Note ID {note_id} by User ID {user_id} ---")

        # Call the database function to delete the note
        deleted = await crud.delete_note(
            db_session=db_session, note_id=note_id, user_id=user_id
        )
        if not deleted:
            # Check if the note existed before claiming failure
            logger.warning(
                f"Delete failed for Note ID {note_id} by User ID {user_id}: Note not found or access denied."
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Note not found."
            )
        
        logger.info(f"Successfully finished delete_note_endpoint for Note ID {note_id}")
        return None
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"UNEXPECTED ERROR in delete_note_endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# update note
@router.put("/notes/{note_id}", response_model=schemas.NotePublic)
async def update_note_endpoint(
    note_id: int,
    note_update_data: schemas.NoteContent,
    current_user: models.User = Depends(get_current_active_user),
    db_session: AsyncSession = Depends(session.get_db_session),
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
        updated_note: Optional[models.Note] = await crud.update_note_details(
            db_session=db_session,
            note_id=note_id,
            user_id=user_id,
            note_details=note_update_data,
        )
        if not updated_note:
            logger.warning(f"Update failed for Note ID {note_id} by User ID {user_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Note not found."
            )
        else:
            logger.info(f"Successfully updated Note ID {note_id} for User ID {user_id}")
            # Map the updated note to the response model
            tag_names = [nt.tag.name for nt in updated_note.note_tags if nt.tag]
            return schemas.NotePublic(
                id=updated_note.id,
                user_id=updated_note.user_id,
                created_at=updated_note.created_at,
                note_content=schemas.NoteContent(
                    field1=updated_note.field1,
                    field2=updated_note.field2,
                    tags=tag_names,
                    created_at=updated_note.created_at,
                ),
            )
    except Exception as e:
        logger.exception(
            f"Unexpected error updating Note ID {note_id} for User ID {user_id}: {e}"
        )
        raise HTTPException(
            status_code=500, detail="Failed to update note due to a server error."
        )


@router.post("/quick_add", response_model=schemas.QuickAddResponse)
async def quick_add_from_word_endpoint(
    request_data: schemas.QuickAddRequest,
    current_user: models.User = Depends(get_current_active_user),
    llm_handler: Any = Depends(get_llm),
    sentence_proposer_prompt: str = Depends(get_prompt("sentence_proposer_prompt")),
    db_session: AsyncSession = Depends(session.get_db_session),
):

    user_id = current_user.id
    logger.info(f"--- Entering /quick_add_from word endpoint by User ID: {user_id} ---")
    logger.info(f"Received quick add request for word: '{request_data.topic}'")
    target_word = request_data.topic
    formatted_prompt = sentence_proposer_prompt.format(target_word=target_word)
    proposed_english = ""
    proposed_spanish = ""

    try:
        logger.info(f"Sending proposal request to LLM for '{target_word}'...")
        response_text = await llm_handler.generate_one_off(formatted_prompt)
        logger.info(f"Received proposal response from LLM.")
        if not response_text or response_text.startswith("(Response blocked"):
            logger.error(
                f"LLM returned empty/blocked response for sentence proposal. Response: {response_text}"
            )
            raise HTTPException(
                status_code=500,
                detail=f"AI returned an empty or blocked response: {response_text}",
            )
        try:
            response_text_cleaned = response_text.strip()
            if response_text_cleaned.startswith("```json"):
                response_text_cleaned = response_text_cleaned[7:-3].strip()
            elif response_text_cleaned.startswith("```"):
                response_text_cleaned = response_text_cleaned[3:-3].strip()
            start_brace = response_text_cleaned.find("{")
            end_brace = response_text_cleaned.rfind("}")
            if start_brace != -1 and end_brace != -1 and end_brace > start_brace:
                response_text_cleaned = response_text_cleaned[
                    start_brace : end_brace + 1
                ]
            else:
                logger.warning(
                    f"Proposal response might not be clean JSON after initial cleaning. Raw: {response_text}"
                )
                pass
            response_data = json.loads(response_text_cleaned)
            if (
                "proposed_spanish" not in response_data
                or "proposed_english" not in response_data
            ):
                logger.error(
                    f"LLM response missing required keys (propose). Raw: {response_text}"
                )
                raise ValueError(
                    "LLM response missing required keys (proposed_spanish, proposed_english)."
                )
            response_data["target_word"] = target_word
            proposed_spanish = response_data.get("proposed_spanish", "").strip()
            proposed_english = response_data.get("proposed_english", "").strip()
        except json.JSONDecodeError as json_err:
            logger.error(
                f"Failed to parse JSON (propose): {json_err}. Raw: {response_text}"
            )
            raise HTTPException(
                status_code=500, detail="Failed to parse sentence proposal from AI."
            )
        except ValueError as val_err:
            logger.error(
                f"LLM response validation error (propose): {val_err}. Raw: {response_text}"
            )
            raise HTTPException(
                status_code=500,
                detail=f"Invalid sentence proposal format from AI: {val_err}",
            )
    except HTTPException as http_exc:
        raise http_exc
    except Exception as e:
        logger.error(f"Error during LLM call (propose): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error proposing sentence: {e}")

    if not proposed_spanish or not proposed_english:
        logger.error(f"LLM returned empty proposal for word: {target_word}")
        raise HTTPException(status_code=500, detail="AI returned an empty proposal.")

    note: models.Note = await crud.add_note_with_cards(
        db_session=db_session,
        user_id=user_id,
        note_to_add=schemas.NoteContent(
            field1=proposed_spanish,  # Spanish front
            field2=proposed_english,  # English back
            tags=["quick_add"],  # Tags as a space-separated string
        ),
    )

    if note:  # Check if note_id is not None
        logger.info(
            f"Successfully saved new Note to DB with ID: {note.id} (and its cards) for User ID: {user_id}"
        )
        # Return the note_id instead of card_id
        return schemas.QuickAddResponse(
            success=True,
            message="Quick Add was sucessfully added",
            note_id=note.id,
            user_id=user_id,
            field1=proposed_spanish,
            field2=proposed_english,
        )
    else:
        logger.error(
            f"Failed to save note to database for user {user_id}, add_note_with_cards returned None."
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to save note to database. Check server logs.",
        )


def _parse_llm_studio_response(response_text: str) -> schemas.LLMStudioResponse:
    """
    Cleans a string from an LLM response and parses it directly into a
    type-safe Pydantic model.

    Raises:
        ValueError: If the response is empty, malformed, or fails validation.
    """
    if not response_text:
        raise ValueError("LLM returned an empty response.")

    cleaned_text = response_text.strip()
    if cleaned_text.startswith("```json"):
        cleaned_text = cleaned_text[7:-3].strip()
    elif cleaned_text.startswith("```"):
        cleaned_text = cleaned_text[3:-3].strip()

    # Fallback to find the outermost JSON object
    start_brace = cleaned_text.find("{")
    end_brace = cleaned_text.rfind("}")
    if start_brace != -1 and end_brace != -1 and end_brace > start_brace:
        cleaned_text = cleaned_text[start_brace : end_brace + 1]

    try:
        # Pydantic handles both JSON parsing and data validation in one go.
        # This is much safer and more explicit than `json.loads`.
        return schemas.LLMStudioResponse.model_validate_json(cleaned_text)
    except (ValidationError, json.JSONDecodeError) as e:
        logger.error(
            f"Failed to parse or validate LLM response: {e}. Raw: {response_text}"
        )
        # Re-raising as a ValueError to be caught by the endpoint handler.
        raise ValueError("The AI returned a response with an invalid structure.") from e


# --- API Endpoints ---


@router.post("/create_from_topic", response_model=List[schemas.StudioCard])
async def create_cards_from_topic(
    request: schemas.CreateFromTopicRequest,
    current_user: models.User = Depends(get_current_active_user),
    llm_handler: Any = Depends(get_llm),
    prompt_template: str = Depends(get_prompt("studio_topic_prompt")),
):
    """
    Generates a list of flashcard suggestions based on a topic.
    The cards are NOT saved to the database; they are returned for user review.
    """
    logger.info(
        f"User ID {current_user.id} requested {request.card_amount} cards for topic: '{request.topic}'"
    )

    custom_instructions = (
        request.custom_instructions if request.custom_instructions else "None."
    )
    formatted_prompt = prompt_template.format(
        topic=request.topic,
        card_amount=request.card_amount,
        custom_instructions_section=custom_instructions,
    )

    try:
        logger.info("Sending 'create from topic' request to LLM...")
        response_text = await llm_handler.generate_one_off(formatted_prompt)
        logger.info("Received LLM response for 'create from topic'.")

        # The parsing and validation now happen in our type-safe helper.
        # `llm_response` is now a fully typed `LLMStudioResponse` object.
        llm_response = _parse_llm_studio_response(response_text)

        logger.info(
            f"Successfully generated {len(llm_response.cards)} cards for topic: '{request.topic}'"
        )

        # The type checker knows `llm_response.cards` is a `List[StudioCard]`,
        # which perfectly matches the `response_model`.
        return llm_response.cards

    except ValueError as e:
        # Catches errors from our parsing function.
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(
            f"An unexpected error occurred in /create_from_topic: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while generating cards.",
        )


@router.post("/create_from_text", response_model=List[schemas.StudioCard])
async def create_cards_from_text(
    request: schemas.CreateFromTextRequest,
    current_user: models.User = Depends(get_current_active_user),
    llm_handler: Any = Depends(get_llm),
    prompt_template: str = Depends(get_prompt("studio_text_prompt")),
):
    """
    Generates a list of flashcard suggestions by extracting vocabulary from a block of text.
    The cards are NOT saved to the database; they are returned for user review.
    """
    logger.info(f"User ID {current_user.id} requested cards from a block of text.")

    custom_instructions = (
        request.custom_instructions if request.custom_instructions else "None."
    )
    formatted_prompt = prompt_template.format(
        text=request.text, custom_instructions_section=custom_instructions
    )

    try:
        logger.info("Sending 'create from text' request to LLM...")
        response_text = await llm_handler.generate_one_off(formatted_prompt)
        logger.info("Received LLM response for 'create from text'.")

        # Re-using the same robust, type-safe parsing logic.
        llm_response = _parse_llm_studio_response(response_text)

        logger.info(
            f"Successfully generated {len(llm_response.cards)} cards from text."
        )
        return llm_response.cards

    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.error(
            f"An unexpected error occurred in /create_from_text: {e}", exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while generating cards.",
        )


@router.post("/bulk_save_notes", response_class=JSONResponse)
async def bulk_save_notes(
    request_data: list[schemas.SaveCardRequest],
    current_user: models.User = Depends(get_current_active_user),
    db_session: AsyncSession = Depends(session.get_db_session),
):
    """Saves the final Spanish/English pair as a Note with two Cards."""
    user_id = current_user.id
    logger.info(f"--- Entering /save_note endpoint by User ID: {user_id} ---")
    logger.info(f"Received request to save `{len(request_data)}` final notes.")
    notes_to_add: list[schemas.NoteContent] = []
    for item in request_data:
        if not item.spanish_front or not item.english_back:
            logger.error(f"Invalid note data in bulk save: {item}")
            raise HTTPException(
                status_code=400,
                detail="Each note must have both 'spanish_front' and 'english_back'.",
            )
        new_note = schemas.NoteContent(
            field1=item.spanish_front, field2=item.english_back, tags=item.tags
        )

        notes_to_add.append(new_note)
    try:
        await crud.add_notes_with_cards_bulk(
            db_session=db_session, user=current_user, notes_to_add=notes_to_add
        )
        await db_session.commit()
        
        logger.info(
            f"Successfully saved `{len(request_data)}` new Notes to DB (and their cards) for User ID: {user_id}"
        )
        return JSONResponse(
            content={
                "success": True,
                "message": f"{len(request_data)} Notes and cards saved to database.",
            }
        )
    except Exception as e:
        logger.error(
            f"Error saving notes to database for user {user_id}: {e}", exc_info=True
        )
        raise HTTPException(status_code=500, detail=f"Database error saving notes: {e}")


@router.post(
    "/translate", response_model=schemas.APIResponse[schemas.TranslateResponse]
)
async def translate_text_endpoint(
    request: schemas.TranslateRequest,
    current_user: models.User = Depends(get_current_active_user),
    llm_handler: Any = Depends(get_llm),
    smart_prompt: str = Depends(get_prompt("smart_translator_prompt")),
    standard_prompt: str = Depends(get_prompt("standard_translator_prompt")),
) -> schemas.APIResponse[schemas.TranslateResponse]:
    """
    Translates English text to Spanish using a specified translation mode.
    - Standard: Direct translation.
    - Smart: Provides a personalized translation based on user data such as proficiency level.
    """
    logger.info(
        f"User {current_user.id} requested '{request.translation_mode}' translation."
    )

    prompt_template = smart_prompt if request.translation_mode == "smart" else standard_prompt
    formatted_prompt = prompt_template.format(text=request.text)
    
    response_text = ""
    try:
        logger.info(f"Sending {request.translation_mode} translation request to LLM...")
        response_text = await llm_handler.generate_one_off(formatted_prompt)
        
        cleaned_text = response_text.strip()
        if cleaned_text.startswith("```json"):
            cleaned_text = cleaned_text[7:-3].strip()
        elif cleaned_text.startswith("```"):
            cleaned_text = cleaned_text[3:-3].strip()

        # Fallback to find the outermost JSON object
        start_brace = cleaned_text.find("{")
        end_brace = cleaned_text.rfind("}")
        if start_brace != -1 and end_brace != -1 and end_brace > start_brace:
            cleaned_text = cleaned_text[start_brace : end_brace + 1]
        
        data = json.loads(cleaned_text)

        # We now expect the LLM to return field1 as Spanish and field2 as English
        note_content = schemas.NoteContent(
            field1=data.get("field1", ""),
            field2=data.get("field2", ""),
            tags=data.get("tags", []),
        )

        # Fallback if LLM didn't provide one of the fields (should not happen with good prompts)
        if not note_content.field1 or not note_content.field2:
             logger.warning(f"LLM returned incomplete fields: {data}")
             # If we can't tell, just put input in one and result in other
             # But our new prompts are explicit.

        return schemas.APIResponse(
            status="success",
            data=schemas.TranslateResponse(
                translation=note_content, translation_type=request.translation_mode
            ),
        )
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(
            f"Failed to parse {request.translation_mode} translation JSON from LLM: {e}. Raw: {response_text}"
        )
        raise HTTPException(
            status_code=500,
            detail="AI returned a malformed response for translation.",
        )
    except Exception as e:
        logger.error(
            f"An unexpected error occurred during {request.translation_mode} translation: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"An unexpected error occurred during {request.translation_mode} translation.",
        )
