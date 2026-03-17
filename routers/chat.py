import logging
import uuid
import json
from typing import List, Optional, Dict, Any
import pprint


from fastapi import APIRouter, HTTPException, Depends
import database.crud as crud
import database.models as models
from core.config import settings

# Import the corrected utility function
from utils import load_prompt_from_template
from services.llm_handler import OpenRouterHandler
import schemas

# Import dependencies
from dependencies import get_current_active_user, get_llm, get_prompt
from sqlalchemy.ext.asyncio import AsyncSession
from database.session import get_db_session
from services.orchestrator.tools import AgentToolRegistry, CardGenerator, CardCompressor, CardDecompressor


logger = logging.getLogger(__name__)
router = APIRouter()

HISTORY_LOOKBACK = 10


@router.get("/chat-history", response_model=list[schemas.ChatMessage])
async def get_chat_history(
    db_session: AsyncSession = Depends(get_db_session),
    current_user: models.User = Depends(get_current_active_user),
    session_id: Optional[str] = None,
    limit: int = HISTORY_LOOKBACK,
):
    """
    Fetches chat history for the authenticated user.
    Returns a structured response with chat messages.
    """
    user_id = current_user.id
    if not user_id:
        raise HTTPException(status_code=403, detail="Could not identify user.")
    logger.info(
        f"Fetching chat history for User ID {user_id} with session ID {session_id}"
    )

    if session_id is None:
        # If no session ID provided, generate a new one
        session_id = str(uuid.uuid4())
        logger.info(f"No session ID provided. Generated new session ID: {session_id}")
    # Fetch chat history from the database

    chat_history: list[models.ChatMessage] = await crud.get_chat_history(
        db_session=db_session, user_id=user_id, session_id=session_id, limit=limit
    )

    return chat_history


@router.get("/health-llm", tags=["Health"])
async def health_check_llm(
    llm_handler: Any = Depends(get_llm),
):
    """
    Diagnostic endpoint to verify LLM connectivity and configuration.
    """
    logger.info("Manual LLM health check requested.")
    try:
        # Check provider
        provider = "OpenRouter"
        model_name = getattr(llm_handler, "model_name", "Unknown")

        # Attempt generation
        logger.info(f"Testing generation with {provider} ({model_name})...")
        response = await llm_handler.generate_one_off("Hello, are you online? Reply with 'Yes'.")
        
        return {
            "status": "ok",
            "provider": provider,
            "model": model_name,
            "response_preview": response[:50] if response else None,
            "full_response": response
        }
    except Exception as e:
        logger.error(f"LLM Health Check Failed: {e}", exc_info=True)
        return {
            "status": "error",
            "provider": "OpenRouter",
            "model": getattr(llm_handler, "model_name", "Unknown"),
            "error": str(e)
        }


