import unittest
from unittest.mock import AsyncMock, MagicMock
import json
from routers.chat import chat_endpoint
from tests.mocks import MockLLMHandler
import schemas

class TestChatAgent(unittest.IsolatedAsyncioTestCase):
    async def test_chat_tool_triggering(self):
        """Test that the chat endpoint correctly triggers a tool based on user message."""
        
        # Mock request data
        request_data = schemas.ChatMessageCreate(
            user_id="00000000-0000-0000-0000-000000000001",
            session_id="test-session",
            content="Generate some cards for me",
            role="user"
        )
        
        # Mock dependencies
        current_user = MagicMock()
        current_user.id = "00000000-0000-0000-0000-000000000001"
        
        llm_handler = MockLLMHandler()
        # Ensure it behaves like our tool-calling mock
        llm_handler.generate_with_tools = AsyncMock(side_effect=llm_handler.generate_with_tools)
        
        db_session = AsyncMock()
        
        # Mock internal CRUD calls
        import routers.chat as chat_module
        chat_module.crud = AsyncMock()
        chat_module.crud.add_chat_message = AsyncMock(side_effect=lambda chat_message, db_session: chat_message)
        
        # Create a mock message object that the endpoint expects
        mock_msg = MagicMock()
        mock_msg.role = "user"
        mock_msg.content = "Generate some cards for me"
        chat_module.crud.get_chat_history = AsyncMock(return_value=[mock_msg])
        
        # Mock the tool itself to avoid DB calls inside tool.execute
        from services.orchestrator.tools import CardGenerator
        original_execute = CardGenerator.execute
        CardGenerator.execute = AsyncMock(return_value={"action": "generated_cards", "count": 5})
        
        try:
            # Execute endpoint
            response = await chat_endpoint(
                request_data=request_data,
                current_user=current_user,
                llm_handler=llm_handler,
                db_session=db_session
            )
            
            # Verify tool was called
            self.assertIn("generated 5 new flashcards", response.content)
            
        finally:
            # Restore original method
            CardGenerator.execute = original_execute

    async def test_card_compressor_triggering(self):
        """Test that the chat agent infers CardCompressor for workload-related messages."""
        request_data = schemas.ChatMessageCreate(
            user_id="00000000-0000-0000-0000-000000000001",
            session_id="test-session",
            content="I am feeling overwhelmed with my reviews",
            role="user"
        )
        
        current_user = MagicMock()
        current_user.id = "00000000-0000-0000-0000-000000000001"
        llm_handler = MockLLMHandler()
        db_session = AsyncMock()
        
        import routers.chat as chat_module
        chat_module.crud = AsyncMock()
        chat_module.crud.add_chat_message = AsyncMock(side_effect=lambda chat_message, db_session: chat_message)
        mock_msg = MagicMock(role="user", content=request_data.content)
        chat_module.crud.get_chat_history = AsyncMock(return_value=[mock_msg])
        
        from services.orchestrator.tools import CardCompressor
        original_execute = CardCompressor.execute
        CardCompressor.execute = AsyncMock(return_value={
            "action": "compressed_cards", 
            "compression_results": {"cards_processed": 50, "suspended": 20}
        })
        
        try:
            response = await chat_endpoint(request_data, current_user, llm_handler, db_session)
            self.assertIn("compressed your workload", response.content)
            self.assertIn("suspended 20", response.content)
        finally:
            CardCompressor.execute = original_execute

    async def test_card_decompressor_triggering(self):
        """Test that the chat agent infers CardDecompressor for reactivation messages."""
        request_data = schemas.ChatMessageCreate(
            user_id="00000000-0000-0000-0000-000000000001",
            session_id="test-session",
            content="Reactivate some of my suspended cards",
            role="user"
        )
        
        current_user = MagicMock()
        current_user.id = "00000000-0000-0000-0000-000000000001"
        llm_handler = MockLLMHandler()
        db_session = AsyncMock()
        
        import routers.chat as chat_module
        chat_module.crud = AsyncMock()
        chat_module.crud.add_chat_message = AsyncMock(side_effect=lambda chat_message, db_session: chat_message)
        mock_msg = MagicMock(role="user", content=request_data.content)
        chat_module.crud.get_chat_history = AsyncMock(return_value=[mock_msg])
        
        from services.orchestrator.tools import CardDecompressor
        original_execute = CardDecompressor.execute
        CardDecompressor.execute = AsyncMock(return_value={"action": "decompressed_cards", "reactivated_count": 10})
        
        try:
            response = await chat_endpoint(request_data, current_user, llm_handler, db_session)
            self.assertIn("reactivated 10", response.content)
        finally:
            CardDecompressor.execute = original_execute

if __name__ == "__main__":
    unittest.main()
