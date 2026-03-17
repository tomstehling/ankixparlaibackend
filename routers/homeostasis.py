import logging
from fastapi import APIRouter, Depends, BackgroundTasks, Request
from dependencies import verify_cron_secret
from sqlalchemy.ext.asyncio import AsyncSession
from services.orchestrator.session_engine import SessionEngine
from services.orchestrator.tools import CardGenerator, CardCompressor, CardDecompressor
from database.session import get_db_session

logger = logging.getLogger(__name__)
router = APIRouter()


async def run_homeostasis_for_user(
    session_factory,
    user_id: str,
    llm_handler=None
) -> dict:
    """
    Run homeostasis engine for a single user with proper Unit of Work pattern.
    
    Args:
        session_factory: Database session factory
        user_id: User ID to process
        llm_handler: Optional LLM handler for AI operations
        
    Returns:
        Dict with processing results
    """
    try:
        async with session_factory() as db_session:
            # Use Unit of Work pattern - isolated session per user
            session_engine = SessionEngine(db_session=db_session, user_id=user_id, llm_handler=llm_handler)
            
            # Evaluate user's workload
            action, metrics = await session_engine.evaluate_user_workload()
            
            results = {
                "user_id": user_id,
                "action": action.value,
                "metrics": metrics,
                "tools_executed": []
            }
            
            # Execute appropriate tools based on action
            if action.value == "generate_cards":
                generator = CardGenerator(llm_handler=llm_handler)
                generator_result = await generator.execute(db_session, user_id, target_count=5)
                results["tools_executed"].append(generator_result)
                
            elif action.value == "compress_cards":
                compressor = CardCompressor(llm_handler=llm_handler)
                compressor_result = await compressor.execute(db_session, user_id, max_due_cards=30)
                results["tools_executed"].append(compressor_result)
                
            elif action.value == "decompress_cards":
                decompressor = CardDecompressor(llm_handler=llm_handler)
                decompressor_result = await decompressor.execute(db_session, user_id, reactivate_count=10)
                results["tools_executed"].append(decompressor_result)
                
            # For maintain_status, no tools are executed
            
            logger.info(f"Homeostasis completed for user {user_id}: {action.value}")
            return results
            
    except Exception as e:
        logger.error(f"Error in homeostasis for user {user_id}: {e}")
        return {
            "user_id": user_id,
            "action": "error",
            "error": str(e),
            "tools_executed": []
        }


@router.post("/run-nightly-homeostasis", dependencies=[Depends(verify_cron_secret)])
async def trigger_nightly_homeostasis(
    background_tasks: BackgroundTasks,
    request: Request,
    db_session: AsyncSession = Depends(get_db_session)
):
    """
    Internal endpoint triggered by scheduler.
    Acts as the Dispatcher: Identifies users and fans out background workers.
    
    Uses the Factory & Unit of Work pattern to avoid dead connections:
    - Gets session factory from app.state (not open session)
    - Offloads to background tasks for immediate response
    - Each background worker manages its own isolated sessions
    """
    logger.info("Internal: Received nightly homeostasis trigger. Starting fan-out.")
    
    # Get session factory from app state (not the session from Depends)
    session_factory = request.app.state.db_session_factory
    llm_handler = getattr(request.app.state, "llm_handler", None)
    
    # Add background task to process all users
    background_tasks.add_task(
        run_homeostasis_for_all_users,
        session_factory,
        llm_handler
    )
    
    return {"status": "nightly homeostasis fan-out initiated"}


async def run_homeostasis_for_all_users(session_factory, llm_handler=None):
    """
    Background worker that processes all active users using Unit of Work pattern.
    
    Architecture:
    1. Global Fetch: Brief connection to get user list
    2. Per-User Isolation: New session for each user
    3. Safe Execution: Commit/rollback per user
    """
    try:
        # Step 1: Global fetch - get all active users
        logger.info("Fetching all active users for homeostasis processing...")
        
        async with session_factory() as global_session:
            from sqlalchemy import select
            from database import models
            import uuid
            
            query = select(models.User.id)
            result = await global_session.execute(query)
            user_ids = [str(row[0]) for row in result.fetchall()]
            
        logger.info(f"Found {len(user_ids)} users to process")
        
        # Step 2: Per-user isolation with Unit of Work pattern
        total_results = []
        successful_users = 0
        failed_users = 0
        
        for user_id_str in user_ids:
            try:
                user_id = uuid.UUID(user_id_str)
                result = await run_homeostasis_for_user(
                    session_factory=session_factory,
                    user_id=user_id,
                    llm_handler=llm_handler
                )
                
                total_results.append(result)
                
                if result["action"] != "error":
                    successful_users += 1
                    logger.debug(f"Processed user {user_id}: {result['action']}")
                else:
                    failed_users += 1
                    logger.warning(f"Failed to process user {user_id}: {result['error']}")
                    
                # Small delay to prevent overwhelming the database
                import asyncio
                await asyncio.sleep(0.1)
                
            except Exception as e:
                failed_users += 1
                logger.error(f"Critical error processing user {user_id_str}: {e}")
                total_results.append({
                    "user_id": user_id_str,
                    "action": "error",
                    "error": str(e),
                    "tools_executed": []
                })
        
        # Log summary
        logger.info(
            f"Homeostasis processing completed: "
            f"{successful_users} successful, {failed_users} failed, "
            f"total users: {len(user_ids)}"
        )
        
        # Log detailed results for debugging
        for result in total_results:
            if result["action"] in ["generate_cards", "compress_cards"]:
                tools = result.get("tools_executed", [])
                for tool in tools:
                    if tool.get("action") in ["generated_cards", "compressed_cards"]:
                        count = tool.get("count", tool.get("cards_processed", 0))
                        logger.info(f"User {result['user_id']}: {tool['action']} - {count} items")
        
        return {
            "total_users": len(user_ids),
            "successful_users": successful_users,
            "failed_users": failed_users,
            "results": total_results
        }
        
    except Exception as e:
        logger.error(f"Fatal error in homeostasis background worker: {e}")
        raise