@router.post("/chat", response_model=schemas.ChatMessage)
async def chat_endpoint(
    request_data: schemas.ChatMessageCreate,
    current_user: models.User = Depends(get_current_active_user),
    llm_handler: OpenRouterHandler = Depends(get_llm),
    db_session: AsyncSession = Depends(get_db_session),
):
    """
    Unified chat endpoint that supports regular conversation and tool execution.
    """
    user_id = current_user.id
    user_message = request_data.content
    session_id = request_data.session_id
    
    if not user_id:
        raise HTTPException(status_code=403, detail="Could not identify user.")
        
    logger.info(f"Chat request from user {user_id}: '{user_message[:50]}...'")

    # 1. Initialize Tool Registry and register tools
    registry = AgentToolRegistry()
    registry.register(CardGenerator(llm_handler=llm_handler))
    registry.register(CardCompressor(llm_handler=llm_handler))
    registry.register(CardDecompressor(llm_handler=llm_handler))
    
    available_tools = registry.get_llm_schemas()

    # 2. Store User Message
    chat_message = schemas.ChatMessageCreate(
        user_id=user_id, session_id=session_id, role="user", content=user_message
    )
    await crud.add_chat_message(chat_message=chat_message, db_session=db_session)

    # 3. Fetch History and Format for LLM
    chat_history = await crud.get_chat_history(
        db_session=db_session,
        user_id=user_id,
        session_id=session_id,
        limit=HISTORY_LOOKBACK,
    )
    
    messages = []
    # Add System Prompt with context
    system_prompt = await _get_formatted_system_prompt(user_id, db_session)
    messages.append({"role": "system", "content": system_prompt})
    
    # Add History (reversed because crud returns newest first)
    for msg in reversed(chat_history):
        messages.append({"role": msg.role, "content": msg.content})

    # 4. LLM Call with Tool Support
    try:
        response = await llm_handler.generate_with_tools(
            messages=messages,
            tools=available_tools
        )
        
        ai_reply = ""
        tool_call_executed = False
        
        # Check for tool calls
        if response.choices and response.choices[0].message.tool_calls:
            tool_call = response.choices[0].message.tool_calls[0]
            tool_name = tool_call.function.name
            tool_args = json.loads(tool_call.function.arguments)
            
            logger.info(f"LLM requested tool execution: {tool_name} with {tool_args}")
            
            try:
                tool_instance = registry.get_tool(tool_name)
                result = await tool_instance.execute(
                    db_session=db_session,
                    user_id=user_id,
                    **tool_args
                )
                
                # Format a reply about what the tool did
                if tool_name == "CardGenerator":
                    ai_reply = f"I've generated {result.get('count', 0)} new flashcards for you based on your learning patterns."
                elif tool_name == "CardCompressor":
                    res = result.get('compression_results', {})
                    ai_reply = f"I've compressed your workload. Processed {res.get('cards_processed', 0)} cards and suspended {res.get('suspended', 0)} to make your review session more manageable."
                elif tool_name == "CardDecompressor":
                    ai_reply = f"I've reactivated {result.get('reactivated_count', 0)} of your suspended cards so you have more to practice."
                else:
                    ai_reply = f"I've executed the tool {tool_name} for you."
                
                tool_call_executed = True
                
            except Exception as tool_err:
                logger.error(f"Error executing tool {tool_name}: {tool_err}")
                ai_reply = f"I tried to execute the {tool_name} tool, but encountered an error: {str(tool_err)}"
        
        elif response.choices and response.choices[0].message.content:
            ai_reply = response.choices[0].message.content
        else:
            ai_reply = "I'm sorry, I couldn't generate a response."

        # 5. Store and Return AI Response
        ai_message = schemas.ChatMessageCreate(
            user_id=user_id,
            session_id=session_id,
            role="assistant",
            content=ai_reply,
            message_type="chat"
        )
        stored_reply = await crud.add_chat_message(
            chat_message=ai_message, db_session=db_session
        )
        
        return stored_reply

    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"AI communication failed: {str(e)}")


async def _get_formatted_system_prompt(user_id: uuid.UUID, db_session: AsyncSession) -> str:
    """Helper to fetch cards and format the system prompt."""
    try:
        template = load_prompt_from_template(settings.SYSTEM_PROMPT_TEMPLATE)
        user_notes = await crud.get_all_notes_for_user(user_id=user_id, db_session=db_session)
        learned_sentences = [note.field1.strip() for note in user_notes[:50]]
        
        formatted_list = "No sentences learned yet."
        if learned_sentences:
            formatted_list = "MY KNOWN SENTENCES:\n- " + "\n- ".join(learned_sentences)
            
        return template.format(learned_content=formatted_list)
    except Exception as e:
        logger.error(f"Failed to format system prompt: {e}")
        return "You are a helpful Spanish teaching assistant."


