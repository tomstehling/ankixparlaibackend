import sys
import os
import logging
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional, List # Keep necessary basic types

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
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
from routers import authentication, chat, cards, sync
import dependencies # Import shared dependencies setup

# --- Setup Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Lifespan for Startup/Shutdown Logic ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources when the server starts and clean up."""
    logger.info("--- Server starting up ---")

    # Initialize Database
    try:
        db_file = getattr(config, 'DATABASE_FILE', 'chatbot_cards.db')
        database.DATABASE_FILE = db_file
        database.initialize_database()
    except Exception as e:
        logger.exception("FATAL: Database initialization failed.")
        sys.exit(1)

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
        sys.exit(1)

    # Load prompts
    try:
        app.state.system_prompt = utils.load_prompt_from_template(config.SYSTEM_PROMPT_TEMPLATE)
        app.state.teacher_prompt = utils.load_prompt_from_template(config.TEACHER_PROMPT_TEMPLATE)
        app.state.sentence_proposer_prompt = utils.load_prompt_from_template(config.SENTENCE_PROPOSER_PROMPT)
        app.state.sentence_validator_prompt = utils.load_prompt_from_template(config.SENTENCE_VALIDATOR_PROMPT)
        logger.info("Core prompts loaded successfully and stored in app state.")
    except FileNotFoundError as e:
        logger.error(f"FATAL: Failed to load prompts - {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"FATAL: An unexpected error occurred loading prompts: {e}")
        sys.exit(1)

    # Load initial 'learned' sentences (Optional - Consider if still needed globally)
    # If needed, load and store in app.state.learned_sentences = ...
    # For now, we'll assume it's not globally essential or managed differently
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


    # Initialize simple in-memory chat session store in app state
    app.state.chat_sessions_store: Dict[str, Any] = {}
    logger.info("In-memory chat session store initialized in app state.")

    logger.info("--- Server startup complete ---")
    yield # Application runs here
    # --- Shutdown Logic (if any) ---
    logger.info("--- Server shutting down ---")


# --- FastAPI Application Instance ---
app = FastAPI(
    title="Spanish Learning Chatbot API",
    version="1.0.0",
    lifespan=lifespan # Use the lifespan context manager
)

# --- CORS Middleware ---
origins = [
    "http://localhost:5173", # Vue Dev
    "http://127.0.0.1:5173",
    "http://localhost:5500", # VS Code Live Server
    "http://127.0.0.1:5500",
    "http://localhost:8080", # python http.server
    "http://127.0.0.1:8080",
    # Add production frontend/backend URLs here
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if "*" in origins else origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Include Routers ---
app.include_router(authentication.router, prefix="/auth", tags=["Authentication"])
app.include_router(chat.router, tags=["Chat & Explain"])
app.include_router(cards.router, prefix="/cards", tags=["Flashcards & SRS"])
app.include_router(sync.router, prefix="/sync", tags=["Anki Sync (Deprecated?)"])


# Simple root if no static files are served:
@app.get("/", tags=["Root"], include_in_schema=True)
async def read_root():
    """Provides a simple message indicating the API is running."""
    return {"message": "Spanish Learning Chatbot API is running."}


# --- Main Execution Guard (for local testing) ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    logger.info(f"Starting Uvicorn server locally on http://0.0.0.0:{port} with reload enabled")
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)