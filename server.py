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

# --- Setup Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Global Variables & Initialization ---
# These will be initialized properly in the startup event
llm_handler: Optional[GeminiHandler] = None
learned_sentences: List[str] = []
tandem_system_prompt: Optional[str] = None
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

# --- Server Startup Logic ---
@app.on_event("startup")
async def startup_event():
    """Initialize resources when the server starts."""
    global llm_handler, learned_sentences, tandem_system_prompt, teacher_system_prompt, card_creator_prompt
    logger.info("Server starting up...")
    try:
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
        # card_creator_prompt = utils.load_prompt_from_template(
        #     config.CARD_CREATOR_PROMPT_FILE, None
        # ) # Load if/when card feature is re-added

        logger.info("Prompts and flashcards loaded.")
        logger.info("Server startup complete.")

    except Exception as e:
        logger.exception(f"FATAL: Server startup failed: {e}")
        # In a real app, you might want to handle this more gracefully
        # For now, FastAPI might fail to start properly, check logs.
        raise


# --- API Endpoints ---

# Inside server.py

@app.post("/chat", response_model=ChatResponse)
async def handle_chat(payload: ChatMessage):
    """Handles receiving a chat message and returning the AI's reply."""
    # --- vvv ADD/VERIFY LOGGING HERE vvv ---
    logger.info(f"--- ENTERING handle_chat endpoint ---")
    logger.info(f"Received chat message for session: {payload.session_id}")
    # --- ^^^ ADD/VERIFY LOGGING HERE ^^^ ---

    if not llm_handler:
        logger.error("LLM Handler not initialized.")
        raise HTTPException(status_code=503, detail="Service Temporarily Unavailable: LLM Handler not ready.") # Use 503

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

    # --- vvv ADD/VERIFY LOGGING HERE vvv ---
    logger.info(f"--- CALLING llm_handler.send_chat_message for session {session_id} ---")
    if chat_session is None:
         logger.error(f"Critical: chat_session is None just before calling send_chat_message for session {session_id}")
         raise HTTPException(status_code=500, detail="Internal Server Error: Chat session lost")
    # --- ^^^ ADD/VERIFY LOGGING HERE ^^^ ---

    # Send message using the handler
    ai_reply = llm_handler.send_chat_message(chat_session, user_message)
    logger.info(f"--- RETURNED from llm_handler.send_chat_message with result type: {type(ai_reply)} ---") # Add this


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
    # --- vvv ADD/VERIFY LOGGING HERE vvv ---
    logger.info(f"--- ENTERING handle_explanation endpoint ---")
    logger.info(f"Received explanation query: '{payload.query[:50]}...'") # Log snippet
    # --- ^^^ ADD/VERIFY LOGGING HERE ^^^ ---

    if not llm_handler:
        logger.error("LLM Handler not initialized during explain request.")
        raise HTTPException(status_code=503, detail="Service Temporarily Unavailable: LLM Handler not ready.")
    if not teacher_system_prompt:
         logger.error("Teacher prompt not loaded during explain request.")
         raise HTTPException(status_code=500, detail="Server error: Teacher prompt unavailable.")

    query = payload.query
    # Construct prompt for the teacher role
    prompt = f"{teacher_system_prompt}\n\n--- User Query ---\nPlease explain: \"{query}\""

    # --- vvv ADD/VERIFY LOGGING HERE vvv ---
    logger.info(f"--- CALLING llm_handler.generate_one_off ---")
    # --- ^^^ ADD/VERIFY LOGGING HERE ^^^ ---

    # Use the one-off generation method
    explanation = llm_handler.generate_one_off(prompt)
    logger.info(f"--- RETURNED from llm_handler.generate_one_off with result type: {type(explanation)} ---") # Add this

    if explanation is None:
        logger.warning(f"LLM Handler returned None for explanation query: '{query}'. Sending error message.")
        # Return a valid ExplainResponse object, but indicate failure
        return ExplainResponse(
            explanation="(Sorry, an error occurred or the AI couldn't generate an explanation.)"
        )

    logger.info(f"Sending explanation for query: '{query}'")
    return ExplainResponse(explanation=explanation)


app.mount("/static", StaticFiles(directory="static"), name="static")

# --- Serve index.html at the root ---
@app.get("/", response_class=FileResponse)
async def read_index():
    """Serves the main index.html file."""
    logger.info("Root endpoint accessed, serving index.html")
    # Ensure index.html is inside the 'static' folder
    # Need 'import os' at the top of the file for this to work
    import os
    index_path = os.path.join("static", "index.html")
    if not os.path.exists(index_path):
         raise HTTPException(status_code=404, detail="index.html not found")
    return FileResponse(index_path)




# --- Add this block to run with uvicorn locally ---
if __name__ == "__main__":
    import uvicorn
    logger.info("Starting Uvicorn server...")
    # Run on 0.0.0.0 to make it accessible on your local network
    # Use port 8000 (or another available port)
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)