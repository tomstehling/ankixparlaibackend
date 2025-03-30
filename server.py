# server.py

import uuid
import sys 
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware # To allow frontend calls
from pydantic import BaseModel
from typing import Dict, Optional, List, Any # Add Any here
import logging # Use logging instead of print for server messages
from fastapi.staticfiles import StaticFiles # <-- Import StaticFiles
from fastapi.responses import FileResponse  # <-- Import FileResponse


# --- Load Environment Variables ---
# Load early to ensure API keys are available for handlers
from dotenv import load_dotenv
load_dotenv()

# --- Project Imports ---
import config
import utils
from llm_handler import GeminiHandler
import database # <-- Import the new database module

# --- Setup Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Global Variables & Initialization ---
# These will be initialized properly in the startup event
llm_handler: Optional[GeminiHandler] = None
# --- vvv Store learned sentences globally (can be updated by sync) vvv ---
learned_sentences: List[str] = []
# --- ^^^ ---
tandem_system_prompt: Optional[str] = None # Will be rebuilt if learned_sentences changes
teacher_system_prompt: Optional[str] = None
card_creator_prompt: Optional[str] = None # Keep for potential future use

# Simple in-memory storage for chat sessions (Session ID -> ChatSession Object)
# WARNING: This data is lost when the server restarts! Suitable for simple testing.
chat_sessions_store: Dict[str, Any] = {}

# --- FastAPI Application Instance ---
app = FastAPI(title="Spanish Tandem Chatbot API")

# --- CORS Middleware ---
# Allow requests from your frontend (adjust origins if needed for deployment)
# Using ["*"] is permissive for local development, restrict in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Or specify frontend origins like ["http://localhost:8000", "http://127.0.0.1:8000"]
    allow_credentials=True,
    allow_methods=["*"], # Allows all methods (GET, POST, etc.)
    allow_headers=["*"], # Allows all headers
)


# --- Pydantic Models for Request/Response ---
class ChatMessage(BaseModel):
    message: str
    session_id: Optional[str] = None # Frontend can send existing ID or get a new one

class ChatResponse(BaseModel):
    reply: str
    session_id: str # Always return the session ID

class ExplainQuery(BaseModel):
    query: str

class ExplainResponse(BaseModel):
    explanation: str
    query: str # Add query back for frontend context

class AddCardRequest(BaseModel):
    query: str # The Spanish word/phrase to add

class AddCardResponse(BaseModel):
    message: str
    success: bool

class SyncDeckRequest(BaseModel):
    fronts: List[str] # List of Spanish sentences from Anki

class GetNewCardsResponse(BaseModel):
    cards: List[Dict[str, Any]] # List of card dicts {id, front, back, tags}

class MarkSyncedRequest(BaseModel):
    card_ids: List[int] # List of IDs successfully added to Anki


# --- Server Startup Logic ---
@app.on_event("startup")
async def startup_event():
    """Initialize resources when the server starts."""
    global llm_handler, learned_sentences, tandem_system_prompt, teacher_system_prompt, card_creator_prompt
    logger.info("Server starting up...")
    try:
        database.initialize_database()

        # Configure API (needed once for the library)
        utils_temp = sys.modules.get('utils') # Need a way to call configure_api if moved
        # Let's keep configure_api simple here for now
        import google.generativeai as genai
        import os
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key: raise ValueError("GOOGLE_API_KEY missing")
        genai.configure(api_key=api_key)
        logger.info("Gemini API configured.")

        # Initialize LLM Handler
        llm_handler = GeminiHandler(config.MODEL_NAME)

        # Load data using utils
        learned_sentences = utils.load_flashcards(config.FLASHCARD_FILE)
        tandem_system_prompt = utils.load_prompt_from_template(
            config.TANDEM_PROMPT_TEMPLATE_FILE, learned_sentences
        )
        teacher_system_prompt = utils.load_prompt_from_template(
            config.TEACHER_PROMPT_TEMPLATE_FILE, None
        )
        # --- vvv LOAD CARD CREATOR PROMPT vvv ---
        card_creator_prompt = utils.load_prompt_from_template(
            config.CARD_CREATOR_PROMPT_FILE, None
        )
        # --- ^^^ LOAD CARD CREATOR PROMPT ^^^ ---

        logger.info("Prompts and flashcards loaded.")
        logger.info("Server startup complete.")

    except Exception as e:
        logger.exception(f"FATAL: Server startup failed: {e}")
        # In a real app, you might want to handle this more gracefully
        # For now, FastAPI might fail to start properly, check logs.
        raise


