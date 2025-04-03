# llm_handler.py
"""
Handles interactions with the Google Gemini LLM API.
Encapsulates model initialization, chat session creation, and API calls.
"""
import os # Added for api key retrieval
import google.generativeai as genai
import logging
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from typing import Optional, List, Dict, Any

# --- Setup Logging ---
# Assuming logging is configured elsewhere (e.g., in server.py)
# If running standalone, you might need basicConfig here.
logger = logging.getLogger(__name__) # Use standard logger

# Define safety settings (optional, adjust as needed)
SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
}

class GeminiHandler:
    """ Handles setup and communication with the Gemini API."""

    def __init__(self, api_key: str, model_name: str): # <-- Added api_key parameter
        """
        Configures the API key and initializes the base GenerativeModel instance.

        Args:
            api_key: The Google Gemini API key.
            model_name: The name of the Gemini model to use (e.g., "gemini-1.5-flash-latest").
        """
        logger.info(f"Initializing GeminiHandler with model: {model_name}")
        try:
            # --- vvv Configure API Key vvv ---
            if not api_key:
                raise ValueError("Gemini API key is required for initialization.")
            genai.configure(api_key=api_key)
            logger.info("Gemini API configured successfully.")
            # --- ^^^ Configure API Key ^^^ ---

            self.model_name = model_name # Store model name if needed later
            self.model = genai.GenerativeModel(
                model_name,
                # safety_settings=SAFETY_SETTINGS # Uncomment to apply safety settings
            )
            logger.info("Base Gemini model initialized successfully.")
        except ValueError as ve:
             logger.error(f"Configuration Error: {ve}")
             raise
        except Exception as e:
            logger.exception(f"FATAL: Failed to initialize base Gemini model: {e}")
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
        logger.info("Attempting to create new Gemini chat session...") # Use logger
        try:
            # If a system prompt is provided, create a model instance specifically for it
            if system_prompt:
                 model_instance = genai.GenerativeModel(
                     self.model_name, # Use stored model name
                     system_instruction=system_prompt,
                     # safety_settings=SAFETY_SETTINGS # Apply safety here too
                 )
                 chat = model_instance.start_chat(history=[])
                 logger.info("Chat session created with system prompt.") # Use logger
            else:
                 # Start chat without system prompt using the base model
                 chat = self.model.start_chat(history=[])
                 logger.info("Chat session created without system prompt.") # Use logger
            return chat
        except Exception as e:
            logger.exception(f"Error creating Gemini chat session: {e}") # Use logger.exception
            return None

    # --- vvv MAKE ASYNC vvv ---
    async def send_chat_message(self, chat_session: genai.ChatSession, user_input: str) -> Optional[str]:
    # --- ^^^ MAKE ASYNC ^^^ ---
        """
        Sends a message asynchronously to an existing chat session and returns the text response.

        Args:
            chat_session: The active ChatSession object.
            user_input: The user's message text.

        Returns:
            The AI's text response, or None if an error occurs or response is blocked/empty.
        """
        if not chat_session:
            logger.error("Error: Attempted to send message to an invalid chat session.") # Use logger
            return None
        try:
            logger.info(f"Sending message async to chat session: '{user_input[:50]}...'") # Use logger

            # --- vvv USE ASYNC METHOD vvv ---
            response = await chat_session.send_message_async(user_input)
            # --- ^^^ USE ASYNC METHOD ^^^ ---

            # Basic response checking (remains the same)
            if response.text:
                return response.text
            elif not response.candidates:
                 feedback = response.prompt_feedback if hasattr(response, 'prompt_feedback') else None
                 block_reason = feedback.block_reason.name if (feedback and feedback.block_reason) else "Unknown"
                 logger.warning(f"Chat response was empty or blocked. Reason: {block_reason}") # Use logger
                 return f"(Response blocked: {block_reason})"
            else:
                 logger.warning("Chat response had candidates but no text content.") # Use logger
                 return None
        except Exception as e:
            logger.exception(f"Error sending message async via Gemini API: {e}") # Use logger.exception
            return None

    # --- vvv MAKE ASYNC vvv ---
    async def generate_one_off(self, prompt: str) -> Optional[str]:
    # --- ^^^ MAKE ASYNC ^^^ ---
        """
        Generates content asynchronously for a single, non-chat prompt.
        """
        try:
            logger.info(f"Sending one-off generation request async (first 80 chars): '{prompt[:80]}...'")

            # --- vvv USE ASYNC METHOD vvv ---
            response = await self.model.generate_content_async(
                prompt,
                # safety_settings=SAFETY_SETTINGS
            )
            # --- ^^^ USE ASYNC METHOD ^^^ ---
            logger.info("Received one-off response object from Gemini async.")

            # Basic response checking (remains the same)
            if hasattr(response, 'text') and response.text:
                logger.info("One-off response has text content.")
                return response.text
            elif not response.candidates:
                 feedback = response.prompt_feedback if hasattr(response, 'prompt_feedback') else None
                 block_reason = feedback.block_reason.name if (feedback and feedback.block_reason) else "Unknown"
                 logger.warning(f"One-off generation BLOCKED async. Reason: {block_reason}")
                 return f"(Response blocked: {block_reason})"
            else:
                 logger.warning("One-off async response has NO text content but was not blocked.")
                 logger.warning(f"Response details (if any): candidates={response.candidates}, prompt_feedback={response.prompt_feedback}")
                 return None
        except Exception as e:
            logger.exception(f"Exception during one-off async generation: {e}")
            return None