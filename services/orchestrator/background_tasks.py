import logging
from sqlalchemy.ext.asyncio import async_sessionmaker
import database.crud as crud
from services.session_engine import execute_session_engine_background

logger = logging.getLogger(__name__)

async def run_background_task(session_factory: async_sessionmaker):
    """
    Background task that processes all users with due cards using the session agent.
    """
    logger.info("Starting session agent background task")
    
    async with session_factory() as db_session:
        # Fetch only users that have due cards (using a single efficient query)
        users = await crud.get_users_with_due_cards(db_session)
        logger.info(f"Found {len(users)} users with due cards")
        
        for user in users:
            user_id = user.id
            try:
                logger.info(f"Processing user {user_id} with session agent")
                # Execute session engine for this user (in its own session)
                await execute_session_engine_background(session_factory, user_id)
            except Exception as e:
                logger.error(f"Error processing user {user_id}: {e}", exc_info=True)
                # Continue with other users
                continue
    
    logger.info("Session agent background task completed")
