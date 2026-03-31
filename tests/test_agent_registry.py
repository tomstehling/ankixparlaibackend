import unittest
from services.orchestrator.tools import AgentToolRegistry, CardGenerator, CardCompressor, CardDecompressor

class TestAgentRegistry(unittest.TestCase):
    def test_registry_registration(self):
        registry = AgentToolRegistry()
        registry.register(CardGenerator())
        registry.register(CardCompressor())
        registry.register(CardDecompressor())
        
        self.assertIn("CardGenerator", registry._tools)
        self.assertIn("CardCompressor", registry._tools)
        self.assertIn("CardDecompressor", registry._tools)

    def test_get_llm_schemas(self):
        """Verify that the registry correctly generates JSON schemas for LLM tools."""
        registry = AgentToolRegistry()
        registry.register(CardGenerator())
        
        schemas = registry.get_llm_schemas()
        self.assertEqual(len(schemas), 1)
        
        schema = schemas[0]
        self.assertEqual(schema["function"]["name"], "CardGenerator")
        
        # Check specific parameter from schema (e.g., 'target_count')
        params = schema["function"]["parameters"]["properties"]
        self.assertIn("target_count", params)
        self.assertEqual(params["target_count"]["type"], "integer")

if __name__ == "__main__":
    unittest.main()