# --- Explain Endpoint ---
@router.post("/explain", response_model=schemas.ExplainResponse)
async def explain_endpoint(
    request_data: schemas.ExplainRequest,
    current_user: models.User = Depends(get_current_active_user),
    llm_handler: OpenRouterHandler = Depends(get_llm),
    teacher_prompt: str = Depends(get_prompt("teacher_prompt")),
):
    """
    Explains a topic using the LLM. Parses the LLM response to extract
    explanation text and structured examples. Requires authentication.
    """
    user_id = current_user.id
    topic = request_data.topic
    context = request_data.context
    if not user_id:
        raise HTTPException(status_code=403, detail="Could not identify user.")
    logger.info(
        f"Received explanation request from User ID {user_id} for topic: '{topic}'"
    )

    # Format the prompt (no changes needed here)
    try:
        full_prompt = teacher_prompt.format(topic=topic, context=context or "N/A")
    except KeyError as e:
        logger.error(f"KeyError formatting teacher prompt. Check placeholder '{e}'.")
        raise HTTPException(
            status_code=500, detail="Server configuration error (explanation prompt)."
        )
    except Exception as e:
        logger.error(f"Error formatting teacher prompt: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Server error processing explanation request."
        )

    try:
        response_text = await llm_handler.generate_one_off(full_prompt)
        logger.debug(
            f"LLM Raw Explanation for User ID {user_id}, Topic '{topic}': '{response_text}'"
        )  # Log full raw response for debug

        if not response_text or response_text.startswith("(Response blocked"):
            logger.error(
                f"LLM returned empty/blocked response for explanation. Topic: {topic}. Response: {response_text}"
            )
            raise HTTPException(
                status_code=500, detail=f"AI returned an empty or blocked response."
            )  # Simplified detail

        # --- PARSING AND STRUCTURING LOGIC ---
        explanation_content: Optional[str] = None
        example_list: Optional[List[ExamplePair]] = None
        parsed_successfully = False

        try:
            # 1. Clean the response text (remove markdown fences, etc.)
            response_text_cleaned = response_text.strip()
            # Handle ```json ... ``` and ``` ... ```
            if response_text_cleaned.startswith("```json"):
                response_text_cleaned = response_text_cleaned[7:-3].strip()
            elif response_text_cleaned.startswith("```"):
                response_text_cleaned = response_text_cleaned[3:-3].strip()

            # Attempt to find JSON object boundaries (more robust than just first/last brace)
            # Look for the first '{' and the last '}'
            start_brace = response_text_cleaned.find("{")
            end_brace = response_text_cleaned.rfind("}")

            if start_brace != -1 and end_brace != -1 and end_brace > start_brace:
                json_string = response_text_cleaned[start_brace : end_brace + 1]
            else:
                # If no clear braces, maybe the whole thing is JSON? Or maybe it's just text.
                json_string = (
                    response_text_cleaned  # Assume it might be the whole string
                )

            # 2. Attempt to parse the cleaned string as JSON
            parsed_data = json.loads(json_string)

            # 3. Validate the PARSED structure (check types)
            if isinstance(parsed_data, dict):
                explanation_content = parsed_data.get("explanation_text")
                raw_examples = parsed_data.get("examples")

                if isinstance(explanation_content, str):
                    # Explanation text looks valid
                    if isinstance(raw_examples, list):
                        # Examples key exists and is a list, try to build ExamplePair list
                        valid_examples = []
                        for item in raw_examples:
                            if (
                                isinstance(item, dict)
                                and "spanish" in item
                                and "english" in item
                            ):
                                try:
                                    # Validate/create ExamplePair to ensure types
                                    valid_examples.append(schemas.ExamplePair(**item))
                                except Exception as pair_exc:
                                    logger.warning(
                                        f"Skipping invalid example item during parsing: {item}. Error: {pair_exc}"
                                    )
                                    continue  # Skip this invalid example item
                            else:
                                logger.warning(
                                    f"Skipping non-dict or incomplete example item: {item}"
                                )
                        example_list = (
                            valid_examples if valid_examples else None
                        )  # Assign if list isn't empty after validation
                        parsed_successfully = (
                            True  # We got text and potentially valid examples
                        )
                    elif raw_examples is None:
                        # Examples key is explicitly null or missing, which is fine
                        example_list = None
                        parsed_successfully = True  # We got the text part
                    else:
                        # Examples key exists but isn't a list - invalid format
                        logger.warning(
                            f"Parsed 'examples' field is not a list. Type: {type(raw_examples)}. Raw: {response_text}"
                        )
                else:
                    # explanation_text key missing or not a string
                    logger.warning(
                        f"Parsed JSON missing 'explanation_text' string. Raw: {response_text}"
                    )
            else:
                # The parsed data wasn't even a dictionary
                logger.warning(
                    f"Parsed JSON is not a dictionary. Type: {type(parsed_data)}. Raw: {response_text}"
                )

        except json.JSONDecodeError:
            logger.warning(
                f"Failed to parse LLM explanation as JSON. Raw: {response_text}"
            )
            # Keep explanation_content as None, handled by fallback below
        except Exception as parse_exc:
            logger.error(
                f"Unexpected error during explanation parsing/validation: {parse_exc}",
                exc_info=True,
            )
            # Keep explanation_content as None, handled by fallback below

        # --- Fallback Logic ---
        if not parsed_successfully:
            # Parsing failed or structure was invalid.
            # Use the ORIGINAL, unprocessed response_text as the explanation.
            # Set examples to None.
            logger.warning(
                f"Explanation structure parsing failed or incomplete. Returning raw text for topic '{topic}'."
            )
            explanation_content = response_text  # Fallback to the raw LLM output
            example_list = None

        # Ensure we always have some explanation text (even if it's the raw fallback)
        if not explanation_content:
            logger.error(
                f"Failed to extract any explanation content for topic '{topic}'. Raw: {response_text}"
            )
            raise HTTPException(
                status_code=500,
                detail="Failed to process the explanation response from AI.",
            )

        # 4. Construct and return the structured response
        return schemas.ExplainResponse(
            topic=topic, explanation_text=explanation_content, examples=example_list
        )

    except HTTPException as http_exc:
        # Re-raise specific HTTP exceptions (like from LLM safety blocks)
        raise http_exc
    except Exception as e:
        # Catch any other unexpected errors during the process
        logger.error(
            f"Error during LLM explanation generation for User ID {user_id}, Topic '{topic}': {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=500, detail=f"An error occurred generating the explanation."
        )
