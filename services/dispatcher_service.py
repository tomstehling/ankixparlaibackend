import logging
import uuid
from typing import List, Protocol
from fastapi import BackgroundTasks
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from services.compression_service import process_user_compression

logger = logging.getLogger(__name__)

class CompressionDispatcher(Protocol):
    """
    Protocol for the dispatching mechanism. 
    Allows swapping between BackgroundTasks and Cloud Tasks.
    """
    def dispatch(self, user_id: uuid.UUID):
        ...

class FastAPIBackgroundDispatcher:
    """
    Adapter for FastAPI's BackgroundTasks.
    """
    def __init__(
        self, 
        background_tasks: BackgroundTasks, 
        session_factory: async_sessionmaker[AsyncSession]
    ):
        self.background_tasks = background_tasks
        self.session_factory = session_factory

    def dispatch(self, user_id: uuid.UUID):
        logger.debug(f"Dispatcher: Queueing compression task for user {user_id} via BackgroundTasks.")
        self.background_tasks.add_task(
            process_user_compression, 
            user_id, 
            self.session_factory
        )

# --- Dispatcher Helper ---

async def fan_out_compression_tasks(
    db_session: AsyncSession, 
    dispatcher: CompressionDispatcher
):
    """
    Orchestrator: Identifies all users needing compression and 
    dispatches workers via the provided adapter.
    """
    from database import crud
    
    # 1. Fetch all users who have due cards
    active_user_ids = await crud.get_users_with_due_cards(db_session)
    
    logger.info(f"Dispatcher: Found {len(active_user_ids)} users for nightly compression.")
    
    # 2. Fan out using the dispatcher
    for user_id in active_user_ids:
        dispatcher.dispatch(user_id)
        
    logger.info("Dispatcher: All tasks have been queued.")