# --- API Endpoints ---

@app.post("/chat", response_model=ChatResponse)
async def handle_chat(payload: ChatMessage):
    """Handles receiving a chat message and returning the AI's reply."""
    logger.info(f"--- ENTERING handle_chat endpoint ---")
    logger.info(f"Received chat message for session: {payload.session_id}")

    if not llm_handler:
        logger.error("LLM Handler not initialized.")
        raise HTTPException(status_code=503, detail="Service Temporarily Unavailable: LLM Handler not ready.")

    session_id = payload.session_id
    user_message = payload.message

    # Get or create chat session
    chat_session = None # Initialize to None
    if session_id and session_id in chat_sessions_store:
        logger.info(f"Using existing chat session: {session_id}")
        chat_session = chat_sessions_store[session_id]
    else:
        logger.info("Attempting to create new chat session...")
        if not llm_handler: # Double check handler again before use
             logger.error("LLM Handler became unavailable before creating session.")
             raise HTTPException(status_code=503, detail="Service Temporarily Unavailable")
        chat_session = llm_handler.create_chat_session(tandem_system_prompt)

        if not chat_session:
            logger.error("Failed to create new chat session via LLM Handler.")
            raise HTTPException(status_code=500, detail="Server error: Could not create chat session.")

        session_id = str(uuid.uuid4())
        chat_sessions_store[session_id] = chat_session
        logger.info(f"New chat session created with ID: {session_id}")

    logger.info(f"--- CALLING llm_handler.send_chat_message for session {session_id} ---")
    if chat_session is None:
         logger.error(f"Critical: chat_session is None just before calling send_chat_message for session {session_id}")
         raise HTTPException(status_code=500, detail="Internal Server Error: Chat session lost")

    # Send message using the handler
    ai_reply = llm_handler.send_chat_message(chat_session, user_message)
    logger.info(f"--- RETURNED from llm_handler.send_chat_message with result type: {type(ai_reply)} ---")

    if ai_reply is None:
        logger.warning(f"LLM Handler returned None for session: {session_id}. Sending error message.")
        # Return a valid ChatResponse object, but indicate failure in the reply
        return ChatResponse(
            reply="(Sorry, an error occurred or the AI didn't respond. Please try again.)",
            session_id=session_id # session_id should be valid here
        )

    logger.info(f"Sending reply for session: {session_id}")
    return ChatResponse(reply=ai_reply, session_id=session_id)

@app.post("/explain", response_model=ExplainResponse)
async def handle_explanation(payload: ExplainQuery):
    """Handles receiving a query for explanation."""
    logger.info(f"--- ENTERING handle_explanation endpoint ---")
    logger.info(f"Received explanation query: '{payload.query[:50]}...'")

    if not llm_handler:
        logger.error("LLM Handler not initialized during explain request.")
        raise HTTPException(status_code=503, detail="Service Temporarily Unavailable: LLM Handler not ready.")
    if not teacher_system_prompt:
         logger.error("Teacher prompt not loaded during explain request.")
         raise HTTPException(status_code=500, detail="Server error: Teacher prompt unavailable.")

    query = payload.query
    # Construct prompt for the teacher role
    prompt = f"{teacher_system_prompt}\n\n--- User Query ---\nPlease explain: \"{query}\""

    logger.info(f"--- CALLING llm_handler.generate_one_off ---")
    # Use the one-off generation method
    explanation = llm_handler.generate_one_off(prompt)
    logger.info(f"--- RETURNED from llm_handler.generate_one_off with result type: {type(explanation)} ---")

    if explanation is None:
        logger.warning(f"LLM Handler returned None for explanation query: '{query}'. Sending error message.")
        # Return a valid ExplainResponse object, but indicate failure
        return ExplainResponse(
            explanation="(Sorry, an error occurred or the AI couldn't generate an explanation.)",
            query=query
        )

    logger.info(f"Sending explanation for query: '{query}'")
    return ExplainResponse(explanation=explanation, query=query)

