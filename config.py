# config.py
"""
Configuration settings for the Spanish Chatbot application.
"""

import os
from dotenv import load_dotenv
load_dotenv() # Load environment variables from .env file for local dev

# --- Core Application Settings ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") # CRITICAL: Needs to be set in environment
if not GEMINI_API_KEY:
    print("\n" + "*"*60)
    print("ERROR: GEMINI_API_KEY environment variable not set.")
    print("       The application requires a valid Gemini API key to function.")
    print("*"*60 + "\n")
    # Consider exiting here if the key is absolutely mandatory for startup
    # import sys
    # sys.exit(1)

DATABASE_FILE = os.getenv("DATABASE_FILE", "chatbot_cards.db") # Default DB name

# --- Gemini Model Configuration ---
GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-1.5-flash-latest") # Your preferred model

# --- Security Configuration ---
# Generate a strong secret key, e.g., using: openssl rand -hex 32
# Store it in your .env file locally and in your Cloud Run secrets / environment variables
SECRET_KEY = os.getenv("SECRET_KEY", "a_very_bad_default_secret_key_CHANGE_ME")
ALGORITHM = "HS256" # Algorithm for JWT signing
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30)) # Access token lifetime

# Warning for default secret key
if SECRET_KEY == "a_very_bad_default_secret_key_CHANGE_ME":
    print("\n" + "*"*60)
    print("WARNING: Using default SECRET_KEY. Please generate a strong key")
    print("         and set it as an environment variable (SECRET_KEY).")
    print("         Example command: openssl rand -hex 32")
    print("*"*60 + "\n")

# --- File Paths ---
# Directory for system prompts (adjust if your structure differs)
PROMPT_DIR = "system_prompts"

SYSTEM_PROMPT_TEMPLATE = os.path.join(PROMPT_DIR, "system_prompt_template.txt")
TEACHER_PROMPT_TEMPLATE = os.path.join(PROMPT_DIR, "teacher_prompt_template.txt")
SENTENCE_PROPOSER_PROMPT = os.path.join(PROMPT_DIR, "sentence_proposer_prompt.txt")
SENTENCE_VALIDATOR_PROMPT = os.path.join(PROMPT_DIR, "sentence_validator_prompt.txt")

# Optional file for Anki integration (if used by external scripts/sync)
ANKI_FLASHCARDS_FILE = os.getenv("ANKI_FLASHCARDS_FILE", "flashcards.json")

# --- Spaced Repetition System (SRS) Configuration ---
# These values control the card scheduling logic
LEARNING_STEPS_MINUTES: list[int] = [1, 10] # Intervals in minutes for learning phase
DEFAULT_EASY_INTERVAL_DAYS: float = 4.0   # Initial interval (days) after graduating or 'easy' on new
DEFAULT_EASE_FACTOR: float = 2.5          # Starting ease factor for new cards (Anki default)
MIN_EASE_FACTOR: float = 1.3              # Minimum ease factor allowed
LAPSE_INTERVAL_MULTIPLIER: float = 0.0    # Interval multiplier on 'again' (0=reset to learning steps)
DEFAULT_INTERVAL_MODIFIER: float = 1.0    # Base multiplier for 'good' reviews (adjust as needed, 1.0 is neutral)
EASY_BONUS: float = 1.3                   # Extra multiplier for 'easy' reviews (Anki default)

# --- Command Triggers (Potentially less relevant for pure API backend) ---
CARD_COMMAND = "!card" # Command to trigger flashcard creation (if used elsewhere)

# --- AnkiConnect Configuration (For external Anki integration scripts/tools) ---
# Note: The core FastAPI backend does NOT directly use these for its internal SRS.
# These are relevant if you have a separate script or plugin talking to AnkiConnect.
ANKICONNECT_URL = os.getenv("ANKICONNECT_URL", "http://localhost:8765") # Default AnkiConnect URL

# !!! User must configure these if using external Anki integration !!!
ANKI_DECK_NAME = os.getenv("ANKI_DECK_NAME", "ankixparlai") # Target deck name in Anki
ANKI_MODEL_NAME = os.getenv("ANKI_MODEL_NAME", "Basic (and reversed card)") # Note type in Anki
ANKI_FIELD_FRONT = os.getenv("ANKI_FIELD_FRONT", "Front") # Field name for the front of the card
ANKI_FIELD_BACK = os.getenv("ANKI_FIELD_BACK", "Back")   # Field name for the back of the card

# --- Other Settings ---
# (Add any other configuration constants here in the future)

print(f"--- Configuration Loaded ---")
print(f"Database file: {DATABASE_FILE}")
print(f"Gemini Model: {GEMINI_MODEL_NAME}")
print(f"Prompt Directory: {PROMPT_DIR}")
# Add other print statements if helpful for debugging startup
# print(f"Default Ease: {DEFAULT_EASE_FACTOR}")
print(f"--------------------------")
