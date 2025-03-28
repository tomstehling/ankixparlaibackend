# config.py
"""
Configuration settings for the Spanish Chatbot application.
"""

import os

# --- Gemini Model Configuration ---
MODEL_NAME = "gemini-1.5-flash-latest"

# --- File Paths ---
FLASHCARD_FILE = "flashcards.json"
TANDEM_PROMPT_TEMPLATE_FILE = "system_prompt_template.txt"
TEACHER_PROMPT_TEMPLATE_FILE = "teacher_prompt_template.txt"
CARD_CREATOR_PROMPT_FILE = "card_creator_prompt.txt"

# --- Command Triggers ---
# Teacher command is checked directly as '? ' in chatbot.py run() method
CARD_COMMAND = "!card" # Command to trigger flashcard creation

# --- AnkiConnect Configuration ---
ANKICONNECT_URL = "http://localhost:8765" # Default AnkiConnect URL

# !!! IMPORTANT: User must configure these Anki settings !!!
# vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv
# Replace with the exact name of the deck you want cards added to
ANKI_DECK_NAME = "Spanish::Chatbot" # Example: "Spanish::Vocabulary"

# Replace with the exact name of the Note Type you use for vocabulary
ANKI_MODEL_NAME = "Basic" # Example: "Basic", "Basic (and reversed card)"

# Field names within your Anki Note Type that correspond to Front and Back
# For the default "Basic" model, these are typically "Front" and "Back"
ANKI_FIELD_FRONT = "Front"
ANKI_FIELD_BACK = "Back"
# ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

# --- Other Settings ---
# (Add any other configuration constants here in the future)