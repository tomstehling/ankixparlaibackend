# chatbot.py

import os
import sys
import json
import re
import requests
from typing import Optional, List, Dict, Any

# --- Import configuration ---
import config

# --- Import custom modules ---
from anki_handler import AnkiConnector
import utils
from llm_handler import GeminiHandler # Import the new handler

class Chatbot:
    """
    Orchestrates the chatbot application, using handlers for specific tasks.
    """

    def __init__(self):
        """Initializes the chatbot and its handlers."""
        print("Initializing Chatbot...")
        # Handlers
        self.llm_handler: Optional[GeminiHandler] = None # Use specific handler type
        self.anki_connector: Optional[AnkiConnector] = None
        # State / Data
        self.tandem_chat: Optional[genai.ChatSession] = None # Still need to store the session object
        self.learned_sentences: List[str] = []
        self.tandem_system_prompt: Optional[str] = None
        self.teacher_system_prompt: Optional[str] = None
        self.card_creator_prompt: Optional[str] = None
        self.anki_available: bool = False

        try:
            self._configure_api_credentials() # Separate credentials from handler init
            # --- Initialize LLM Handler ---
            self.llm_handler = GeminiHandler(config.MODEL_NAME)
            # --- ---
            self.learned_sentences = utils.load_flashcards(config.FLASHCARD_FILE)
            self._load_prompts()
            self.anki_connector = AnkiConnector(
                anki_connect_url=config.ANKICONNECT_URL,
                deck_name=config.ANKI_DECK_NAME,
                model_name=config.ANKI_MODEL_NAME,
                field_front=config.ANKI_FIELD_FRONT,
                field_back=config.ANKI_FIELD_BACK
            )
            self.anki_available = self.anki_connector.check_connection()
            print("Chatbot initialization complete.")

        except Exception as e:
            # Catch errors from handler initializations or file loading
            print(f"FATAL: Chatbot initialization failed: {e}")
            sys.exit(1)

    def _configure_api_credentials(self):
        """Configures the Generative AI client credentials."""
        # This part still needs the genai library initially for configure()
        import google.generativeai as genai
        print("Configuring API credentials...")
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key: raise ValueError("GOOGLE_API_KEY environment variable not set.")
        try:
            genai.configure(api_key=api_key)
            print("Successfully configured Gemini API credentials.")
        except Exception as e:
            print(f"FATAL: Error configuring Gemini API credentials: {e}")
            raise # Re-raise to stop initialization

    def _load_prompts(self):
        """Loads system prompts for all roles using the utility function."""
        # (This method remains unchanged - uses utils)
        self.tandem_system_prompt = utils.load_prompt_from_template(config.TANDEM_PROMPT_TEMPLATE_FILE, self.learned_sentences)
        self.teacher_system_prompt = utils.load_prompt_from_template(config.TEACHER_PROMPT_TEMPLATE_FILE, None)
        self.card_creator_prompt = utils.load_prompt_from_template(config.CARD_CREATOR_PROMPT_FILE, None)

    def _initialize_tandem_chat(self):
        """Initializes the Tandem chat session using the LLM Handler."""
        if not self.llm_handler: print("Error: LLM Handler not initialized."); return False
        if not self.tandem_system_prompt: print("Error: Tandem prompt not loaded."); return False

        print("\nInitializing Tandem chat session via LLM Handler...")
        # Delegate chat creation to the handler
        self.tandem_chat = self.llm_handler.create_chat_session(self.tandem_system_prompt)

        if self.tandem_chat:
            print("Tandem chat initialized successfully.")
            return True
        else:
            print("Failed to initialize Tandem chat session.")
            return False

    def get_teacher_explanation(self, query: str) -> str:
        """Handles the Teacher role request using the LLM Handler."""
        if not self.llm_handler: return "Error: LLM Handler unavailable."
        if not self.teacher_system_prompt: return "Error: Teacher prompt unavailable."

        print(f"\n--- Requesting Teacher Explanation: '{query}' ---")
        # Construct the full prompt
        prompt = f"{self.teacher_system_prompt}\n\n--- User Query ---\nPlease explain: \"{query}\""
        print("Delegating Teacher request to LLM Handler...")
        # Delegate the one-off generation call
        response_text = self.llm_handler.generate_one_off(prompt)

        return response_text if response_text is not None else "Error or no explanation received."

    def handle_tandem_message(self, user_input: str) -> str:
        """Handles sending a message to the Tandem role via the LLM Handler."""
        if not self.llm_handler: return "Error: LLM Handler unavailable."
        if not self.tandem_chat:
             if not self._initialize_tandem_chat(): return "Error: Tandem chat unavailable."

        print("\nDelegating Tandem message to LLM Handler...")
        # Delegate sending the message to the handler
        response_text = self.llm_handler.send_chat_message(self.tandem_chat, user_input)

        return response_text if response_text is not None else "Error or no response received."

    def add_card_to_anki(self, spanish_query: str):
        """Generates flashcard data via LLM Handler and uses AnkiConnector."""
        if not self.llm_handler: print("Error: LLM Handler unavailable."); return
        if not self.card_creator_prompt: print("Error: Card Creator prompt unavailable."); return
        if not self.anki_connector: print("Error: AnkiConnector unavailable."); return

        print(f"\n--- Generating Flashcard Data for: '{spanish_query}' ---")
        card_data_text = ""
        try:
            # 1. Get structured data from AI via LLM Handler
            prompt_for_creator = f"{self.card_creator_prompt}\n\nInput: {spanish_query}"
            print("Delegating Card Creator request to LLM Handler...")
            card_data_response = self.llm_handler.generate_one_off(prompt_for_creator)

            if not card_data_response: print("Card Creator AI returned empty/error."); return
            card_data_text = card_data_response.strip()
            print(f"AI Card Data: {card_data_text}")

            # --- Rest of the logic remains the same (parsing, using AnkiConnector) ---
            parts = [p.strip() for p in card_data_text.split("||")]
            if len(parts) != 4:
                print(f"Error: Cannot parse AI response: {card_data_text}"); print(f"---\n{card_data_text}\n---"); return

            spanish_front, english_back, grammar_info, topic_tag = parts
            tags = [tag.strip().replace(" ", "_") for tag in [grammar_info, topic_tag] if tag.strip()]

            note_id = self.anki_connector.add_note(front=spanish_front, back=english_back, tags=tags)

            if note_id is None: # Handle failure (printed by AnkiConnector)
                print("--- Card Data (Manual Copy) ---")
                print(f"Front: {spanish_front}\nBack: {english_back}\nTags: {', '.join(tags)}")
                print("-------------------------------")

        except Exception as e:
            print(f"Error during card creation process: {e}")
            if card_data_text: print(f"--- Raw AI Card Data ---\n{card_data_text}\n------------------------")

    def run(self):
        """Starts and manages the main chat loop."""
        # (This method remains unchanged - it calls the other methods)
        print("\n--- Starting Spanish Tandem Partner ---")
        if not self._initialize_tandem_chat(): print("Failed Tandem init. Exiting."); return

        print(f"Type your Spanish message.")
        print(f"Use '? [word/phrase]' for an English explanation.")
        print(f"Use '{config.CARD_COMMAND} [word/phrase]' to add a flashcard to Anki.")
        print("Type 'quit' to exit.")
        print("-" * 30)
        if not self.anki_available: print("Reminder: AnkiConnect unavailable. Card adding will fallback.")

        try: # Initial greeting
             print("\nAmigo Lingüístico starting..."); initial_response = self.handle_tandem_message("Hola.")
             print("\n🤖 Amigo Lingüístico:"); print("-"*20); print(initial_response); print("-"*20)
        except Exception as e: print(f"Error on initial message: {e}")

        try: # Main loop
            while True:
                # ... (Input handling and command detection logic is identical) ...
                user_input = input("\nYou:\n> ")
                if user_input.lower() == 'quit': break
                user_input_stripped = user_input.strip()
                if not user_input_stripped: continue
                if user_input_stripped.startswith("? "): # Teacher
                    query = user_input_stripped[2:].strip()
                    if query: explanation = self.get_teacher_explanation(query) # Uses handler now
                    else: print("Usage: ? [word or phrase]"); continue
                    print("\n👩‍🏫 Teacher:"); print("-"*25); print(explanation); print("-"*25)
                    continue
                elif user_input_stripped.lower().startswith(config.CARD_COMMAND): # Card
                    match = re.match(rf"^{config.CARD_COMMAND}\s+(.*)", user_input, re.IGNORECASE | re.DOTALL)
                    if match:
                        query = match.group(1).strip()
                        if query: self.add_card_to_anki(query) # Uses handler now
                        else: print(f"Provide word/phrase after {config.CARD_COMMAND}.")
                    else: print(f"Usage: {config.CARD_COMMAND} [word or phrase]")
                    continue
                else: # Default: Tandem
                    response_text = self.handle_tandem_message(user_input) # Uses handler now
                    print("\n🤖 Amigo Lingüístico:"); print("-"*20); print(response_text); print("-"*20)
        except KeyboardInterrupt: print("\nExiting script.")
        finally: print("\n--- Chat Finished ---")


# --- Main execution block ---
if __name__ == "__main__":
    # Need to load dotenv here before anything else tries to use env vars
    from dotenv import load_dotenv
    load_dotenv()

    print("Loading configuration from config.py...")
    if config.ANKI_DECK_NAME == "Spanish::Chatbot" or config.ANKI_MODEL_NAME == "Basic":
         print("Reminder: Check ANKI settings in config.py!")

    bot = Chatbot()
    bot.run()