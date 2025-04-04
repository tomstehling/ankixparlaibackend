# utils.py
import json
from typing import Optional, List
import logging # Use logging instead of print for consistency

logger = logging.getLogger(__name__) # Create a logger for this module

def load_flashcards(filename: str) -> List[str]:
    """Loads Spanish sentences from the 'front' field of a JSON flashcard file."""
    logger.info(f"Loading learned content from '{filename}'...") # Use logger
    sentences = []
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list):
                for card in data:
                    if isinstance(card, dict):
                        sentence = card.get("front")
                        if sentence and isinstance(sentence, str) and sentence.strip():
                            sentences.append(sentence.strip())
            else:
                logger.warning(f"Expected '{filename}' to be a JSON list. Found {type(data)}.")
    except FileNotFoundError:
        logger.warning(f"Flashcard file '{filename}' not found.")
    except json.JSONDecodeError as e:
        logger.warning(f"Could not decode JSON from '{filename}'. Check format. Details: {e}")
    except Exception as e:
        logger.warning(f"Error processing flashcard file '{filename}': {e}")

    if sentences:
        logger.info(f"Successfully loaded {len(sentences)} sentences from '{filename}'.")
    else:
        logger.warning("No valid sentences loaded from flashcards.")
    return sentences

# --- CORRECTED FUNCTION ---
def load_prompt_from_template(template_filename: str) -> str:
    """
    Loads a prompt template string from a file.
    Does NOT perform any formatting.
    """
    logger.info(f"Loading prompt template from '{template_filename}'...") # Use logger
    try:
        with open(template_filename, 'r', encoding='utf-8') as f:
            template_content = f.read()
        if not template_content:
             logger.warning(f"Template file '{template_filename}' is empty.")
             # Return empty string or raise error depending on desired handling
             return ""
        logger.info(f"Successfully loaded template from '{template_filename}'.")
        return template_content
    except FileNotFoundError:
        logger.error(f"Prompt template file '{template_filename}' not found.")
        raise # Re-raise the exception
    except Exception as e:
        logger.error(f"Error reading template '{template_filename}': {e}", exc_info=True)
        raise # Re-raise