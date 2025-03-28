# chatbot.py

import os
from dotenv import load_dotenv
load_dotenv() # Loads environment variables from .env file
import google.generativeai as genai
import sys
import json
import re
import requests
from typing import Optional, List, Dict, Any

# --- Import configuration ---
import config

# --- Import custom modules ---
from anki_handler import AnkiConnector
import utils # Import the new utils module

class Chatbot:
    """
    Orchestrates the chatbot application, using handlers and utilities.
    """

    def __init__(self):
        """Initializes the chatbot and its handlers."""
        print("Initializing Chatbot...")
        self.model: Optional[genai.GenerativeModel] = None
        self.tandem_chat: Optional[genai.ChatSession] = None
        self.learned_sentences: List[str] = []
        self.tandem_system_prompt: Optional[str] = None
        self.teacher_system_prompt: Optional[str] = None
        self.card_creator_prompt: Optional[str] = None
        self.anki_connector: Optional[AnkiConnector] = None
        self.anki_available: bool = False

        try:
            self._configure_api()
            # --- Use utils function to load flashcards ---
            self.learned_sentences = utils.load_flashcards(config.FLASHCARD_FILE)
            # --- Load prompts using utils function ---
            self._load_prompts()
            # --- ---
            self.model = genai.GenerativeModel(config.MODEL_NAME)
            print("Chatbot base model initialized.")
            self.anki_connector = AnkiConnector(
                anki_connect_url=config.ANKICONNECT_URL,
                deck_name=config.ANKI_DECK_NAME,
                model_name=config.ANKI_MODEL_NAME,
                field_front=config.ANKI_FIELD_FRONT,
                field_back=config.ANKI_FIELD_BACK
            )
            self.anki_available = self.anki_connector.check_connection()

        except Exception as e:
            print(f"FATAL: Chatbot initialization failed: {e}")
            sys.exit(1)

    def _configure_api(self):
        """Configures the Generative AI client."""
        # (This method remains unchanged)
        print("Configuring API...")
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key: raise ValueError("GOOGLE_API_KEY environment variable not set.")
        genai.configure(api_key=api_key)
        print("Successfully configured Gemini API.")

    # REMOVED: _load_flashcards method (now in utils.py)
    # REMOVED: _load_prompt_from_template method (now in utils.py)

    def _load_prompts(self):
        """Loads system prompts for all roles using the utility function."""
        # Call the imported function from utils
        self.tandem_system_prompt = utils.load_prompt_from_template(
            config.TANDEM_PROMPT_TEMPLATE_FILE, learned_sentences=self.learned_sentences
        )
        self.teacher_system_prompt = utils.load_prompt_from_template(
            config.TEACHER_PROMPT_TEMPLATE_FILE, learned_sentences=None # Explicitly pass None
        )
        self.card_creator_prompt = utils.load_prompt_from_template(
            config.CARD_CREATOR_PROMPT_FILE, learned_sentences=None # Explicitly pass None
        )

    def _initialize_tandem_chat(self):
        """Initializes the Tandem chat session."""
        # (This method remains unchanged)
        if not self.tandem_system_prompt: return False
        print("\nInitializing Tandem chat...")
        try:
            tandem_model_instance = genai.GenerativeModel(config.MODEL_NAME, system_instruction=self.tandem_system_prompt)
            self.tandem_chat = tandem_model_instance.start_chat(history=[])
            print("Tandem chat initialized.")
            return True
        except Exception as e: print(f"Error initializing Tandem chat: {e}"); self.tandem_chat = None; return False

    def get_teacher_explanation(self, query: str) -> str:
        """Handles the Teacher role request."""
        # (This method remains unchanged)
        if not self.model or not self.teacher_system_prompt: return "Error: Teacher components missing."
        print(f"\n--- Requesting Teacher Explanation: '{query}' ---")
        try:
            prompt = f"{self.teacher_system_prompt}\n\n--- User Query ---\nPlease explain: \"{query}\""
            print("Sending Teacher request...")
            response = self.model.generate_content(prompt)
            if response.text: return response.text
            else: return "Teacher explanation empty/blocked."
        except Exception as e: print(f"Teacher error: {e}"); return "Error getting explanation."

    def handle_tandem_message(self, user_input: str) -> str:
        """Handles sending a message to the Tandem role's chat session."""
        # (This method remains unchanged)
        if not self.tandem_chat:
             if not self._initialize_tandem_chat(): return "Error: Tandem chat unavailable."
        print("\nSending Tandem message...")
        try:
            response = self.tandem_chat.send_message(user_input)
            if response.text: return response.text
            else: return "Tandem response empty/blocked."
        except Exception as e: print(f"\nTandem error: {e}"); return "Error during conversation."

    def add_card_to_anki(self, spanish_query: str):
        """Generates flashcard data via AI and uses AnkiConnector to add it."""
        # (This method remains unchanged)
        if not self.model or not self.card_creator_prompt: print("Error: Card Creator components missing."); return
        if not self.anki_connector: print("Error: AnkiConnector not available."); return

        print(f"\n--- Generating Flashcard Data for: '{spanish_query}' ---")
        card_data_text = ""
        try:
            prompt_for_creator = f"{self.card_creator_prompt}\n\nInput: {spanish_query}"
            print("Sending Card Creator request...")
            response = self.model.generate_content(prompt_for_creator)

            if not response.text: print("Card Creator AI returned empty."); return
            card_data_text = response.text.strip()
            print(f"AI Card Data: {card_data_text}")

            parts = [p.strip() for p in card_data_text.split("||")]
            if len(parts) != 4:
                print(f"Error: Cannot parse AI response: {card_data_text}"); print(f"---\n{card_data_text}\n---"); return

            spanish_front, english_back, grammar_info, topic_tag = parts
            tags = [tag.strip().replace(" ", "_") for tag in [grammar_info, topic_tag] if tag.strip()]

            note_id = self.anki_connector.add_note(front=spanish_front, back=english_back, tags=tags)

            if note_id is None:
                print("--- Card Data (Manual Copy) ---")
                print(f"Front: {spanish_front}\nBack: {english_back}\nTags: {', '.join(tags)}")
                print("-------------------------------")

        except Exception as e:
            print(f"Error during card creation: {e}")
            if card_data_text: print(f"--- Raw AI Card Data ---\n{card_data_text}\n------------------------")

    def run(self):
        """Starts and manages the main chat loop."""
        # (This method remains unchanged)
        print("\n--- Starting Spanish Tandem Partner ---")
        if not self._initialize_tandem_chat(): print("Failed Tandem init. Exiting."); return

        print(f"Type your Spanish message.")
        print(f"Use '? [word/phrase]' for an English explanation.")
        print(f"Use '{config.CARD_COMMAND} [word/phrase]' to add a flashcard to Anki.")
        print("Type 'quit' to exit.")
        print("-" * 30)
        if not self.anki_available: print("Reminder: AnkiConnect check failed. Card adding will fallback to console.")

        try:
             print("\nAmigo Lingüístico starting..."); initial_response = self.handle_tandem_message("Hola.")
             print("\n🤖 Amigo Lingüístico:"); print("-"*20); print(initial_response); print("-"*20)
        except Exception as e: print(f"Error on initial message: {e}")

        try:
            while True:
                user_input = input("\nYou:\n> ")
                if user_input.lower() == 'quit': break
                user_input_stripped = user_input.strip()
                if not user_input_stripped: continue
                if user_input_stripped.startswith("? "): # Teacher
                    query = user_input_stripped[2:].strip()
                    if query:
                        explanation = self.get_teacher_explanation(query)
                        print("\n👩‍🏫 Teacher:"); print("-"*25); print(explanation); print("-"*25)
                    else: print("Usage: ? [word or phrase]")
                    continue
                elif user_input_stripped.lower().startswith(config.CARD_COMMAND): # Card
                    match = re.match(rf"^{config.CARD_COMMAND}\s+(.*)", user_input, re.IGNORECASE | re.DOTALL)
                    if match:
                        query = match.group(1).strip()
                        if query: self.add_card_to_anki(query)
                        else: print(f"Provide word/phrase after {config.CARD_COMMAND}.")
                    else: print(f"Usage: {config.CARD_COMMAND} [word or phrase]")
                    continue
                else: # Default: Tandem
                    response_text = self.handle_tandem_message(user_input)
                    print("\n🤖 Amigo Lingüístico:"); print("-"*20); print(response_text); print("-"*20)
        except KeyboardInterrupt: print("\nExiting script.")
        finally: print("\n--- Chat Finished ---")


# --- Main execution block ---
if __name__ == "__main__":
    print("Loading configuration from config.py...")
    if config.ANKI_DECK_NAME == "Spanish::Chatbot" or config.ANKI_MODEL_NAME == "Basic":
         print("Reminder: Check ANKI settings in config.py!")

    bot = Chatbot()
    bot.run()