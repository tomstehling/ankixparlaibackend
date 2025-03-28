import os
import google.generativeai as genai
import sys
import json
import re
# ---vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv---
# --- ENSURE THIS IMPORT IS AT THE TOP ---
from typing import Optional, List
# ---^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^---

# --- Configuration ---
MODEL_NAME = "gemini-1.5-flash-latest"
FLASHCARD_FILE = "flashcards.json"
TANDEM_PROMPT_TEMPLATE_FILE = "system_prompt_template.txt" # Your existing tandem prompt
# --- New Configuration ---
TEACHER_PROMPT_TEMPLATE_FILE = "teacher_prompt_template.txt" # New teacher prompt
TEACHER_COMMAND = "/teacher" # Command to activate teacher mode
# TEACHER_COMMAND = "/explain" # Alternative command

# --- configure_api() --- (Keep as before)
def configure_api():
    # ... (same code) ...
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key: print("Error: GOOGLE_API_KEY not set."); sys.exit(1)
    try:
        genai.configure(api_key=api_key)
        print("Successfully configured Gemini API.")
    except Exception as e: print(f"Error configuring API: {e}"); sys.exit(1)

# --- load_spanish_sentences_from_json() --- (Keep as before)
def load_spanish_sentences_from_json(filename: str) -> list[str]:
    # ... (same code) ...
    print(f"Attempting to load sentences from {filename}")
    sentences = []
    # ... (rest of loading logic) ...
    return sentences

# --- create_system_prompt() --- (Keep as before, loads specified template)
def create_system_prompt(learned_sentences: Optional[List[str]], template_filename: str) -> str:
    """Loads prompt from template, optionally inserting learned content."""
    print(f"Attempting to load system prompt template from '{template_filename}'...")
    try:
        with open(template_filename, 'r', encoding='utf-8') as f:
            template_content = f.read()
        print("Successfully loaded system prompt template.")

        # The logic here already handles None correctly
        if '{learned_content}' in template_content:
            if not learned_sentences: # Checks if None or empty
                learned_content_str = "(No learned sentences loaded)"
            else:
                learned_content_str = "\n".join(f"- {s}" for s in learned_sentences)
            final_prompt = template_content.format(learned_content=learned_content_str)
        else:
            final_prompt = template_content

        return final_prompt
    # ... (rest of exception handling) ...
    except FileNotFoundError: print(f"Error: Prompt template file '{template_filename}' not found."); sys.exit(1)
    except KeyError as e: print(f"Error: Placeholder {e} missing in template '{template_filename}'."); sys.exit(1)
    except Exception as e: print(f"Error reading template '{template_filename}': {e}"); sys.exit(1)

# ---vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv---
# --- NEW FUNCTION FOR TEACHER EXPLANATIONS    ---
# ---vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv---
def get_teacher_explanation(query: str, model: genai.GenerativeModel) -> str:
    """
    Gets a detailed explanation in English for a Spanish query using the Teacher role.
    Makes a separate, non-chat API call.
    """
    print(f"\n--- Requesting Teacher Explanation for: '{query}' ---")
    try:
        # 1. Load the teacher prompt (doesn't need flashcards)
        teacher_instructions = create_system_prompt(None, TEACHER_PROMPT_TEMPLATE_FILE)

        # 2. Construct the prompt for the single API call
        # We combine the instructions and the specific user query.
        # Using a clear structure helps the model understand the task.
        prompt_for_teacher = f"""
{teacher_instructions}

--- User Query ---
Please explain the following Spanish word/phrase: "{query}"
"""

        # 3. Make a single, stateless generate_content call
        print("Sending request to Teacher AI...")
        response = model.generate_content(prompt_for_teacher) # No history needed here

        # 4. Process the response
        if response.text:
            return response.text
        elif hasattr(response, 'prompt_feedback') and response.prompt_feedback.block_reason:
             return f"Teacher explanation blocked: {response.prompt_feedback.block_reason.name}"
        elif not response.candidates:
             return "Teacher explanation response was empty or blocked for an unknown reason."
        else:
             return "Received an empty explanation from the Teacher AI."

    except Exception as e:
        print(f"An error occurred during Teacher explanation call: {e}")
        return "Sorry, I encountered an error trying to get the teacher explanation."
# ---^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^---
# --- END OF NEW FUNCTION                      ---
# ---^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^---


