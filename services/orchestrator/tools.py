import logging
from typing import List, Optional, Dict, Any
from abc import ABC, abstractmethod
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
import database.models as models

logger = logging.getLogger(__name__)


class BaseTool(ABC):
    """Base class for all AI-powered tools used by the SessionEngine."""
    
    def __init__(self, llm_handler=None):
        self.llm_handler = llm_handler
        
    @abstractmethod
    async def execute(self, db_session: AsyncSession, user_id: uuid.UUID, **kwargs) -> Dict[str, Any]:
        """Execute the tool's specific task."""
        pass


class CardGenerator(BaseTool):
    """
    Tool for generating new cards to address low workload situations.
    Uses AI to create appropriate flashcards based on user's learning patterns.
    """
    
    async def execute(
        self, 
        db_session: AsyncSession, 
        user_id: uuid.UUID, 
        target_count: int = 5,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate new cards for the user.
        
        Args:
            db_session: Database session
            user_id: User to generate cards for
            target_count: Number of cards to generate
            
        Returns:
            Dict with generation results
        """
        try:
            logger.info(f"Generating {target_count} cards for user {user_id}")
            
            # Get user's existing tags and learning patterns
            user_tags = await self._get_user_tags(db_session, user_id)
            recent_cards = await self._get_recent_cards(db_session, user_id, limit=10)
            
            # Use LLM to generate new cards based on user's patterns
            if self.llm_handler:
                new_cards = await self._generate_cards_with_ai(
                    user_id=user_id,
                    existing_tags=user_tags,
                    recent_cards=recent_cards,
                    target_count=target_count
                )
            else:
                # Fallback: generate basic cards if no LLM available
                new_cards = await self._generate_fallback_cards(
                    db_session, user_id, target_count
                )
            
            # Save new cards to database
            created_cards = await self._save_cards(db_session, user_id, new_cards)
            
            return {
                "action": "generated_cards",
                "count": len(created_cards),
                "cards": created_cards
            }
            
        except Exception as e:
            logger.error(f"Error generating cards for user {user_id}: {e}")
            raise
            
    async def _get_user_tags(self, db_session: AsyncSession, user_id: uuid.UUID) -> List[models.Tag]:
        """Get user's tags and their scores."""
        query = select(models.Tag).join(
            models.UserTagScore
        ).where(
            models.UserTagScore.user_id == user_id,
            models.UserTagScore.score > 0.5  # Only get tags with positive scores
        ).order_by(models.UserTagScore.score.desc())
        
        result = await db_session.execute(query)
        return result.scalars().all()
        
    async def _get_recent_cards(self, db_session: AsyncSession, user_id: uuid.UUID, limit: int = 10) -> List[models.Card]:
        """Get user's most recent cards for pattern analysis."""
        query = select(models.Card).where(
            models.Card.user_id == user_id
        ).order_by(
            models.Card.created_at.desc()
        ).limit(limit)
        
        result = await db_session.execute(query)
        return result.scalars().all()
        
    async def _generate_cards_with_ai(
        self, 
        user_id: uuid.UUID, 
        existing_tags: List[models.Tag], 
        recent_cards: List[models.Card], 
        target_count: int
    ) -> List[Dict[str, str]]:
        """Generate new cards using AI based on user's learning patterns."""
        
        # Build prompt for card generation
        tag_names = [tag.name for tag in existing_tags[:5]]  # Top 5 tags
        recent_examples = [
            f"Front: {card.front}\nBack: {card.back}" 
            for card in recent_cards[:3]  # Top 3 recent cards
        ]
        
        prompt = f"""
Generate {target_count} new Spanish flashcards for a user who is learning the following topics: {', '.join(tag_names)}.

Based on the user's recent card patterns:
{chr(10).join(recent_examples)}

Create cards that:
1. Build on existing knowledge from the mentioned topics
2. Include appropriate difficulty progression
3. Cover different aspects (vocabulary, grammar, usage)
4. Are practical and useful for real communication

For each card, provide:
- Front: Spanish text (question/prompt)
- Back: English translation/explanation

Format response as JSON:
{{
    "cards": [
        {{
            "front": "Spanish text",
            "back": "English explanation"
        }}
    ]
}}
"""
        
        try:
            response = await self.llm_handler.generate_response(prompt)
            import json
            data = json.loads(response)
            return data.get("cards", [])
        except Exception as e:
            logger.warning(f"AI card generation failed, using fallback: {e}")
            return await self._generate_fallback_cards(None, user_id, target_count)
            
    async def _generate_fallback_cards(
        self, 
        db_session: AsyncSession, 
        user_id: uuid.UUID, 
        target_count: int
    ) -> List[Dict[str, str]]:
        """Generate basic fallback cards when AI is not available."""
        
        # Basic Spanish vocabulary cards as fallback
        basic_cards = [
            {"front": "Hola", "back": "Hello"},
            {"front": "Gracias", "back": "Thank you"},
            {"front": "Por favor", "back": "Please"},
            {"front": "¿Cómo estás?", "back": "How are you?"},
            {"front": "Buenos días", "back": "Good morning"},
        ]
        
        return basic_cards[:target_count]
        
    async def _save_cards(
        self, 
        db_session: AsyncSession, 
        user_id: uuid.UUID, 
        card_data: List[Dict[str, str]]
    ) -> List[models.Card]:
        """Save generated cards to database."""
        
        created_cards = []
        
        for card_info in card_data:
            # Create a new note for each card
            note = models.Note(
                user_id=user_id,
                field1=card_info["front"],
                field2=card_info["back"]
            )
            db_session.add(note)
            await db_session.flush()  # Get the note ID
            
            # Create the card
            card = models.Card(
                note_id=note.id,
                front=card_info["front"],
                back=card_info["back"],
                due_date=models.func.now()  # Due immediately
            )
            db_session.add(card)
            created_cards.append(card)
            
        await db_session.commit()
        logger.info(f"Created {len(created_cards)} new cards for user {user_id}")
        
        return created_cards


class CardCompressor(BaseTool):
    """
    Tool for compressing workload by consolidating or prioritizing cards.
    Uses AI to identify and handle high workload situations.
    """
    
    async def execute(
        self, 
        db_session: AsyncSession, 
        user_id: uuid.UUID, 
        max_due_cards: int = 30,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Compress user's workload by prioritizing and consolidating cards.
        
        Args:
            db_session: Database session
            user_id: User to compress workload for
            max_due_cards: Maximum number of due cards to maintain
            
        Returns:
            Dict with compression results
        """
        try:
            logger.info(f"Compressing workload for user {user_id}, target max due cards: {max_due_cards}")
            
            # Get user's due cards
            due_cards = await self._get_due_cards(db_session, user_id)
            current_due_count = len(due_cards)
            
            if current_due_count <= max_due_cards:
                logger.info(f"Workload already balanced: {current_due_count} due cards")
                return {
                    "action": "no_compression_needed",
                    "current_due_count": current_due_count,
                    "max_due_cards": max_due_cards
                }
            
            # Use AI to prioritize and consolidate cards
            if self.llm_handler:
                prioritized_cards = await self._prioritize_cards_with_ai(
                    due_cards, max_due_cards
                )
            else:
                # Fallback: simple prioritization by review count
                prioritized_cards = await self._simple_prioritize_cards(
                    due_cards, max_due_cards
                )
            
            # Update card states based on prioritization
            compression_results = await self._apply_compression(
                db_session, user_id, due_cards, prioritized_cards
            )
            
            return {
                "action": "compressed_cards",
                "original_due_count": current_due_count,
                "new_due_count": len(prioritized_cards),
                "cards_processed": len(due_cards),
                "compression_results": compression_results
            }
            
        except Exception as e:
            logger.error(f"Error compressing cards for user {user_id}: {e}")
            raise
            
    async def _get_due_cards(self, db_session: AsyncSession, user_id: uuid.UUID) -> List[models.Card]:
        """Get all due cards for the user."""
        query = select(models.Card).where(
            models.Card.user_id == user_id,
            models.Card.due_date <= models.func.now(),
            models.Card.state.in_([0, 1, 2])  # Active learning states
        ).order_by(models.Card.due_date.asc())
        
        result = await db_session.execute(query)
        return result.scalars().all()
        
    async def _prioritize_cards_with_ai(
        self, 
        due_cards: List[models.Card], 
        max_due_cards: int
    ) -> List[models.Card]:
        """Use AI to prioritize which cards should be kept in active rotation."""
        
        # Take the most urgent cards (due soonest)
        urgent_cards = due_cards[:max_due_cards]
        
        # Use AI to analyze and optimize the selection
        card_summaries = [
            f"Card {i+1}: Front='{card.front[:50]}...', Back='{card.back[:50]}...', Due='{card.due_date}'"
            for i, card in enumerate(due_cards[:20])  # Limit analysis to first 20 cards
        ]
        
        prompt = f"""
You are a Spanish learning expert. The user has {len(due_cards)} due cards but can only handle {max_due_cards} effectively.

Here are the due cards (most urgent first):
{chr(10).join(card_summaries)}

Based on learning science principles, recommend which cards should be prioritized for active review. Consider:
1. Frequency of vocabulary (more common words first)
2. Importance for communication
3. Logical learning progression
4. Balance between different types of knowledge

Return the indices (1-based) of the {max_due_cards} most important cards to keep active, separated by commas.
"""
        
        try:
            response = await self.llm_handler.generate_response(prompt)
            # Parse indices from response
            import re
            indices = re.findall(r'\d+', response)
            selected_indices = [int(i) - 1 for i in indices[:max_due_cards]]  # Convert to 0-based
            
            # Return the prioritized cards
            return [due_cards[i] for i in selected_indices if 0 <= i < len(due_cards)]
            
        except Exception as e:
            logger.warning(f"AI prioritization failed, using simple method: {e}")
            return await self._simple_prioritize_cards(due_cards, max_due_cards)
            
    async def _simple_prioritize_cards(
        self, 
        due_cards: List[models.Card], 
        max_due_cards: int
    ) -> List[models.Card]:
        """Simple prioritization: keep cards with fewest reviews (newer/less practiced)."""
        # Sort by review count (fewer reviews first) and then due date
        sorted_cards = sorted(
            due_cards,
            key=lambda card: (card.review_count or 0, card.due_date)
        )
        return sorted_cards[:max_due_cards]
        
    async def _apply_compression(
        self, 
        db_session: AsyncSession, 
        user_id: uuid.UUID, 
        all_due_cards: List[models.Card], 
        active_cards: List[models.Card]
    ) -> Dict[str, Any]:
        """Apply compression by changing card states."""
        
        active_ids = {card.id for card in active_cards}
        
        processed = 0
        kept_active = 0
        suspended = 0
        
        for card in all_due_cards:
            processed += 1
            if card.id in active_ids:
                # Keep this card active
                kept_active += 1
            else:
                # Suspend this card (move to learning state 3 = suspended)
                card.state = 3  # Assuming state 3 is for suspended cards
                suspended += 1
                
        await db_session.commit()
        
        return {
            "cards_processed": processed,
            "kept_active": kept_active,
            "suspended": suspended
        }