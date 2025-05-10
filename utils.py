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

    import logging
from bs4 import BeautifulSoup
# You might need to install beautifulsoup4: pip install beautifulsoup4

logger = logging.getLogger(__name__)

def strip_html_bs4(html_content: str) -> str:
    """Strips HTML tags from a string using BeautifulSoup."""
    if not isinstance(html_content, str) or not html_content:
        return ""
    try:
        # Use 'html.parser' which is built-in, requires no extra C libraries like lxml
        soup = BeautifulSoup(html_content, "html.parser")

        # Replace common block tags with newlines before getting text
        # to preserve some basic structure (optional but often helpful)
        for tag in soup(['br', 'p', 'div']):
             tag.append('\n')

        # Get text, joining pieces with space, and stripping leading/trailing whitespace
        text = soup.get_text(separator=" ", strip=True)

        # Optional: Normalize multiple newlines/spaces resulting from replacements
        text = ' '.join(text.split()) # Replace multiple spaces/newlines with single space

        return text
    except Exception as e:
        # Log the error but return the original (stripped) content as fallback
        logger.warning(f"BeautifulSoup failed to parse/strip content. Returning raw (stripped). Error: {e}. Content: '{html_content[:100]}...'")
        return html_content.strip()