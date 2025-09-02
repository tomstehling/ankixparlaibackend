import uvicorn
import sys
import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.sql import text


# --- project imports
from core.config import settings
import utils
from services.llm_handler import GeminiHandler
from routers import authentication, chat, cards, feedback
from sqlalchemy.ext.asyncio import async_sessionmaker

# --- Logging Configuration ---
log_level = getattr(logging, getattr(settings, 'LOG_LEVEL', 'DEBUG').upper(), logging.INFO)
logging.basicConfig(level=log_level, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- load evironment variables from .env file
load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources when the server starts and clean up."""
    logger.info("--- Server starting up ---")

    # Initialize Gemini Handler
    try:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set.")
        # Check secret key during startup for security warning
        _ = settings.AUTH_MASTER_KEY # Trigger warning from config.py if default
        llm_handler = GeminiHandler(api_key=api_key, model_name=settings.GEMINI_MODEL_NAME)
        app.state.llm_handler = llm_handler # Store handler in app state
        logger.info(f"Gemini Handler initialized successfully with model '{settings.GEMINI_MODEL_NAME}'.")
    except Exception as e:
        logger.exception("FATAL: Failed to initialize Gemini Handler.")
        app.state.llm_handler = None
        # Decide if LLM is critical for startup
        # sys.exit(1)

    # Load prompts
    try:
        app.state.system_prompt = utils.load_prompt_from_template(settings.SYSTEM_PROMPT_TEMPLATE)
        app.state.teacher_prompt = utils.load_prompt_from_template(settings.TEACHER_PROMPT_TEMPLATE)
        app.state.sentence_proposer_prompt = utils.load_prompt_from_template(settings.SENTENCE_PROPOSER_PROMPT)
        app.state.sentence_validator_prompt = utils.load_prompt_from_template(settings.SENTENCE_VALIDATOR_PROMPT)
        logger.info("Core prompts loaded successfully and stored in app state.")
    except FileNotFoundError as e:
        logger.error(f"FATAL: Failed to load prompts - {e}")
        sys.exit(1) # Exit if prompts missing
    except Exception as e:
        logger.error(f"FATAL: An unexpected error occurred loading prompts: {e}")
        sys.exit(1) 

    # check database connection
    # pooled transaction on supabase needs the cache removed, but local postgres doesnt know the connect args so they are added conditionally
    if settings.DATABASE_URL:
    # --- Database Connection with VERBOSE LOGGING ---
        logger.info("--- Preparing Database Connection ---")

        engine = create_async_engine(
            settings.DATABASE_URL,
            echo=False
        )
    else:
        logger.error(f"FATAL: No Database URL found")
        sys.exit(1) 





    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1")) 
        logger.info("Database connection successful.")
        app.state.db_engine = engine
        app.state.db_session_factory = async_sessionmaker(bind=engine)

    except Exception as e:
        logger.error(f"FATAL: Database connection failed - {e}")
        sys.exit(1)
    

    logger.info("--- Server startup complete ---")
    yield # Application runs here
    
    # --- Shutdown Logic ---
    logger.info("--- Server shutting down ---")

    if hasattr(app.state, 'db_engine'):
        logger.info("Disposing of database engine connection pool.")
        await app.state.db_engine.dispose()
   




# --- FastAPI Application Instance ---
app = FastAPI(
    title="Spanish Learning Chatbot API",
    version="1.3.0", # Bump version for import feature
    lifespan=lifespan # Use the lifespan context manager
)

# --- CORS Middleware ---
origins = ["*"]
# Filter out None/empty strings
origins = [origin for origin in origins if origin and origin.strip()]

logger.info(f"Configuring CORS for origins: {origins}")
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
app.include_router(feedback.router, tags=["Feedback"])


@app.get("/", tags=["Root"], include_in_schema=True)
async def read_root():
    """Provides a simple message indicating the API is running."""
    return {"message": "Spanish Learning Chatbot API is running."}


# --- Main Execution Guard (for local testing) ---
if __name__ == "__main__":
    # Use port/host from config or environment variables
    port = settings.PORT
    host = settings.HOST # Use HOST from config (e.g., "0.0.0.0")

    # Log effective settings
    logger.info(f"Starting Uvicorn server configuration:")
    logger.info(f"  - Host: {host}")
    logger.info(f"  - Port: {port}")
    logger.info(f"  - Reload: {settings.RELOAD}")
    logger.info(f"  - Log Level: {log_level}")

    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=settings.RELOAD, # Use RELOAD from config
        log_level=log_level # Pass log level to uvicorn
        )
    
    