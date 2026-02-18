import logging
import uuid
from typing import List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from database import models, crud

logger = logging.getLogger(__name__)

# --- Session Sorter (Pure Business Logic) ---

def sort_cards_for_compression(
    cards: List[models.Card], 
    stability_threshold: float = 7.0, 
    lapse_threshold: int = 3
) -> Tuple[List[models.Card], List[models.Card]]:
    """
    Sorts cards into two buckets: Fragile and Mature.
    Fragile: Should not be compressed (learning, high lapses, or low stability).
    Mature: Safe for AI-driven compression/summarization.
    """
    fragile = []
    mature = []

    for card in cards:
        # State mapping: 0=New, 1=Learning, 2=Review, 3=Lapsed
        is_in_review = (card.state == 2)
        has_low_lapses = (card.lapse_count <= lapse_threshold)
        has_high_stability = ((card.stability or 0.0) >= stability_threshold)

        if is_in_review and has_low_lapses and has_high_stability:
            mature.append(card)
        else:
            fragile.append(card)

    return fragile, mature


# --- Core Worker Logic (Service Layer) ---

async def process_user_compression(
    user_id: uuid.UUID, 
    session_factory: async_sessionmaker[AsyncSession]
):
    """
    Main worker logic for a single user's nightly compression.
    Decoupled from HTTP and dispatching logic.
    """
    logger.info(f"Compression Worker: Starting for User ID {user_id}")
    
    try:
        async with session_factory() as session:
            # 1. Fetch all due cards for the user
            # (Re-using get_due_cards but without limit for compression)
            due_cards = await crud.get_due_cards(session, user_id, limit=1000)
            
            if not due_cards:
                logger.info(f"Compression Worker: No cards due for user {user_id}. Skipping.")
                return

            # 2. Sort cards into buckets
            fragile, mature = sort_cards_for_compression(due_cards)
            
            logger.info(
                f"Compression Worker: User {user_id} summary - "
                f"Total: {len(due_cards)}, Mature: {len(mature)}, Fragile: {len(fragile)}"
            )

            # 3. Handle Compression (Placeholder for LLM Logic)
            if mature:
                logger.info(f"Compression Worker: Mocking compression for {len(mature)} mature cards...")
                # In the future, this will:
                # - Send card content to LLM
                # - Summarize/Compress
                # - Update the notes in the DB
                pass
            
            logger.info(f"Compression Worker: Successfully finished for User ID {user_id}")

    except Exception as e:
        logger.error(f"Compression Worker Error for User ID {user_id}: {e}", exc_info=True)
