import unittest
import asyncio
import os
from dotenv import load_dotenv
from services.llm_handler import OpenRouterHandler

# Load environment variables with override to ensure we get the correct values
load_dotenv(".env", override=True)


class TestOpenRouterConnectivity(unittest.IsolatedAsyncioTestCase):
    """Test suite to verify OpenRouter API connectivity and basic functionality."""

    async def asyncSetUp(self):
        """Set up test environment with OpenRouter handler."""
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            self.skipTest("OPENROUTER_API_KEY not found in environment. Cannot test connectivity.")

        # Clean up the API key (remove quotes if present)
        api_key = api_key.strip("'").strip('"')

        model_name = os.getenv("OPENROUTER_MODEL_NAME", "openai/gpt-oss-120b:free")

        self.llm_handler = OpenRouterHandler(api_key=api_key, model_name=model_name)
        print(f"\n✓ Initialized OpenRouterHandler with model: {model_name}")

    async def test_basic_connectivity(self):
        """Test basic connectivity to OpenRouter API with a simple prompt."""
        print("\n🔍 Testing basic OpenRouter connectivity...")

        test_prompt = "Say 'Hello, connection successful!' in exactly those words."

        try:
            response = await self.llm_handler.generate_one_off(test_prompt)

            # Verify we got a response
            self.assertIsNotNone(response, "Response from OpenRouter should not be None")
            self.assertIsInstance(response, str, "Response should be a string")
            self.assertTrue(len(response) > 0, "Response should not be empty")

            print(f"✓ Basic connectivity test passed")
            print(f"  Response: {response[:100]}...")

        except Exception as e:
            self.fail(f"Basic connectivity test failed with error: {e}")

    async def test_api_key_validity(self):
        """Test if the API key is valid by checking client initialization."""
        print("\n🔍 Testing API key validity...")

        try:
            # The handler should have been initialized successfully
            self.assertIsNotNone(self.llm_handler, "OpenRouterHandler should be initialized")
            self.assertIsNotNone(self.llm_handler.api_key, "API key should not be None")
            self.assertTrue(len(self.llm_handler.api_key) > 0, "API key should not be empty")

            print(f"✓ API key validity test passed")
            print(f"  Key format: {self.llm_handler.api_key[:8]}...{self.llm_handler.api_key[-4:]}")

        except Exception as e:
            self.fail(f"API key validity test failed with error: {e}")

    async def test_model_availability(self):
        """Test if the specified model is available and responding."""
        print("\n🔍 Testing model availability...")

        try:
            # Make a simple request to verify the model is available
            test_prompt = "Respond with just the number 42."
            response = await self.llm_handler.generate_one_off(test_prompt)

            # Verify the model responded
            self.assertIsNotNone(response, "Model should return a response")
            self.assertTrue(len(response) > 0, "Model response should not be empty")

            print(f"✓ Model availability test passed")
            print(f"  Model: {self.llm_handler.model_name}")
            print(f"  Response: {response[:50]}...")

        except Exception as e:
            self.fail(f"Model availability test failed with error: {e}")

    async def test_response_quality(self):
        """Test if responses are generated with reasonable quality."""
        print("\n🔍 Testing response quality...")

        try:
            # Ask a question that should get a meaningful response
            test_prompt = "What is 2 + 2? Answer with just the number."
            response = await self.llm_handler.generate_one_off(test_prompt)

            # Verify response contains the expected answer
            self.assertIsNotNone(response, "Response should not be None")
            self.assertTrue("4" in response, "Response should contain '4'")

            print(f"✓ Response quality test passed")
            print(f"  Prompt: {test_prompt}")
            print(f"  Response: {response}")

        except Exception as e:
            self.fail(f"Response quality test failed with error: {e}")


if __name__ == "__main__":
    unittest.main()
