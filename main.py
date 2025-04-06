import sys
import os
import logging
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional, List # Keep necessary basic types

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles # Keep if needed, but currently not used in provided code
from fastapi.responses import FileResponse, HTMLResponse

# --- Load Environment Variables ---
from dotenv import load_dotenv
load_dotenv()

# --- Project Imports ---
import config
import utils
from llm_handler import GeminiHandler
import database
import security # Needed for SECRET_KEY check during startup
# --- Import Routers ---
# Remove or comment out the sync import
# from routers import authentication, chat, cards, sync
from routers import authentication, chat, cards, twilio_whatsapp # Import active routers + new twilio router
import dependencies # Import shared dependencies setup

# --- Setup Logging ---
# logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s') # Old line
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s') # New line - Changed level to DEBUG and added logger name
logger = logging.getLogger(__name__)

# --- Lifespan for Startup/Shutdown Logic ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources when the server starts and clean up."""
    logger.info("--- Server starting up ---")

    # Initialize Database
    try:
        db_file = getattr(config, 'DATABASE_FILE', 'chatbot_cards.db')
        # Ensure DATABASE_FILE in database module is updated if needed, though direct use is often better avoided
        # database.DATABASE_FILE = db_file # This might not be necessary if database.py uses the import correctly
        database.initialize_database()
        logger.info("Database initialization verified.") # Log success after call
    except Exception as e:
        logger.exception("FATAL: Database initialization failed.")
        sys.exit(1) # Exit if DB fails

    # Initialize Gemini Handler
    try:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set.")
        _ = config.SECRET_KEY # Trigger warning from config.py if default
        llm_handler = GeminiHandler(api_key=api_key, model_name=config.GEMINI_MODEL_NAME)
        app.state.llm_handler = llm_handler # Store handler in app state
        logger.info("Gemini Handler initialized successfully.")
    except Exception as e:
        logger.exception("FATAL: Failed to initialize Gemini Handler.")
        app.state.llm_handler = None
        # Allow startup without LLM? Or exit? For now, log and continue.
        # sys.exit(1)

    # Load prompts
    try:
        app.state.system_prompt = utils.load_prompt_from_template(config.SYSTEM_PROMPT_TEMPLATE)
        app.state.teacher_prompt = utils.load_prompt_from_template(config.TEACHER_PROMPT_TEMPLATE)
        app.state.sentence_proposer_prompt = utils.load_prompt_from_template(config.SENTENCE_PROPOSER_PROMPT)
        app.state.sentence_validator_prompt = utils.load_prompt_from_template(config.SENTENCE_VALIDATOR_PROMPT)
        logger.info("Core prompts loaded successfully and stored in app state.")
    except FileNotFoundError as e:
        logger.error(f"FATAL: Failed to load prompts - {e}")
        sys.exit(1) # Exit if prompts missing
    except Exception as e:
        logger.error(f"FATAL: An unexpected error occurred loading prompts: {e}")
        sys.exit(1) # Exit on other prompt errors

    # Load initial 'learned' sentences (Optional - Check if still relevant)
    # This seems less relevant now with integrated DB, maybe remove? Kept for now.
    try:
        flashcard_file = getattr(config, 'ANKI_FLASHCARDS_FILE', None)
        if flashcard_file and os.path.exists(flashcard_file):
             app.state.learned_sentences = utils.load_flashcards(flashcard_file)
             logger.info(f"Loaded {len(app.state.learned_sentences)} known sentences from {flashcard_file}.")
        elif flashcard_file:
             logger.info(f"{flashcard_file} not found, starting with empty learned sentences list.")
             app.state.learned_sentences = []
        else:
             logger.info("ANKI_FLASHCARDS_FILE not defined, starting empty.")
             app.state.learned_sentences = []
    except Exception as e:
        logger.error(f"Failed to load initial learned sentences: {e}", exc_info=True)
        app.state.learned_sentences = []


    # Initialize simple in-memory chat session store in app state (potentially for unlinked users?)
    app.state.chat_sessions_store: Dict[str, Any] = {}
    logger.info("In-memory chat session store initialized in app state.")

    logger.info("--- Server startup complete ---")
    yield # Application runs here
    # --- Shutdown Logic (if any) ---
    logger.info("--- Server shutting down ---")


# --- FastAPI Application Instance ---
app = FastAPI(
    title="Spanish Learning Chatbot API",
    version="1.1.0", # Bump version
    lifespan=lifespan # Use the lifespan context manager
)

# --- CORS Middleware ---
# Define allowed origins explicitly or use "*" for development (less secure)
# Ensure your frontend origins (localhost:5173, localhost:5500) are included
origins = [
    "http://localhost:5173", # Vue Dev
    "http://127.0.0.1:5173",
    "http://localhost:5500", # VS Code Live Server / Python http.server for static chat
    "http://127.0.0.1:5500",
    # Add production frontend URL here when deployed
    # e.g., "https://your-frontend-domain.com"
    getattr(config, "WEB_APP_BASE_URL", None) # Add base URL from config if set
]
# Filter out None in case WEB_APP_BASE_URL is not set
origins = [origin for origin in origins if origin]

# Add ngrok URL for testing if running via ngrok
NGROK_TUNNEL_URL = os.getenv("NGROK_TUNNEL_URL")
if NGROK_TUNNEL_URL:
    origins.append(NGROK_TUNNEL_URL)
    logger.info(f"Allowing CORS for ngrok tunnel: {NGROK_TUNNEL_URL}")


app.add_middleware(
    CORSMiddleware,
    allow_origins=origins, # Use the defined list
    allow_credentials=True,
    allow_methods=["*"], # Allows all methods (GET, POST, PUT, DELETE, etc.)
    allow_headers=["*"], # Allows all headers
)

# --- Include Routers ---
app.include_router(authentication.router, prefix="/auth", tags=["Authentication"])
app.include_router(chat.router, tags=["Chat & Explain"]) # No prefix needed based on previous context
app.include_router(cards.router, prefix="/cards", tags=["Flashcards & SRS"])
app.include_router(twilio_whatsapp.router, prefix="/whatsapp", tags=["WhatsApp"]) # Add the new router
# Remove or comment out the sync router inclusion
# app.include_router(sync.router, prefix="/sync", tags=["Anki Sync (Deprecated?)"])


@app.get("/", tags=["Root"], include_in_schema=True)
async def read_root():
    """Provides a simple message indicating the API is running."""
    return {"message": "Spanish Learning Chatbot API is running."}


# --- Main Execution Guard (for local testing) ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    # Use host="127.0.0.1" for local only or "0.0.0.0" to expose externally
    host = os.environ.get("HOST", "0.0.0.0") # Default to 0.0.0.0 to be accessible within network
    logger.info(f"Starting Uvicorn server locally on http://{host}:{port} with reload enabled")
    uvicorn.run("main:app", host=host, port=port, reload=True)