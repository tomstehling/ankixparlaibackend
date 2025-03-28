# chatbot.py

import os
from dotenv import load_dotenv
load_dotenv() # Loads environment variables from .env file
import google.generativeai as genai
import sys
import json
import re
import requests # Still needed for potential errors in AnkiConnector init check
from typing import Optional, List, Dict, Any

# --- Import configuration ---
import config

# --- Import custom modules ---
from anki_handler import AnkiConnector # Import the new class

class Chatbot:
    """
    Orchestrates the chatbot application, using handlers for specific tasks.
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
        self.anki_connector: Optional[AnkiConnector] = None # Holder for AnkiConnector instance

        try:
            self._configure_api()
            self._load_flashcards() # Keep using helper from this file for now
            self._load_prompts()    # Keep using helper from this file for now
            self.model = genai.GenerativeModel(config.MODEL_NAME) # Base model
            print("Chatbot base model initialized.")

            # --- Initialize AnkiConnector ---
            self.anki_connector = AnkiConnector(
                anki_connect_url=config.ANKICONNECT_URL,
                deck_name=config.ANKI_DECK_NAME,
                model_name=config.ANKI_MODEL_NAME,
                field_front=config.ANKI_FIELD_FRONT,
                field_back=config.ANKI_FIELD_BACK
            )
            self.anki_available = self.anki_connector.check_connection() # Check on startup
            # --- ---

        except Exception as e:
            print(f"FATAL: Chatbot initialization failed: {e}")
            sys.exit(1)

    # --- _configure_api, _load_flashcards, _load_prompt_from_template, _load_prompts ---
    # --- _initialize_tandem_chat, get_teacher_explanation, handle_tandem_message ---
    # --- (Keep these methods exactly the same as the previous version) ---
    # --- They don't need to change for *this* refactoring step ---

    def _configure_api(self):
        # ... (same code) ...
        print("Configuring API...")
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key: raise ValueError("GOOGLE_API_KEY environment variable not set.")
        genai.configure(api_key=api_key)
        print("Successfully configured Gemini API.")

    def _load_flashcards(self) -> None:
        # ... (same code) ...
        print(f"Loading learned content from '{config.FLASHCARD_FILE}'...")
        sentences = []
        try:
            with open(config.FLASHCARD_FILE, 'r', encoding='utf-8') as f: data = json.load(f)
            # ... (rest of flashcard loading logic) ...
        except Exception as e: print(f"Warning: Error processing '{config.FLASHCARD_FILE}': {e}")
        self.learned_sentences = sentences
        if self.learned_sentences: print(f"Loaded {len(self.learned_sentences)} sentences.")
        else: print("Warning: No sentences loaded.")

    def _load_prompt_from_template(self, template_filename: str, inject_content: bool) -> str:
        """Loads a prompt from a template file, optionally injecting learned sentences."""
        print(f"Loading prompt template from '{template_filename}'...")
        try:
            with open(template_filename, 'r', encoding='utf-8') as f:
                template_content = f.read()

            # --- CORRECTED LOGIC ---
            final_prompt = template_content # Default to original content

            if '{learned_content}' in template_content:
                if inject_content: # Inject real content if requested
                    if not self.learned_sentences:
                        learned_content_str = "(No learned sentences loaded)"
                    else:
                        learned_content_str = "\n".join(f"- {s}" for s in self.learned_sentences)
                    # Format *only if* injecting content
                    final_prompt = template_content.format(learned_content=learned_content_str)
                else: # Placeholder exists, but shouldn't inject real content
                     # Replace placeholder with a generic message
                     final_prompt = template_content.format(learned_content="(Content not applicable)")
            # If '{learned_content}' is not in the template, final_prompt remains as template_content

            print(f"Successfully loaded prompt from '{template_filename}'.")
            return final_prompt
            # --- END OF CORRECTED LOGIC ---

        except FileNotFoundError:
            # Critical error if prompt file is missing
            raise FileNotFoundError(f"Prompt template file '{template_filename}' not found.")
        except KeyError as e:
             # Error if .format() fails due to missing placeholder key (shouldn't happen with this logic)
            raise KeyError(f"Placeholder {e} error in template '{template_filename}'. Check template content.")
        except Exception as e:
            # Catch other potential file reading/processing errors
            raise IOError(f"Error reading/processing template '{template_filename}': {e}")

    def _load_prompts(self):
        # ... (same code) ...
        self.tandem_system_prompt = self._load_prompt_from_template(config.TANDEM_PROMPT_TEMPLATE_FILE, True)
        self.teacher_system_prompt = self._load_prompt_from_template(config.TEACHER_PROMPT_TEMPLATE_FILE, False)
        self.card_creator_prompt = self._load_prompt_from_template(config.CARD_CREATOR_PROMPT_FILE, False)

    def _initialize_tandem_chat(self):
        # ... (same code) ...
        if not self.tandem_system_prompt: return False
        print("\nInitializing Tandem chat...")
        try:
            tandem_model_instance = genai.GenerativeModel(config.MODEL_NAME, system_instruction=self.tandem_system_prompt)
            self.tandem_chat = tandem_model_instance.start_chat(history=[])
            print("Tandem chat initialized.")
            return True
        except Exception as e: print(f"Error initializing Tandem chat: {e}"); self.tandem_chat = None; return False

    def get_teacher_explanation(self, query: str) -> str:
        # ... (same code) ...
        if not self.model or not self.teacher_system_prompt: return "Error: Teacher components missing."
        print(f"\n--- Requesting Teacher Explanation: '{query}' ---")
        try:
            prompt = f"{self.teacher_system_prompt}\n\n--- User Query ---\nPlease explain: \"{query}\""
            print("Sending Teacher request...")
            response = self.model.generate_content(prompt)
            # ... (response handling) ...
            if response.text: return response.text
            else: return "Teacher explanation empty/blocked." # Simplified
        except Exception as e: print(f"Teacher error: {e}"); return "Error getting explanation."

    def handle_tandem_message(self, user_input: str) -> str:
        # ... (same code) ...
        if not self.tandem_chat:
             if not self._initialize_tandem_chat(): return "Error: Tandem chat unavailable."
        print("\nSending Tandem message...")
        try:
            response = self.tandem_chat.send_message(user_input)
            # ... (response handling) ...
            if response.text: return response.text
            else: return "Tandem response empty/blocked." # Simplified
        except Exception as e: print(f"\nTandem error: {e}"); return "Error during conversation."

    # ---vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv---
    # --- MODIFIED: add_card_to_anki method        ---
    # --- Now uses self.anki_connector             ---
    # ---vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv---
    def add_card_to_anki(self, spanish_query: str):
        """
        Generates flashcard data via AI and uses AnkiConnector to add it.
        """
        if not self.model or not self.card_creator_prompt:
            print("Error: Card Creator components not initialized.")
            return
        if not self.anki_connector: # Check if AnkiConnector was initialized
             print("Error: AnkiConnector not available.")
             return

        print(f"\n--- Generating Flashcard Data for: '{spanish_query}' ---")
        card_data_text = "" # For fallback
        try:
            # 1. Get structured data from AI
            prompt_for_creator = f"{self.card_creator_prompt}\n\nInput: {spanish_query}"
            print("Sending request to Card Creator AI...")
            response = self.model.generate_content(prompt_for_creator)

            if not response.text: print("Card Creator AI returned empty."); return
            card_data_text = response.text.strip()
            print(f"AI Card Data: {card_data_text}")

            # 2. Parse the AI response
            parts = [p.strip() for p in card_data_text.split("||")]
            if len(parts) != 4:
                print(f"Error: Cannot parse AI response: {card_data_text}")
                print(f"--- Card Data (Manual Copy) ---\n{card_data_text}\n-------------------------------"); return

            spanish_front, english_back, grammar_info, topic_tag = parts
            tags = [tag.strip().replace(" ", "_") for tag in [grammar_info, topic_tag] if tag.strip()]

            # 3. Use AnkiConnector to add the note
            note_id = self.anki_connector.add_note(
                front=spanish_front,
                back=english_back,
                tags=tags
            )

            # 4. Handle result (success is printed within add_note)
            if note_id is None:
                # Failure or connection error occurred (error printed by AnkiConnector)
                # Provide fallback info
                print("--- Card Data (Manual Copy) ---")
                print(f"Front: {spanish_front}\nBack: {english_back}\nTags: {', '.join(tags)}")
                print("-------------------------------")

        except Exception as e:
            # Catch errors from AI call or parsing before AnkiConnector
            print(f"An error occurred during card creation process: {e}")
            if card_data_text: print(f"--- Raw AI Card Data ---\n{card_data_text}\n------------------------")
    # ---^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^---
    # --- END OF MODIFIED METHOD                   ---
    # ---^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^---

    # --- run() method (No changes needed in this step) ---
    def run(self):
        """Starts and manages the main chat loop."""
        print("\n--- Starting Spanish Tandem Partner ---")
        if not self._initialize_tandem_chat(): print("Failed Tandem init. Exiting."); return

        print(f"Type your Spanish message.")
        print(f"Use '? [word/phrase]' for an English explanation.")
        print(f"Use '{config.CARD_COMMAND} [word/phrase]' to add a flashcard to Anki.")
        print("Type 'quit' to exit.")
        print("-" * 30)
        if not self.anki_available: # Remind user if AnkiConnect check failed
             print("Reminder: AnkiConnect connection failed on startup. Card adding will fall back to console output.")

        # ... (rest of run method is the same as before, including command checks and loops) ...
        try: # Initial greeting
             print("\nAmigo Lingüístico starting..."); initial_response = self.handle_tandem_message("Hola.")
             print("\n🤖 Amigo Lingüístico:"); print("-"*20); print(initial_response); print("-"*20)
        except Exception as e: print(f"Error on initial message: {e}")
        try:
            while True:
                user_input = input("\nYou:\n> ")
                if user_input.lower() == 'quit': break
                user_input_stripped = user_input.strip()
                if not user_input_stripped: continue
                if user_input_stripped.startswith("? "): # Teacher Command
                    query = user_input_stripped[2:].strip()
                    if query:
                        explanation = self.get_teacher_explanation(query)
                        print("\n👩‍🏫 Teacher:"); print("-"*25); print(explanation); print("-"*25)
                    else: print("Usage: ? [word or phrase]")
                    continue
                elif user_input_stripped.lower().startswith(config.CARD_COMMAND): # Card Command
                    match = re.match(rf"^{config.CARD_COMMAND}\s+(.*)", user_input, re.IGNORECASE | re.DOTALL)
                    if match:
                        query = match.group(1).strip()
                        if query: self.add_card_to_anki(query) # Use the method
                        else: print(f"Provide word/phrase after {config.CARD_COMMAND}.")
                    else: print(f"Usage: {config.CARD_COMMAND} [word or phrase]")
                    continue
                else: # Default: Tandem Message
                    response_text = self.handle_tandem_message(user_input)
                    print("\n🤖 Amigo Lingüístico:"); print("-"*20); print(response_text); print("-"*20)
        except KeyboardInterrupt: print("\nExiting script.")
        finally: print("\n--- Chat Finished ---")


# --- Main execution block ---
if __name__ == "__main__":
    print("Loading configuration from config.py...")
    if config.ANKI_DECK_NAME == "Spanish::Chatbot" or config.ANKI_MODEL_NAME == "Basic":
         print("Reminder: Check ANKI_DECK_NAME/MODEL/FIELDS in config.py and update if needed!")

    bot = Chatbot()
    bot.run()