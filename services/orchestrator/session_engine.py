import logging
from typing import Optional, List
from enum import Enum
import datetime
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
import database.models as models
import database.crud as crud

logger = logging.getLogger(__name__)


class WorkloadAction(Enum):
    """Enum representing possible actions to balance user workload"""
    GENERATE_CARDS = "generate_cards"
    COMPRESS_CARDS = "compress_cards"
    MAINTAIN_STATUS = "maintain_status"


class SessionEngine:
    """
    The Orchestrator: Evaluates user's workload bounds and decides which actions to take.
    Deletes stale 14-day-old cards and determines if workload needs balancing.
    """
    
    def __init__(self, llm_handler=None):
        self.llm_handler = llm_handler
        
    async def evaluate_user_workload(
        self, 
        db_session: AsyncSession, 
        user_id: uuid.UUID
    ) -> tuple[WorkloadAction, dict]:
        """
        Evaluate user's current workload and return recommended action.
        
        Args:
            db_session: Database session
            user_id: User to evaluate
            
        Returns:
            tuple: (recommended_action, metrics_dict)
        """
        try:
            # Get user's current workload metrics
            metrics = await self._calculate_workload_metrics(db_session, user_id)
            
            # Delete stale cards older than 14 days
            stale_deleted = await self._delete_stale_cards(db_session, user_id)
            if stale_deleted > 0:
                logger.info(f"Deleted {stale_deleted} stale cards for user {user_id}")
                # Recalculate metrics after cleanup
                metrics = await self._calculate_workload_metrics(db_session, user_id)
            
            # Determine appropriate action based on workload bounds
            action = self._determine_workload_action(metrics)
            
            return action, metrics
            
        except Exception as e:
            logger.error(f"Error evaluating workload for user {user_id}: {e}")
            raise
            
    async def _calculate_workload_metrics(
        self, 
        db_session: AsyncSession, 
        user_id: uuid.UUID
    ) -> dict:
        """Calculate current workload metrics for a user."""
        
        # Count due cards (cards that need review)
        due_query = select(func.count(models.Card.id)).where(
            models.Card.user_id == user_id,
            models.Card.due_date <= func.now(),
            models.Card.state.in_([0, 1, 2])  # Active learning states
        )
        due_result = await db_session.execute(due_query)
        due_count = due_result.scalar() or 0
        
        # Count total active cards
        total_query = select(func.count(models.Card.id)).where(
            models.Card.user_id == user_id,
            models.Card.state.in_([0, 1, 2])  # Active learning states
        )
        total_result = await db_session.execute(total_query)
        total_count = total_result.scalar() or 0
        
        # Count recent reviews (last 7 days)
        week_ago = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=7)
        recent_reviews_query = select(func.count(models.ReviewLog.id)).where(
            models.ReviewLog.user_id == user_id,
            models.ReviewLog.review_time >= week_ago
        )
        recent_reviews_result = await db_session.execute(recent_reviews_query)
        recent_reviews = recent_reviews_result.scalar() or 0
        
        return {
            "due_count": due_count,
            "total_count": total_count,
            "recent_reviews": recent_reviews,
            "review_rate": recent_reviews / 7 if recent_reviews > 0 else 0,
        }
        
    def _determine_workload_action(self, metrics: dict) -> WorkloadAction:
        """
        Determine appropriate action based on workload metrics.
        
        Logic:
        - If due_count is very high (>50) and user is not reviewing much: COMPRESS
        - If due_count is very low (<5) and total_count is low: GENERATE  
        - If workload is in reasonable bounds: MAINTAIN
        """
        due_count = metrics["due_count"]
        total_count = metrics["total_count"]
        review_rate = metrics["review_rate"]
        
        # High workload due pile but low review activity - suggest compression
        if due_count > 50 and review_rate < 5:
            logger.info(f"High workload detected: {due_count} due cards, {review_rate} reviews/day")
            return WorkloadAction.COMPRESS_CARDS
            
        # Low workload - suggest generation
        elif due_count < 5 and total_count < 20:
            logger.info(f"Low workload detected: {due_count} due cards, {total_count} total cards")
            return WorkloadAction.GENERATE_CARDS
            
        # Balanced workload
        else:
            logger.info(f"Balanced workload detected: {due_count} due cards, {review_rate} reviews/day")
            return WorkloadAction.MAINTAIN_STATUS
            
    async def _delete_stale_cards(
        self, 
        db_session: AsyncSession, 
        user_id: uuid.UUID
    ) -> int:
        """Delete cards that are older than 14 days and haven't been reviewed."""
        
        cutoff_date = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=14)
        
        # Find old cards that haven't been reviewed recently
        stale_query = select(models.Card).where(
            models.Card.user_id == user_id,
            models.Card.created_at < cutoff_date,
            models.Card.last_review.is_(None),
            models.Card.state.in_([0, 1, 2])  # Only delete active cards
        )
        
        stale_result = await db_session.execute(stale_query)
        stale_cards = stale_result.scalars().all()
        
        if stale_cards:
            card_ids = [card.id for card in stale_cards]
            # Delete related review logs first
            await db_session.execute(
                delete(models.ReviewLog).where(models.ReviewLog.card_id.in_(card_ids))
            )
            # Delete the cards
            await db_session.execute(
                delete(models.Card).where(models.Card.id.in_(card_ids))
            )
            await db_session.commit()
            
            logger.info(f"Deleted {len(stale_cards)} stale cards for user {user_id}")
            return len(stale_cards)
            
        return 0