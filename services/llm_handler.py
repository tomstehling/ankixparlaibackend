import logging
import google.generativeai as genai
from google.generativeai.generative_models import GenerativeModel, ChatSession
from typing import Any 

logger = logging.getLogger(__name__)

class GeminiHandler:
    """Handles interactions with the Google Gemini API."""

    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash-lite"):
        """
        Initializes the Gemini client.

        Args:
            api_key: The Google API key for Gemini.
            model_name: The specific Gemini model to use (e.g., 'gemini-pro', 'gemini-1.5-flash-latest').
        """
        try:
            genai.configure(api_key=api_key)
            self.model_name = model_name
            self.model: GenerativeModel = genai.GenerativeModel(self.model_name)
            logger.info(f"GeminiHandler initialized with model: {self.model_name}")
        except Exception as e:
            logger.exception(f"Failed to configure Google Generative AI: {e}")
            self.model = None

    def get_model(self) -> GenerativeModel:
        """Returns the initialized GenerativeModel instance."""
        if not self.model:
            logger.error("Gemini model was not initialized successfully.")
            raise RuntimeError("Gemini model is not available.")
        return self.model

    async def generate_one_off(self, prompt: str) -> str:
        """Generates content based on a single prompt (non-chat)."""
        if not self.model:
            logger.error("Cannot generate content, Gemini model not initialized.")
            return "(Error: Model not available)"
        try:
            logger.debug(f"Sending one-off generation request to {self.model_name}...")
            response = await self.model.generate_content_async(prompt)

            if not response.candidates:
                 logger.warning(f"No candidates returned from Gemini for prompt: {prompt[:100]}...")
                 reason = getattr(response.prompt_feedback, 'block_reason', 'Unknown')
                 return f"(Response blocked, reason: {reason})"

            content = response.candidates[0].content
            if content and content.parts:
                 return content.parts[0].text
            else:
                 logger.warning(f"Received empty response or unexpected structure from Gemini: {response}")
                 return "(Received empty response from AI)"

        except Exception as e:
            logger.exception(f"Error during Gemini one-off generation: {e}")
            return f"(Error during generation: {e})"

    # Note: The return type Any is okay here, but you could potentially
    # use a more specific type from google.generativeai.types if needed, like GenerateContentResponse
    async def send_message_async(self, chat_session: ChatSession, message: str) -> Any:
        """
        Sends a message within an existing ChatSession asynchronously.
        (This method might become less necessary if router uses chat_session directly)
        """
        if not self.model:
            logger.error("Cannot send message, Gemini model not initialized.")
            raise RuntimeError("Gemini model is not available.")
        try:
            logger.debug(f"Sending message to existing chat session with {self.model_name}...")
            response = await chat_session.send_message_async(message)

            if not response.candidates:
                 logger.warning(f"No candidates returned from Gemini chat message: {message[:100]}...")
                 reason = getattr(response.prompt_feedback, 'block_reason', 'Unknown')
                 raise ValueError(f"Chat response blocked, reason: {reason}")

            return response # Return the full response object (type Any is acceptable)

        except Exception as e:
            logger.exception(f"Error during Gemini chat message sending: {e}")
            raise