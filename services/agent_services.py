import asyncio
import logging
import uuid
import json
from typing import List, Any
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from sqlalchemy.future import select
import database.crud as crud
from services.opportunity_engine import OpportunityEngine
import schemas

logger = logging.getLogger(__name__)

async def run_agent_tagger(
    note_id: int, 
    content: str, 
    session_factory: async_sessionmaker[AsyncSession]
):
    """
    Background task that simulates an AI agent analyzing note content 
    and applying CEFR/pedagogical tags.
    """
    logger.info(f"Background Agent: Starting analysis for Note ID {note_id}")
    
    try:
        # 1. Simulate LLM Latency (3 seconds)
        await asyncio.sleep(3)
        
        # 2. Mock Agent Logic: 
        # In a real scenario, this would call Gemini/OpenRouter to determine CEFR level.
        # For now, we use mock tag IDs. 
        # (Assuming tag IDs 1, 2 are 'A1' and 'Vocabulary' in a seeded database)
        mock_tag_ids = [1, 2] 
        
        logger.info(f"Background Agent: Analysis complete for Note ID {note_id}. Applying tags: {mock_tag_ids}")
        
        # 3. Apply tags using a new CRUD function
        async with session_factory() as session:
            await crud.add_note_tags(session, note_id, mock_tag_ids)
            
        logger.info(f"Background Agent: Successfully tagged Note ID {note_id}")
        
    except Exception as e:
        logger.error(f"Background Agent Error for Note ID {note_id}: {e}", exc_info=True)


async def run_card_generator_agent(
    user_id: uuid.UUID,
    session_factory: async_sessionmaker[AsyncSession],
    llm_handler: Any,
    prompt_template: str
):
    """
    Proactively generates new flashcards using context from user's recent notes
    and existing cards for the target concept to avoid redundancy.
    """
    logger.info(f"Endless Syllabus: Starting context-aware generation for User ID {user_id}")
    AGENT_GENERATED_TAG_ID = 103
    
    try:
        async with session_factory() as session:
            # 1. Use OpportunityEngine to find the best concept to teach next
            engine = OpportunityEngine()
            best_tag_id = await engine.evaluate_user_tags(session, user_id, "General Fluency")
            
            if not best_tag_id:
                logger.warning("Endless Syllabus: No suitable tags found for generation.")
                return

            # Fetch tag details
            tag_query = await session.execute(select(crud.models.Tag).where(crud.models.Tag.id == best_tag_id))
            tag = tag_query.scalar_one_or_none()
            if not tag:
                return

            # 2. Fetch Context: Recent user notes (thematic guide)
            recent_notes = await crud.get_recent_user_notes(session, user_id, limit=5)
            thematic_context = "\n".join([f"- {n.field1}: {n.field2}" for n in recent_notes])
            
            # 3. Fetch Context: Existing cards for this tag (avoid redundancy)
            existing_tag_notes = await crud.get_notes_by_tag(session, user_id, tag.id)
            avoid_list = "\n".join([f"- {n.field1}" for n in existing_tag_notes])

            # 4. Log Context to Console
            print("\n" + "="*50)
            print(f"CONTEXT-AWARE AGENT LOG")
            print(f"User ID: {user_id}")
            print(f"Target Concept: {tag.name} (ID: {tag.id})")
            print(f"Thematic Guide (Recent Notes):\n{thematic_context}")
            print(f"Avoid List (Existing Cards):\n{avoid_list}")
            print("="*50 + "\n")

            # 5. Prepare Prompt with Context
            custom_instructions = (
                f"Target Concept: {tag.name}. Description: {tag.description or ''}\n\n"
                f"THEMATIC CONTEXT (User's recent interests):\n{thematic_context}\n\n"
                f"DO NOT DUPLICATE THESE EXISTING CARDS:\n{avoid_list}\n\n"
                f"Generate new, unique cards that align with the user's recent themes if possible."
            )
            
            formatted_prompt = prompt_template.format(
                topic=tag.name,
                card_amount=3,
                custom_instructions_section=custom_instructions
            )
            
            # 6. Call LLM
            logger.info(f"Endless Syllabus: Calling LLM for {tag.name}...")
            response_text = await llm_handler.generate_one_off(formatted_prompt)
            
            # 7. Parse and Save
            cleaned_text = response_text.strip()
            if cleaned_text.startswith("```json"):
                cleaned_text = cleaned_text[7:-3].strip()
            elif cleaned_text.startswith("```"):
                cleaned_text = cleaned_text[3:-3].strip()
            
            start_brace = cleaned_text.find("{")
            end_brace = cleaned_text.rfind("}")
            if start_brace != -1 and end_brace != -1:
                cleaned_text = cleaned_text[start_brace : end_brace + 1]
            
            response_data = json.loads(cleaned_text)
            cards_data = response_data.get("cards", [])

            if not cards_data:
                logger.warning(f"Endless Syllabus: LLM returned no cards for tag {tag.name}")
                return

            notes_to_add = []
            for c in cards_data:
                # Add the 'agent-generated' tag ID 103 along with the concept tag
                note_content = schemas.NoteContent(
                    field1=c["front"], 
                    field2=c["back"], 
                    tags=c.get("tags", []) + [tag.name]
                )
                notes_to_add.append(note_content)
            
            user = await crud.get_user_by_id(session, user_id)
            if user:
                created_notes = await crud.add_notes_with_cards_bulk(session, user, notes_to_add)
                
                # Manually add the system tag 103 to each created note
                for note in created_notes:
                    await crud.add_note_tags(session, note.id, [AGENT_GENERATED_TAG_ID])
                
                await session.commit()
                logger.info(f"Endless Syllabus: Successfully generated {len(notes_to_add)} context-aware cards for {tag.name}")

    except Exception as e:
        logger.error(f"Endless Syllabus Error for User ID {user_id}: {e}", exc_info=True)
            