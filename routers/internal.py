import logging
from fastapi import APIRouter, Depends, BackgroundTasks, Request
from dependencies import verify_cron_secret
from database.session import get_db_session
from sqlalchemy.ext.asyncio import AsyncSession
from services.dispatcher_service import fan_out_compression_tasks, FastAPIBackgroundDispatcher

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/run-nightly-compression", dependencies=[Depends(verify_cron_secret)])
async def trigger_nightly_compression(
    background_tasks: BackgroundTasks,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session)
):
    """
    Internal endpoint triggered by GPC Scheduler.
    Acts as the Dispatcher: Identifies users and fans out workers.
    """
    logger.info("Internal: Received nightly compression trigger. Starting Fan-Out.")
    
    # Initialize the Dispatcher Adapter
    dispatcher = FastAPIBackgroundDispatcher(
        background_tasks=background_tasks,
        session_factory=request.app.state.db_session_factory
    )
    
    # Orchestrate the fan-out
    await fan_out_compression_tasks(db_session, dispatcher)
    
    return {"status": "nightly compression fan-out completed"}
