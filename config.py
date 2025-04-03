# config.py
"""
Configuration settings for the Spanish Chatbot application.
"""

import os   
from dotenv import load_dotenv

load_dotenv() # Load environment variables from .env file for local dev

# --- Existing config ---
# GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# MODEL_NAME = "gemini-1.5-flash"
# DATABASE_FILE = "chatbot_cards.db"
# ... etc ...

# --- New Security Config ---
# Generate a strong secret key, e.g., using: openssl rand -hex 32
# Store it in your .env file locally and in your Cloud Run secrets
SECRET_KEY = os.getenv("SECRET_KEY", "a_very_bad_default_secret_key_CHANGE_ME")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30 # Access token lifetime (e.g., 30 minutes)
# You might also add REFRESH_TOKEN_EXPIRE_DAYS = 7 for refresh tokens later

if SECRET_KEY == "a_very_bad_default_secret_key_CHANGE_ME":
    print("\n" + "*"*60)
    print("WARNING: Using default SECRET_KEY. Please generate a strong key")
    print("         and set it as an environment variable.")
    print("         Example: openssl rand -hex 32")
    print("*"*60 + "\n")

# --- Gemini Model Configuration ---
GEMINI_MODEL_NAME = "gemini-1.5-flash-latest"

# --- File Paths ---
ANKI_FLASHCARDS_FILE = "flashcards.json"
TANDEM_PROMPT_TEMPLATE_FILE = "./system_prompts/system_prompt_template.txt"
TEACHER_PROMPT_TEMPLATE_FILE = "./system_prompts/teacher_prompt_template.txt"
SYSTEM_PROMPT_TEMPLATE = "system_prompts/system_prompt_template.txt"
TEACHER_PROMPT_TEMPLATE = "system_prompts/teacher_prompt_template.txt"
# Deprecating CARD_CREATOR_PROMPT - replaced by interactive flow
# CARD_CREATOR_PROMPT = "system_prompts/card_creator_prompt.txt"
SENTENCE_PROPOSER_PROMPT = "system_prompts/sentence_proposer_prompt.txt"
SENTENCE_VALIDATOR_PROMPT = "system_prompts/sentence_validator_prompt.txt"


# ... rest of config ...

# --- Command Triggers ---
# Teacher command is checked directly as '? ' in chatbot.py run() method
CARD_COMMAND = "!card" # Command to trigger flashcard creation

# --- AnkiConnect Configuration ---
ANKICONNECT_URL = "http://localhost:8765" # Default AnkiConnect URL

# !!! IMPORTANT: User must configure these Anki settings !!!
# vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv
# Replace with the exact name of the deck you want cards added to
ANKI_DECK_NAME = "ankixparlai" # Example: "Spanish::Vocabulary"

# Replace with the exact name of the Note Type you use for vocabulary
ANKI_MODEL_NAME = "Basic (and reversed card)" # Example: "Basic", "Basic (and reversed card)"

# Field names within your Anki Note Type that correspond to Front and Back
# For the default "Basic" model, these are typically "Front" and "Back"
ANKI_FIELD_FRONT = "Front"
ANKI_FIELD_BACK = "Back"
# ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

# --- Other Settings ---
# (Add any other configuration constants here in the future)