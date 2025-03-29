# llm_handler.py
"""
Handles interactions with the Google Gemini LLM API.
Encapsulates model initialization, chat session creation, and API calls.
"""

import google.generativeai as genai
import logging # Use logging instead of print for server messages
from google.generativeai.types import HarmCategory, HarmBlockThreshold # For potential safety settings
from typing import Optional, List, Dict, Any

# --- Setup Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Define safety settings (optional, adjust as needed)
# You might want to block more harmful content, or less if it's overly sensitive
SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
}

class GeminiHandler:
    """ Handles setup and communication with the Gemini API."""

    def __init__(self, model_name: str):
        """
        Initializes the base GenerativeModel instance.

        Args:
            model_name: The name of the Gemini model to use (e.g., "gemini-1.5-flash-latest").
        """
        print(f"Initializing GeminiHandler with model: {model_name}")
        try:
            self.model = genai.GenerativeModel(
                model_name,
                # safety_settings=SAFETY_SETTINGS # Uncomment to apply safety settings
                )
            print("Base Gemini model initialized successfully.")
        except Exception as e:
            print(f"FATAL: Failed to initialize base Gemini model: {e}")
            # Re-raise to prevent Chatbot from continuing without a model
            raise

    def create_chat_session(self, system_prompt: Optional[str]) -> Optional[genai.ChatSession]:
        """
        Creates a new chat session, optionally with a system prompt.

        Args:
            system_prompt: The system instruction for the chat session.

        Returns:
            A ChatSession object, or None if creation fails.
        """
        print("Attempting to create new Gemini chat session...")
        try:
            # If a system prompt is provided, create a model instance specifically for it
            # This seems to be the more reliable way to apply system instructions per session
            if system_prompt:
                 model_instance = genai.GenerativeModel(
                     self.model.model_name, # Use same model name as base
                     system_instruction=system_prompt,
                     # safety_settings=SAFETY_SETTINGS # Apply safety here too
                 )
                 chat = model_instance.start_chat(history=[])
                 print("Chat session created with system prompt.")
            else:
                 # Start chat without system prompt using the base model
                 chat = self.model.start_chat(history=[])
                 print("Chat session created without system prompt.")
            return chat
        except Exception as e:
            print(f"Error creating Gemini chat session: {e}")
            return None

    def send_chat_message(self, chat_session: genai.ChatSession, user_input: str) -> Optional[str]:
        """
        Sends a message to an existing chat session and returns the text response.

        Args:
            chat_session: The active ChatSession object.
            user_input: The user's message text.

        Returns:
            The AI's text response, or None if an error occurs or response is blocked/empty.
        """
        if not chat_session:
            print("Error: Attempted to send message to an invalid chat session.")
            return None
        try:
            print(f"Sending message to chat session: '{user_input[:50]}...'") # Log snippet
            response = chat_session.send_message(user_input)

            # Basic response checking
            if response.text:
                return response.text
            elif not response.candidates: # Check if blocked
                 feedback = response.prompt_feedback if hasattr(response, 'prompt_feedback') else None
                 block_reason = feedback.block_reason.name if (feedback and feedback.block_reason) else "Unknown"
                 print(f"Warning: Chat response was empty or blocked. Reason: {block_reason}")
                 return f"(Response blocked: {block_reason})" # Return indication of block
            else:
                 print("Warning: Chat response had candidates but no text content.")
                 return None # Indicate empty response
        except Exception as e:
            print(f"Error sending message via Gemini API: {e}")
            return None # Indicate error

    # Inside llm_handler.py -> GeminiHandler

    def generate_one_off(self, prompt: str) -> Optional[str]:
        """
        Generates content for a single, non-chat prompt (e.g., Teacher, Card Creator).
        """
        try:
            # --- vvv ENSURE THESE LOGS EXIST vvv ---
            logger.info(f"Sending one-off generation request (first 80 chars): '{prompt[:80]}...'")
            response = self.model.generate_content(
                prompt,
                # safety_settings=SAFETY_SETTINGS
                )
            logger.info("Received one-off response object from Gemini.")
            # --- ^^^ ENSURE THESE LOGS EXIST ^^^ ---

            # Basic response checking (similar to chat)
            if hasattr(response, 'text') and response.text: # Check attribute exists first
                logger.info("One-off response has text content.")
                return response.text
            elif not response.candidates: # Check if blocked
                 feedback = response.prompt_feedback if hasattr(response, 'prompt_feedback') else None
                 block_reason = feedback.block_reason.name if (feedback and feedback.block_reason) else "Unknown"
                 logger.warning(f"One-off generation BLOCKED. Reason: {block_reason}")
                 return f"(Response blocked: {block_reason})"
            else:
                 logger.warning("One-off response has NO text content but was not blocked.")
                 logger.warning(f"Response details (if any): candidates={response.candidates}, prompt_feedback={response.prompt_feedback}")
                 return None
        except Exception as e:
            # --- vvv ENSURE THIS LOG EXISTS vvv ---
            logger.exception(f"Exception during one-off generation: {e}")
            # --- ^^^ ENSURE THIS LOG EXISTS ^^^ ---
            return None