import logging
import httpx
import openai
from fastapi import HTTPException
from typing import Any, List, Optional, Dict

logger = logging.getLogger(__name__)


class OpenRouterHandler:
    """Handles interactions with the OpenRouter API using the openai SDK."""

    def __init__(self, api_key: str, model_name: str):
        """
        Initializes the OpenRouter client using the openai SDK.

        Args:
            api_key: The OpenRouter API key.
            model_name: The specific model to use (e.g., 'openai/gpt-3.5-turbo').
        """
        self.api_key = api_key
        self.model_name = model_name
        
        # Log masked key for debugging
        masked_key = f"{self.api_key[:8]}...{self.api_key[-4:]}" if self.api_key else "None"
        logger.info(f"Initializing OpenRouterHandler. Model: {self.model_name}, Key: {masked_key}")

        self.client = openai.AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=self.api_key,
            default_headers={
                "HTTP-Referer": "https://ankixparlai.com", # Replace with actual site URL
                "X-Title": "AnkiXParlaI",
            },
        )
        logger.info(f"OpenRouterHandler initialized with model: {self.model_name}")

    async def generate_one_off(self, prompt: str) -> str:
        """Generates content based on a single prompt."""
        try:
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": prompt}],
            )
            logger.debug(f"OpenRouter Raw Response: {response}")
            if response.choices:
                return response.choices[0].message.content
            else:
                return "(Received empty response from AI)"
        except openai.APIError as e:
            logger.exception(f"OpenRouter API error: {e}")
            logger.error(f"OpenRouter Error Details - Status: {getattr(e, 'status_code', 500)}, Message: {e.message}, Code: {getattr(e, 'code', 'N/A')}, Param: {getattr(e, 'param', 'N/A')}")
            raise HTTPException(
                status_code=getattr(e, 'status_code', 500),
                detail=f"OpenRouter API error: {e.message}",
            )
        except Exception as e:
            logger.exception(f"Error during OpenRouter one-off generation: {e}")
            raise HTTPException(
                status_code=500, detail=f"OpenRouter generation failed: {e}"
            )

    async def generate_with_tools(self, messages: List[Dict[str, str]], tools: List[Dict[str, Any]]) -> Any:
        """
        Generates content with tool calling support.
        
        Args:
            messages: List of message objects.
            tools: List of tool definitions.
            
        Returns:
            The completion response object.
        """
        try:
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                tools=tools,
            )
            return response
        except Exception as e:
            logger.exception(f"Error during OpenRouter tool-calling generation: {e}")
            raise HTTPException(
                status_code=500, detail=f"OpenRouter tool-calling failed: {e}"
            )
