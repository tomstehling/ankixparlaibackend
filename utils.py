# utils.py
"""
Utility functions for file loading (prompts, flashcards) for the chatbot application.
"""

import json
from typing import Optional, List

def load_flashcards(filename: str) -> List[str]:
    """Loads Spanish sentences from the 'front' field of a JSON flashcard file."""
    print(f"Loading learned content from '{filename}'...")
    sentences = []
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list):
                for card in data:
                    if isinstance(card, dict):
                        # Assuming 'front' key holds the Spanish sentence
                        sentence = card.get("front")
                        if sentence and isinstance(sentence, str) and sentence.strip():
                            sentences.append(sentence.strip())
            else:
                print(f"Warning: Expected '{filename}' to be a JSON list. Found {type(data)}.")
    except FileNotFoundError:
        # This is common if the user hasn't exported cards yet. Treat as warning.
        print(f"Warning: Flashcard file '{filename}' not found.")
    except json.JSONDecodeError as e:
        # This indicates a problem with the file format. Treat as warning.
        print(f"Warning: Could not decode JSON from '{filename}'. Check format. Details: {e}")
    except Exception as e:
        # Catch other potential file reading/processing errors. Treat as warning.
        print(f"Warning: Error processing flashcard file '{filename}': {e}")

    if sentences:
        print(f"Successfully loaded {len(sentences)} sentences from '{filename}'.")
    else:
        # This will be printed if file not found, empty, or no valid 'front' fields found.
        print("Warning: No valid sentences loaded from flashcards.")
    return sentences

def load_prompt_from_template(template_filename: str, learned_sentences: Optional[List[str]] = None) -> str:
    """
    Loads a prompt from a template file, optionally injecting learned sentences
    using the {learned_content} placeholder.
    """
    print(f"Loading prompt template from '{template_filename}'...")
    try:
        with open(template_filename, 'r', encoding='utf-8') as f:
            template_content = f.read()

        final_prompt = template_content # Default to original content

        if '{learned_content}' in template_content:
            # Only format if placeholder exists
            learned_content_str = "(No learned sentences provided)" # Default placeholder text
            if learned_sentences is not None: # Check if sentences were actually passed
                if learned_sentences: # Check if the list is not empty
                     learned_content_str = "\n".join(f"- {s}" for s in learned_sentences)
                else:
                     learned_content_str = "(Learned sentences list is empty)"

            # Perform the formatting using the determined content string
            try:
                final_prompt = template_content.format(learned_content=learned_content_str)
            except KeyError:
                 # This should ideally not happen if the placeholder check above works, but good safety.
                 print(f"Warning: Placeholder '{{learned_content}}' found but formatting failed in '{template_filename}'. Using raw template.")
                 final_prompt = template_content # Fallback to raw template on format error

        print(f"Successfully loaded prompt from '{template_filename}'.")
        return final_prompt

    except FileNotFoundError:
        # Critical error if a prompt template is missing
        print(f"FATAL: Prompt template file '{template_filename}' not found.")
        raise # Re-raise the exception to stop initialization
    except Exception as e:
        # Catch other potential file reading/processing errors
        print(f"FATAL: Error reading/processing template '{template_filename}': {e}")
        raise # Re-raise the exception