import unittest
import asyncio
import os
from dotenv import load_dotenv
from services.llm_handler import OpenRouterHandler
from services.orchestrator.tools import AgentToolRegistry, CardGenerator, CardCompressor, CardDecompressor

# Load environment variables
load_dotenv("ankixparlaibackend/.env")

class TestRealLLMInference(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        api_key = os.getenv("OPENROUTER_API_KEY")
        if api_key:
            api_key = api_key.strip("'").strip('"')
            # print(f"DEBUG: Using API key starting with: {api_key[:10]}...")
        
        # Use the model requested by the user
        model_name = "openai/gpt-oss-20b:free"
        
        if not api_key:
            self.skipTest("OPENROUTER_API_KEY not found in environment.")
            
        self.llm_handler = OpenRouterHandler(api_key=api_key, model_name=model_name)
        
        # Initialize Registry
        self.registry = AgentToolRegistry()
        self.registry.register(CardGenerator())
        self.registry.register(CardCompressor())
        self.registry.register(CardDecompressor())
        self.tools = self.registry.get_llm_schemas()

    async def test_infer_card_generator(self):
        """Test if the real LLM infers CardGenerator for a content creation request."""
        messages = [
            {"role": "system", "content": "You are a Spanish learning assistant. You have access to tools to help the user."},
            {"role": "user", "content": "I'd like to learn some new Spanish words about traveling."}
        ]
        
        response = await self.llm_handler.generate_with_tools(messages, self.tools)
        
        # Verify tool call exists
        self.assertTrue(hasattr(response.choices[0].message, "tool_calls") and response.choices[0].message.tool_calls, 
                        f"Expected a tool call but got: {response.choices[0].message.content}")
        
        tool_call = response.choices[0].message.tool_calls[0]
        self.assertEqual(tool_call.function.name, "CardGenerator")

    async def test_infer_card_compressor(self):
        """Test if the real LLM infers CardCompressor for workload stress messages."""
        messages = [
            {"role": "system", "content": "You are a Spanish learning assistant. You have access to tools to help the user."},
            {"role": "user", "content": "I have 500 cards due today and I'm totally overwhelmed. Help me manage this workload."}
        ]
        
        response = await self.llm_handler.generate_with_tools(messages, self.tools)
        
        # Verify tool call exists
        self.assertTrue(hasattr(response.choices[0].message, "tool_calls") and response.choices[0].message.tool_calls, 
                        f"Expected a tool call but got: {response.choices[0].message.content}")
        
        tool_call = response.choices[0].message.tool_calls[0]
        self.assertEqual(tool_call.function.name, "CardCompressor")

    async def test_infer_card_decompressor(self):
        """Test if the real LLM infers CardDecompressor for reactivation requests."""
        messages = [
            {"role": "system", "content": "You are a Spanish learning assistant. You have access to tools to help the user."},
            {"role": "user", "content": "I feel like I'm ready for more. Can you bring back some of those cards I suspended earlier?"}
        ]
        
        response = await self.llm_handler.generate_with_tools(messages, self.tools)
        
        # Verify tool call exists
        self.assertTrue(hasattr(response.choices[0].message, "tool_calls") and response.choices[0].message.tool_calls, 
                        f"Expected a tool call but got: {response.choices[0].message.content}")
        
        tool_call = response.choices[0].message.tool_calls[0]
        self.assertEqual(tool_call.function.name, "CardDecompressor")

if __name__ == "__main__":
    unittest.main()
