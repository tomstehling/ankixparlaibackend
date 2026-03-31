import uuid
import logging
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
import database.crud as crud

logger = logging.getLogger(__name__)

class OpportunityEngine:
    def __init__(
        self, 
        w_readiness: float = 0.4, 
        w_uncertainty: float = 0.2, 
        w_weakness: float = 0.4
    ):
        self.w_readiness = w_readiness
        self.w_uncertainty = w_uncertainty
        self.w_weakness = w_weakness
        
        # Normalized difficulty scores based on CEFR level
        self.cefr_difficulty_map = {
            "A1": 1.0,
            "A2": 0.8,
            "B1": 0.6,
            "B2": 0.4,
            "C1": 0.2,
            "C2": 0.1
        }

    def _calculate_readiness(self, prereq_scores: List[float], cefr_level: str) -> float:
        """
        Calculates how ready a user is for a new concept.
        Formula: (0.7 * Average Prerequisite Mastery) + (0.3 * Difficulty Score)
        Filter: If any prerequisite score < 70, Readiness = 0.
        """
        if not prereq_scores:
            # No prerequisites means user is ready by default
            # We still apply difficulty weighting
            difficulty_score = self.cefr_difficulty_map.get(cefr_level, 0.5)
            return difficulty_score

        # Go/No-Go Filter: Strictly less than 70
        if any(score < 70.0 for score in prereq_scores):
            return 0.0

        avg_mastery = sum(prereq_scores) / len(prereq_scores)
        # Normalize avg_mastery to 0.0-1.0 assuming scores are 0-100
        normalized_mastery = avg_mastery / 100.0
        difficulty_score = self.cefr_difficulty_map.get(cefr_level, 0.5)
        
        return (0.7 * normalized_mastery) + (0.3 * difficulty_score)

    def _calculate_weakness(
        self, 
        total_lapses: int, 
        opportunity_count: int, 
        recent_failures: int, 
        total_recent_reviews: int, 
        hard_grades: int, 
        success_grades: int
    ) -> float:
        """
        Calculates a 'Weakness' score representing concepts the user struggles with.
        Formula: (0.5 * Instability) + (0.3 * Recency) + (0.2 * Low Confidence)
        """
        instability = total_lapses / max(1, opportunity_count)
        recency = recent_failures / max(1, total_recent_reviews)
        low_confidence = hard_grades / max(1, success_grades)
        
        return (0.5 * instability) + (0.3 * recency) + (0.2 * low_confidence)

    def _calculate_uncertainty(self, opportunity_count: int) -> float:
        """
        Formula: 1 / (1 + opportunity_count)
        Highlights concepts the user hasn't seen much.
        """
        return 1.0 / (1.0 + opportunity_count)

    def _get_goal_multiplier(self, tag_name: str, user_goal: str) -> float:
        """
        Mock method for goal relevance. Returns 1.0 for now.
        """
        return 1.0

    async def evaluate_user_tags(
        self, 
        db_session: AsyncSession, 
        user_id: uuid.UUID, 
        user_goal: str
    ) -> Optional[int]:
        """
        Main orchestration logic:
        1. Fetch all tags and user data.
        2. Loop through tags to calculate Opportunity Scores.
        3. Return the tag_id with the highest score.
        """
        logger.info(f"Opportunity Engine: Evaluating tags for User ID {user_id}")
        
        # 1. Fetch data from CRUD layer
        all_tags = await crud.get_all_tags(db_session)
        user_scores = await crud.get_user_tag_scores(db_session, user_id)
        
        best_tag_id = None
        max_score = -1.0
        
        for tag in all_tags:
            # Data for current tag
            user_tag_score = user_scores.get(tag.id)
            opportunity_count = user_tag_score.opportunity_count if user_tag_score else 0
            total_lapses = user_tag_score.total_lapses if user_tag_score else 0
            
            # A. Calculate Readiness
            prereq_ids = await crud.get_tag_prerequisites(db_session, tag.id)
            prereq_scores = [
                user_scores.get(pid).score if user_scores.get(pid) else 0.0 
                for pid in prereq_ids
            ]
            readiness = self._calculate_readiness(prereq_scores, tag.cefr_level)
            
            # Optimization: If readiness is 0, total score will be severely impacted (though not necessarily 0)
            # However, concepts with 0 readiness shouldn't be recommended.
            if readiness == 0.0 and prereq_ids:
                continue

            # B. Calculate Weakness
            metrics = await crud.get_recent_review_metrics(db_session, user_id, tag.id)
            weakness = self._calculate_weakness(
                total_lapses=total_lapses,
                opportunity_count=opportunity_count,
                recent_failures=metrics["recent_failures"],
                total_recent_reviews=metrics["total_recent_reviews"],
                hard_grades=metrics["hard_grades"],
                success_grades=metrics["success_grades"]
            )
            
            # C. Calculate Uncertainty
            uncertainty = self._calculate_uncertainty(opportunity_count)
            
            # D. Calculate Final Opportunity Score
            weighted_base = (
                (self.w_readiness * readiness) + 
                (self.w_uncertainty * uncertainty) + 
                (self.w_weakness * weakness)
            )
            
            goal_multiplier = self._get_goal_multiplier(tag.name, user_goal)
            final_score = weighted_base * goal_multiplier
            
            if final_score > max_score:
                max_score = final_score
                best_tag_id = tag.id
                
        logger.info(f"Opportunity Engine: Best concept for user is Tag ID {best_tag_id} with score {max_score:.4f}")
        return best_tag_id
