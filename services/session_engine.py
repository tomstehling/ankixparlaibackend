import uuid
import logging
from datetime import datetime, timedelta
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
import database.crud as crud
from database import models
from sqlalchemy import select, delete

logger = logging.getLogger(__name__)

LOWER_BOUND = 15
UPPER_BOUND = 40
CARDS_TO_ADD = 5
CARDS_TO_REMOVE = 10


class SessionEngine:
    def __init__(self):
        pass

    async def evaluate_and_adjust(self, db_session: AsyncSession, user_id: uuid.UUID) -> Dict[str, Any]:
        await self._prune_stale_generated_cards(db_session)

        user = await db_session.get(models.User, user_id)
        if not user:
            logger.error(f"User {user_id} not found")
            return {"initial_due": 0, "action": "error_user_not_found", "final_due": 0}

        timezone_str = user.timezone or "UTC"

        initial_due = await crud.get_workload_count(db_session, user_id, timezone_str)

        action = "none"
        final_due = initial_due

        if initial_due < LOWER_BOUND:
            action = "card_generator"
            logger.info(f"User {user_id}: Initial due {initial_due} < {LOWER_BOUND}, triggering Card Generator")
            final_due = initial_due + CARDS_TO_ADD
        elif initial_due > UPPER_BOUND:
            action = "card_compressor"
            logger.info(f"User {user_id}: Initial due {initial_due} > {UPPER_BOUND}, triggering Card Compressor")
            final_due = initial_due - CARDS_TO_REMOVE
        else:
            action = "none"
            logger.info(f"User {user_id}: Initial due {initial_due} within goldilocks zone [{LOWER_BOUND}, {UPPER_BOUND}]")

        return {
            "initial_due": initial_due,
            "action": action,
            "final_due": final_due
        }

    async def _prune_stale_generated_cards(self, db_session: AsyncSession) -> int:
        cutoff_date = datetime.utcnow() - timedelta(days=10)
        
        query = (
            delete(models.Card)
            .where(models.Card.state == 0)
            .where(models.Card.created_at < cutoff_date)
        )
        
        result = await db_session.execute(query)
        await db_session.commit()
        
        deleted_count = result.rowcount
        if deleted_count > 0:
            logger.info(f"Pruned {deleted_count} stale generated cards (state=0, created > 10 days ago)")
        
        return deleted_count


async def execute_session_engine_background(db_session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID) -> None:
    """
    Background task wrapper for SessionEngine designed to be passed to FastAPI's BackgroundTasks.
    
    Args:
        db_session_factory: The async session factory from app.state
        user_id: UUID of the user to process
    """
    task_logger = logging.getLogger("session_engine.background")
    task_logger.info(f"Starting SessionEngine background task for user {user_id}")
    
    try:
        async with db_session_factory() as db_session:
            engine = SessionEngine()
            result = await engine.evaluate_and_adjust(db_session, user_id)
            
            task_logger.info(
                f"SessionEngine completed for user {user_id}: "
                f"initial_due={result['initial_due']}, action={result['action']}, final_due={result['final_due']}"
            )
            
    except Exception as e:
        task_logger.error(
            f"SessionEngine background task failed for user {user_id}: {str(e)}",
            exc_info=True
        )
