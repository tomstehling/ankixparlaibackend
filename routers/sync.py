import logging
from typing import List # Only needed for type hint if keeping learned_sentences global update

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

import database.database as database
from schemas import AnkiDeckUpdateRequest, GetNewCardsResponse, MarkSyncedRequest
from dependencies import get_current_active_user, get_learned_sentences # Import dependencies

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/anki_deck")
async def sync_anki_deck_endpoint(
    payload: AnkiDeckUpdateRequest,
    # Decide if this endpoint still needs to update a global list or if it's truly deprecated
    # learned_sentences: List[str] = Depends(get_learned_sentences) # Example if needed
):
    """(DEPRECATED/Review Needed) Receives sentences from hypothetical Anki plugin."""
    logger.warning(f"--- Endpoint /sync/anki_deck accessed (DEPRECATED) ---")
    logger.info(f"Received sync_anki_deck request with {len(payload.sentences)} sentences.")
    # If you still need the global list for the basic chat prompt:
    # learned_sentences.clear()
    # learned_sentences.extend(payload.sentences)
    # logger.info(f"Updated global learned sentences list (Review if still needed).")
    return {"message": "Endpoint deprecated. Functionality may be removed.", "success": True}


@router.get("/new_cards", response_model=GetNewCardsResponse)
async def get_new_chatbot_cards_endpoint(
    current_user: dict = Depends(get_current_active_user)
):
    """(DEPRECATED/Review Needed) Provides pending cards (for hypothetical Anki sync)."""
    user_id = current_user.get("id")
    logger.warning(f"--- Endpoint /sync/new_cards accessed by User ID {user_id} (DEPRECATED) ---")
    try:
        # Assuming get_pending_cards filters by user_id and status='pending'
        cards = database.get_pending_cards(user_id=user_id)
        logger.info(f"Returning {len(cards)} pending cards for user {user_id} (Deprecated Endpoint).")
        # Convert to the expected format if necessary (already done by model?)
        return GetNewCardsResponse(cards=cards)
    except Exception as e:
        logger.error(f"Database error retrieving pending cards for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve pending cards from database.")


@router.post("/mark_synced", response_class=JSONResponse)
async def mark_cards_synced_endpoint(
    payload: MarkSyncedRequest,
    current_user: dict = Depends(get_current_active_user)
):
    """(DEPRECATED/Review Needed) Marks cards as synced (for hypothetical Anki sync)."""
    user_id = current_user.get("id")
    logger.warning(f"--- Endpoint /sync/mark_synced accessed by User ID {user_id} (DEPRECATED) ---")
    card_ids = payload.card_ids
    if not card_ids:
        return JSONResponse(content={"success": True, "message": "No card IDs provided."}, status_code=200)

    logger.info(f"Received request from user {user_id} to mark {len(card_ids)} cards as synced: {card_ids} (Deprecated Endpoint).")
    try:
        # Ensure mark_cards_as_synced checks ownership (user_id)
        success = database.mark_cards_as_synced(card_ids, user_id=user_id)
        if success:
            # Determine actual number modified if possible from DB function
            logger.info(f"Marking cards {card_ids} for user {user_id} reported successful.")
            return JSONResponse(content={"success": True, "message": f"Successfully marked cards as synced (Deprecated)." })
        else:
            logger.warning(f"Marking cards {card_ids} failed for user {user_id}.")
            # Use 400 if it's likely due to bad input (e.g., wrong IDs), 500 for server error
            return JSONResponse(content={"success": False, "message": f"Failed to mark cards as synced. Check logs/permissions (Deprecated)."}, status_code=400)
    except Exception as e:
        logger.error(f"Error during /mark_cards_synced for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Server error while updating card statuses.")