# --- main() function --- (Modified for role switching)
def main():
    print("--- Spanish Tandem Partner Script ---")
    configure_api()

    print(f"\n--- Loading learned content from {FLASHCARD_FILE} ---")
    learned_sentences = load_spanish_sentences_from_json(FLASHCARD_FILE)
    # Don't exit if loading fails, but tandem prompt will show warning

    # --- Load Tandem prompt ---
    # Pass learned sentences only to the tandem prompt creation
    tandem_system_prompt = create_system_prompt(learned_sentences, TANDEM_PROMPT_TEMPLATE_FILE)

    print(f"\n--- Initializing Model: {MODEL_NAME} ---")
    try:
        # Initialize the main model instance
        # We'll use this instance for both Tandem chat and one-off Teacher calls
        model = genai.GenerativeModel(MODEL_NAME) # System prompt applied to chat session

        # --- Initialize Tandem Chat Session ---
        print("Initializing Tandem chat session...")
        tandem_chat = model.start_chat(
            history=[],
            # Apply the tandem system prompt specifically to this chat session
            # Note: Re-initializing model for chat seems necessary if system_instruction is per-model
            # Let's try initializing the model WITH the tandem prompt first
        )
        # Re-initialize model specifically for chat with system prompt
        # This is a slight adaptation as system_instruction is often tied to the model instance
        tandem_model_instance = genai.GenerativeModel(
             MODEL_NAME,
             system_instruction=tandem_system_prompt
        )
        tandem_chat = tandem_model_instance.start_chat(history=[])

        print("Tandem chat initialized. Starting conversation.")
        print(f"Type your Spanish message, or use '{TEACHER_COMMAND} [word/phrase]' for an English explanation.")
        print("Type 'quit' to exit.")
        print("-" * 30)

        print("\nAmigo Lingüístico is starting the conversation...")
        # Send initial message to the TANDEM chat
        initial_response = tandem_chat.send_message("Hola, Amigo Lingüístico.")

        print("\n🤖 Amigo Lingüístico (Tandem):")
        print("-" * 20)
        if initial_response.text: print(initial_response.text)
        # ... (rest of initial response handling) ...
        else: print("(No initial response text received)")
        print("-" * 20)

    except Exception as e:
        print(f"Error initializing model or starting chat: {e}"); sys.exit(1)

    # --- Main conversation loop ---
    try:
        while True:
            user_input = input("\nYou:\n> ")

            if user_input.lower() == 'quit': break
            if not user_input.strip(): continue # Skip empty input

            # --- Check for Teacher Command ---
            if user_input.lower().startswith(TEACHER_COMMAND):
                # Extract the query part after the command
                match = re.match(rf"^{TEACHER_COMMAND}\s+(.*)", user_input, re.IGNORECASE | re.DOTALL)
                if match:
                    query_to_explain = match.group(1).strip()
                    if query_to_explain:
                        # Call the teacher explanation function (uses the base 'model' instance)
                        explanation = get_teacher_explanation(query_to_explain, model)
                        print("\n👩‍🏫 Teacher Explanation:")
                        print("-" * 25)
                        print(explanation)
                        print("-" * 25)
                    else:
                        print(f"Please provide the word/phrase after {TEACHER_COMMAND}. Example: {TEACHER_COMMAND} como")
                else:
                     print(f"Usage: {TEACHER_COMMAND} [word or phrase to explain]")
                # Continue loop to get next input, don't send command to tandem chat
                continue

            # --- If not a command, send to Tandem Chat ---
            print("\nSending to Amigo Lingüístico (Tandem)...")
            try:
                # Send to the persistent tandem chat session
                response = tandem_chat.send_message(user_input)
                print("\n🤖 Amigo Lingüístico (Tandem):")
                print("-" * 20)
                if response.text: print(response.text)
                # ... (rest of response handling) ...
                elif not response.candidates:
                    feedback = response.prompt_feedback if hasattr(response, 'prompt_feedback') else None
                    if feedback and feedback.block_reason: print(f"Response blocked: {feedback.block_reason.name}")
                    else: print("Response was empty or blocked.")
                else: print("Received an empty response.")
                print("-" * 20)

            except Exception as e:
                 print(f"\nAn error occurred during Tandem API call: {e}")
                 print("Please try again.")

    except KeyboardInterrupt:
        print("\nExiting script.")
    finally:
        print("\n--- Chat Finished ---")

if __name__ == "__main__":
    main()