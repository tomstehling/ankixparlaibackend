import logging
import json
import re
from typing import List, Dict, Any, Optional
from services.graph_handler import GraphHandler
from schemas import NoteContent

logger = logging.getLogger(__name__)

class TaggerHandler:
    def __init__(self, llm_handler: Any, graph_handler: GraphHandler, system_prompt: str):
        """
        Initializes the TaggerHandler.
        
        Args:
            llm_handler: Initialized LLM handler (OpenRouterHandler).
            graph_handler: Initialized GraphHandler containing the knowledge graph.
            system_prompt: The system prompt to use for tagging.
        """
        self.llm_handler = llm_handler
        self.graph_handler = graph_handler
        self.system_prompt = system_prompt

    async def tag_notes(self, notes: List[NoteContent]) -> List[NoteContent]:
        """
        Uses the LLM to attach relevant tags to a list of notes.
        
        Args:
            notes: A list of NoteContent objects to be tagged.
            
        Returns:
            The list of NoteContent objects with attached tags.
        """
        if not notes:
            return []

        # 1. Get allowed tags from the graph
        # We fetch tag names from the graph nodes
        allowed_tags = []
        for node_id in self.graph_handler.graph.nodes:
            tag_name = self.graph_handler.graph.nodes[node_id].get('name')
            if tag_name:
                allowed_tags.append(tag_name)
        
        if not allowed_tags:
            logger.warning("No tags found in the knowledge graph. Tagging aborted.")
            return notes

        allowed_tags_str = ", ".join(allowed_tags)

        # 2. Format notes for LLM to keep calls minimal (batching)
        notes_to_tag = []
        for i, note in enumerate(notes):
            notes_to_tag.append({
                "index": i,
                "spanish": note.field1,
                "english": note.field2
            })
        
        notes_json_str = json.dumps(notes_to_tag, ensure_ascii=False)

        # 3. Build the full prompt
        full_prompt = (
            f"{self.system_prompt}\n\n"
            f"ALLOWED TAGS:\n{allowed_tags_str}\n\n"
            f"NOTES TO TAG (JSON):\n{notes_json_str}"
        )

        # 4. Call LLM
        try:
            logger.info(f"Sending batch of {len(notes)} notes to LLM for tagging.")
            response_text = await self.llm_handler.generate_one_off(full_prompt)
            
            # 5. Parse and Validate
            # Clean response text from potential markdown formatting
            clean_json = re.sub(r"```json\s*|\s*```", "", response_text).strip()
            data = json.loads(clean_json)
            tagged_results = data.get("tagged_notes", [])
            
            allowed_tags_set = set(allowed_tags)

            for result in tagged_results:
                idx = result.get("index")
                suggested_tags = result.get("tags", [])
                
                if idx is not None and 0 <= idx < len(notes):
                    # Filter for legal tags (strict validation)
                    legal_tags = [t for t in suggested_tags if t in allowed_tags_set]
                    
                    if len(legal_tags) < len(suggested_tags):
                        illegal = [t for t in suggested_tags if t not in allowed_tags_set]
                        logger.warning(f"LLM suggested illegal tags for note at index {idx}: {illegal}")
                    
                    # Initialize tags list if None
                    if notes[idx].tags is None:
                        notes[idx].tags = []
                    
                    # Merge unique tags
                    existing_tags = set(notes[idx].tags)
                    for lt in legal_tags:
                        if lt not in existing_tags:
                            notes[idx].tags.append(lt)
                            existing_tags.add(lt)
            
            logger.info(f"Successfully tagged {len(notes)} notes.")
            
        except json.JSONDecodeError as e:
            logger.error(f"LLM returned invalid JSON for tagging: {e}")
            logger.debug(f"Raw LLM response: {response_text}")
        except Exception as e:
            logger.error(f"An error occurred during tagging process: {e}", exc_info=True)

        return notes
