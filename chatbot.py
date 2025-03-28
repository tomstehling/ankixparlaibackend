import os
import google.generativeai as genai
import sys
import json
import re
from typing import Optional, List, Dict, Any

# --- Configuration ---
MODEL_NAME = "gemini-1.5-flash-latest"
FLASHCARD_FILE = "flashcards.json"
TANDEM_PROMPT_TEMPLATE_FILE = "system_prompt_template.txt"
TEACHER_PROMPT_TEMPLATE_FILE = "teacher_prompt_template.txt"
# --- No TEACHER_COMMAND constant needed now, we'll use '?' directly ---

class Chatbot:
    """
    Manages the Spanish tandem and teacher AI chatbot application.
    Handles configuration, API interaction, role switching, and the main chat loop.
    """

    # --- __init__, _configure_api, _load_flashcards, _load_prompt_from_template ---
    # --- _load_prompts, _initialize_tandem_chat, get_teacher_explanation        ---
    # --- handle_tandem_message                                                  ---
    # --- (Keep all these methods exactly the same as the previous OOP version)  ---

    def __init__(self):
        """Initializes the chatbot, loads config, prompts, and sets up the API."""
        print("Initializing Chatbot...")
        self.model: Optional[genai.GenerativeModel] = None
        self.tandem_chat: Optional[genai.ChatSession] = None
        self.learned_sentences: List[str] = []
        self.tandem_system_prompt: Optional[str] = None
        self.teacher_system_prompt: Optional[str] = None
        try:
            self._configure_api()
            self._load_flashcards()
            self._load_prompts()
            self.model = genai.GenerativeModel(MODEL_NAME)
            print("Chatbot base model initialized.")
        except Exception as e: print(f"FATAL: Chatbot initialization failed: {e}"); sys.exit(1)

    def _configure_api(self):
        """Configures the Generative AI client."""
        print("Configuring API...")
        # ... (same code) ...
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key: raise ValueError("GOOGLE_API_KEY environment variable not set.")
        genai.configure(api_key=api_key)
        print("Successfully configured Gemini API.")


    def _load_flashcards(self) -> None:
        """Loads Spanish sentences from the flashcard JSON file."""
        print(f"Loading learned content from '{FLASHCARD_FILE}'...")
        # ... (same code) ...
        sentences = []
        try:
            with open(FLASHCARD_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    for card in data:
                         if isinstance(card, dict):
                             sentence = card.get("front")
                             if sentence and isinstance(sentence, str) and sentence.strip(): sentences.append(sentence.strip())
                else: print(f"Warning: Expected '{FLASHCARD_FILE}' to be a JSON list.")
        except FileNotFoundError: print(f"Warning: Flashcard file '{FLASHCARD_FILE}' not found.")
        except json.JSONDecodeError as e: print(f"Warning: Could not decode JSON from '{FLASHCARD_FILE}'. Details: {e}")
        except Exception as e: print(f"Warning: Error processing '{FLASHCARD_FILE}': {e}")
        self.learned_sentences = sentences
        if self.learned_sentences: print(f"Successfully loaded {len(self.learned_sentences)} sentences.")
        else: print("Warning: No valid sentences loaded from flashcards.")

    def _load_prompt_from_template(self, template_filename: str, inject_content: bool) -> str:
        """Loads a prompt from a template file, optionally injecting learned sentences."""
        print(f"Loading prompt template from '{template_filename}'...")
        # ... (same code) ...
        try:
            with open(template_filename, 'r', encoding='utf-8') as f: template_content = f.read()
            if inject_content and '{learned_content}' in template_content:
                learned_content_str = "\n".join(f"- {s}" for s in self.learned_sentences) if self.learned_sentences else "(No learned sentences loaded)"
                final_prompt = template_content.format(learned_content=learned_content_str)
            elif '{learned_content}' in template_content and not inject_content:
                 final_prompt = template_content.format(learned_content="(Content not applicable for this role)")
            else: final_prompt = template_content
            print(f"Successfully loaded prompt from '{template_filename}'.")
            return final_prompt
        except FileNotFoundError: raise FileNotFoundError(f"Prompt template file '{template_filename}' not found.")
        except KeyError as e: raise KeyError(f"Placeholder {e} error in template '{template_filename}'.")
        except Exception as e: raise IOError(f"Error reading/processing template '{template_filename}': {e}")


    def _load_prompts(self):
        """Loads system prompts for both Tandem and Teacher roles."""
        # ... (same code) ...
        self.tandem_system_prompt = self._load_prompt_from_template(TANDEM_PROMPT_TEMPLATE_FILE, inject_content=True)
        self.teacher_system_prompt = self._load_prompt_from_template(TEACHER_PROMPT_TEMPLATE_FILE, inject_content=False)

    def _initialize_tandem_chat(self):
        """Initializes or re-initializes the Tandem chat session."""
        if not self.tandem_system_prompt: print("Error: Tandem system prompt not loaded."); return False
        print("\nInitializing Tandem chat session...")
        # ... (same code) ...
        try:
            tandem_model_instance = genai.GenerativeModel(MODEL_NAME, system_instruction=self.tandem_system_prompt)
            self.tandem_chat = tandem_model_instance.start_chat(history=[])
            print("Tandem chat initialized.")
            return True
        except Exception as e: print(f"Error initializing Tandem chat model: {e}"); self.tandem_chat = None; return False

    def get_teacher_explanation(self, query: str) -> str:
        """Handles the Teacher role request using a non-chat API call."""
        if not self.model or not self.teacher_system_prompt: return "Error: Teacher role components not initialized."
        print(f"\n--- Requesting Teacher Explanation for: '{query}' ---")
        # ... (same code) ...
        try:
            prompt_for_teacher = f"{self.teacher_system_prompt}\n\n--- User Query ---\nPlease explain: \"{query}\""
            print("Sending request to Teacher AI...")
            response = self.model.generate_content(prompt_for_teacher)
            if response.text: return response.text
            elif hasattr(response, 'prompt_feedback') and response.prompt_feedback.block_reason: return f"Teacher explanation blocked: {response.prompt_feedback.block_reason.name}"
            else: return "Teacher explanation response was empty or blocked."
        except Exception as e: print(f"An error occurred during Teacher explanation call: {e}"); return "Error getting teacher explanation."


    def handle_tandem_message(self, user_input: str) -> str:
        """Handles sending a message to the Tandem role's chat session."""
        if not self.tandem_chat:
             if not self._initialize_tandem_chat(): return "Error: Tandem chat is not available."
        print("\nSending to Amigo Lingüístico (Tandem)...")
        # ... (same code) ...
        try:
            response = self.tandem_chat.send_message(user_input)
            if response.text: return response.text
            elif not response.candidates: # Check if blocked
                 feedback = response.prompt_feedback if hasattr(response, 'prompt_feedback') else None
                 if feedback and feedback.block_reason: return f"Response blocked: {feedback.block_reason.name}"
                 else: return "Response was empty or blocked."
            else: return "Received an empty response."
        except Exception as e: print(f"\nError during Tandem API call: {e}"); return "Error during conversation."


    # ---vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv---
    # --- MODIFIED run() method          ---
    # ---vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv---
    def run(self):
        """Starts and manages the main chat loop."""
        print("\n--- Starting Spanish Tandem Partner ---")
        if not self._initialize_tandem_chat():
            print("Failed to initialize Tandem chat. Exiting.")
            return

        # --- Updated user instruction ---
        print(f"Type your Spanish message, or start with '? ' (question mark + space) followed by a word/phrase for an English explanation.")
        print("Type 'quit' to exit.")
        print("-" * 30)

        # Send initial greeting
        try:
            print("\nAmigo Lingüístico is starting the conversation...")
            initial_response_text = self.handle_tandem_message("Hola, Amigo Lingüístico.")
            print("\n🤖 Amigo Lingüístico (Tandem):")
            print("-" * 20)
            print(initial_response_text if initial_response_text else "(No initial response)")
            print("-" * 20)
        except Exception as e: print(f"Error sending initial message: {e}")

        # Main Loop
        try:
            while True:
                user_input = input("\nYou:\n> ")

                if user_input.lower() == 'quit': break
                # Strip leading/trailing whitespace for checks
                user_input_stripped = user_input.strip()
                if not user_input_stripped: continue

                # --- MODIFIED Command Handling ---
                # Check if the input starts with '?' followed by a space
                if user_input_stripped.startswith("? "):
                    # Extract the query part after '? '
                    # No regex needed if we just take the rest of the string
                    query_to_explain = user_input_stripped[2:].strip() # Get substring after '? ' and strip again

                    if query_to_explain:
                        explanation = self.get_teacher_explanation(query_to_explain)
                        print("\n👩‍🏫 Teacher Explanation:")
                        print("-" * 25)
                        print(explanation)
                        print("-" * 25)
                    else:
                        # --- Updated usage message ---
                        print("Please provide the word/phrase after '? '. Example: ? como estas")
                    continue # Ask for next input

                # --- Default: Send to Tandem Role ---
                # Use the original user_input, not the stripped one, to preserve potential internal spacing
                response_text = self.handle_tandem_message(user_input)
                print("\n🤖 Amigo Lingüístico (Tandem):")
                print("-" * 20)
                print(response_text)
                print("-" * 20)

        except KeyboardInterrupt:
            print("\nExiting script.")
        finally:
            print("\n--- Chat Finished ---")
    # ---^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^---
    # --- END OF MODIFIED run() method     ---
    # ---^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^---

# --- Main execution block ---
if __name__ == "__main__":
    bot = Chatbot()
    bot.run()