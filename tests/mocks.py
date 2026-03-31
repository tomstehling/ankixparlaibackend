import json
from typing import List, Dict, Any

class MockLLMHandler:
    def __init__(self):
        self.responses = {}
        self.call_history = []

    async def generate_one_off(self, prompt: str) -> str:
        self.call_history.append(prompt)
        # Check for specific patterns in prompt
        if "propose_sentence" in prompt or "proposed_spanish" in prompt:
            return json.dumps({"proposed_spanish": "Hola", "proposed_english": "Hello"})
        return "Mock Response"

    async def generate_response(self, prompt: str) -> str:
        # For orchestrator tools
        if "CardGenerator" in prompt or "Generate 5 new Spanish flashcards" in prompt:
            return json.dumps({
                "cards": [
                    {"front": f"Mock {i}", "back": f"Mock {i} Translation"} 
                    for i in range(5)
                ]
            })
        return "Mock Response"

    async def generate_with_tools(self, messages: List[Dict[str, str]], tools: List[Dict[str, Any]]):
        # This is for the chat endpoint
        # Simple implementation for testing
        class MockChoice:
            def __init__(self, message):
                self.message = message
        
        class MockMessage:
            def __init__(self, content, tool_calls=None):
                self.content = content
                self.tool_calls = tool_calls

        # Trigger tool calls based on keywords
        user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "").lower()
        
        tool_name = None
        tool_args = {}
        
        if "generate" in user_msg:
            tool_name = "CardGenerator"
            tool_args = {"target_count": 5}
        elif "compress" in user_msg or "overwhelmed" in user_msg:
            tool_name = "CardCompressor"
            tool_args = {"max_due_cards": 30}
        elif "decompress" in user_msg or "reactivate" in user_msg:
            tool_name = "CardDecompressor"
            tool_args = {"reactivate_count": 10}

        if tool_name:
             class MockToolCall:
                def __init__(self, name, args):
                    self.function = type("Function", (), {
                        "name": name,
                        "arguments": json.dumps(args)
                    })
             return type("Response", (), {"choices": [MockChoice(MockMessage(None, [MockToolCall(tool_name, tool_args)]))]})
        
        return type("Response", (), {"choices": [MockChoice(MockMessage("Hello from Mock AI"))]})