@app.post("/addcard", response_model=AddCardResponse)
async def handle_add_card(payload: AddCardRequest):
    """Generates card data and appends it to a file for later import."""
    logger.info(f"--- ENTERING handle_add_card endpoint for query: '{payload.query[:50]}...' ---")

    if not llm_handler:
        logger.error("LLM Handler not initialized during addcard request.")
        raise HTTPException(status_code=503, detail="Service Temporarily Unavailable")
    if not card_creator_prompt:
         logger.error("Card Creator prompt not loaded during addcard request.")
         raise HTTPException(status_code=500, detail="Server error: Card Creator prompt unavailable.")

    spanish_query = payload.query
    output_filename = "new_cards_to_import.csv" # Or .txt, choose format
    card_data_text = "" # For potential error logging

    try:
        # 1. Get structured data from AI Card Creator role
        prompt_for_creator = f"{card_creator_prompt}\n\nInput: {spanish_query}"
        logger.info("Delegating Card Creator request to LLM Handler...")
        card_data_response = llm_handler.generate_one_off(prompt_for_creator)

        if not card_data_response or card_data_response.startswith("(Response blocked"):
            logger.warning(f"Card Creator AI returned empty/blocked response: {card_data_response}")
            return AddCardResponse(message="AI could not generate card data.", success=False)

        card_data_text = card_data_response.strip()
        logger.info(f"AI Card Data received: {card_data_text}")

        # 2. Parse the AI response (using "||" delimiter)
        parts = [p.strip() for p in card_data_text.split("||")]
        if len(parts) != 4:
            logger.error(f"Cannot parse AI response into 4 parts: {card_data_text}")
            return AddCardResponse(message="Error parsing AI response.", success=False)

        spanish_front, english_back, grammar_info, topic_tag = parts
        tags = [tag.strip().replace(" ", "_") for tag in [grammar_info, topic_tag] if tag.strip()]
        anki_tags_string = " ".join(tags) # Anki uses space-separated tags in CSV

        # 3. Format data for CSV (handle quotes within fields)
        def escape_csv_field(field):
            if '"' in field or ',' in field or '\n' in field:
                # Replace " with "" (standard CSV escape)
                escaped_field = field.replace('"', '""')
                # Wrap the result in double quotes
                return '"' + escaped_field + '"'
            return field # Return unchanged if no special chars

        csv_line = f"{escape_csv_field(spanish_front)},{escape_csv_field(english_back)},{escape_csv_field(anki_tags_string)}\n"

        # 4. Append to file (consider potential concurrency issues in high load)
        try:
            with open(output_filename, 'a', encoding='utf-8') as f:
                f.write(csv_line)
            logger.info(f"Successfully appended card data to {output_filename}")
            return AddCardResponse(message="Card data saved for import!", success=True)
        except IOError as e:
            logger.exception(f"IOError writing to {output_filename}: {e}")
            return AddCardResponse(message="Error saving card data to file.", success=False)

    except Exception as e:
        logger.exception(f"Unexpected error during card creation for query '{spanish_query}': {e}")
        return AddCardResponse(message="An unexpected server error occurred.", success=False)

@app.post("/sync_anki_deck")
async def sync_anki_deck(payload: SyncDeckRequest):
    """Receives the current list of card fronts from the Anki plugin."""
    global learned_sentences # Declare modification of global
    logger.info(f"Received sync_anki_deck request with {len(payload.fronts)} card fronts.")
    # Basic validation
    if not isinstance(payload.fronts, list):
         logger.error("Invalid data format received for /sync_anki_deck. 'fronts' should be a list.")
         raise HTTPException(status_code=400, detail="Invalid data format: 'fronts' must be a list.")

    # Replace the global list used for prompts
    learned_sentences = payload.fronts
    logger.info("Updated learned_sentences list.")

    # Reload prompts to reflect the new list
    _reload_prompts()

    return {"message": f"Successfully updated learned sentences list with {len(learned_sentences)} items."}

@app.get("/get_new_chatbot_cards", response_model=GetNewCardsResponse)
async def get_new_chatbot_cards():
    """Provides cards generated via chatbot (status='pending') to the Anki plugin."""
    logger.info("Received request for new chatbot cards")
    cards = database.get_pending_cards()
    return GetNewCardsResponse(cards=cards)

@app.post("/mark_cards_synced")
async def mark_cards_synced(payload: MarkSyncedRequest):
    """Marks cards as successfully synced to Anki."""
    logger.info(f"Received request to mark {len(payload.card_ids)} cards as synced")
    success = database.mark_cards_as_synced(payload.card_ids)
    if success:
        return {"message": f"Successfully marked {len(payload.card_ids)} cards as synced"}
    else:
        raise HTTPException(status_code=500, detail="Failed to update card statuses")

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=FileResponse)
async def read_index():
    """Serves the main index.html file."""
    logger.info("Root endpoint accessed, serving index.html")
    import os
    index_path = os.path.join("static", "index.html")
    if not os.path.exists(index_path):
         raise HTTPException(status_code=404, detail="index.html not found")
    return FileResponse(index_path)

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting Uvicorn server...")
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)