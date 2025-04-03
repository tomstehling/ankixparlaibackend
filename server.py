# server.py

import uuid
import sys
import os
import json
from fastapi import (
    FastAPI,
    HTTPException,
    Request,
    Body,
    Depends, # <<< Added
    status   # <<< Added
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm # <<< Added
from pydantic import BaseModel, Field, EmailStr # <<< Added EmailStr
from typing import Dict, Optional, List, Any
import logging
from contextlib import asynccontextmanager # <<< Added
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
import uvicorn # <<< Added for local running guard

# --- Load Environment Variables ---
from dotenv import load_dotenv
load_dotenv() # Load environment variables from .env file if present

# --- Project Imports ---
import config # Loads constants from config.py
import utils # Loads utility functions
from llm_handler import GeminiHandler # Handles LLM interaction
import database # Handles database operations
# --- vvv Added Security and Model Imports vvv ---
import security # Handles password hashing, JWT
from models import ( # Assuming models are in models.py now
    UserBase, UserCreate, UserLogin, UserPublic,
    Token, TokenData,
    ChatMessage, ChatResponse, ExplainRequest, ExplainResponse, # Keep existing models
    ProposeSentenceRequest, ValidateTranslateRequest, SaveCardRequest,
    AnkiDeckUpdateRequest, GetNewCardsResponse, MarkSyncedRequest
)
# --- ^^^ Added Security and Model Imports ^^^ ---


# --- Setup Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Global Variables & Initialization ---
llm_handler: Optional[GeminiHandler] = None
learned_sentences: List[str] = []
system_prompt: Optional[str] = None
teacher_prompt: Optional[str] = None
sentence_proposer_prompt: Optional[str] = None
sentence_validator_prompt: Optional[str] = None

# Simple in-memory store for chat sessions (replace with persistent storage if needed)
chat_sessions_store: Dict[str, Any] = {}
DEFAULT_SESSION_ID = "default_user" # Placeholder

# --- Lifespan for Startup/Shutdown Logic ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources when the server starts and clean up."""
    global llm_handler, system_prompt, teacher_prompt
    global sentence_proposer_prompt, sentence_validator_prompt
    global learned_sentences
    logger.info("--- Server starting up ---")

        # Initialize Database (Ensure all tables exist)
    try:
        db_file = getattr(config, 'DATABASE_FILE', 'chatbot_cards.db')
        database.DATABASE_FILE = db_file # Ensure database module uses the correct file path
        database.initialize_database() # <<< This handles BOTH users and cards tables now
        # Logger message moved inside initialize_database if successful there
        # logger.info(f"Database '{db_file}' tables checked/created successfully.") # <<< You can remove this line too if initialize_database logs success
    except Exception as e:
        logger.exception("FATAL: Database initialization failed.")
        sys.exit(1) # Exit if DB fails

    # Initialize Gemini Handler
    try:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set.")
        # Check if SECRET_KEY is set (warn if default) - triggers warning from config.py
        _ = config.SECRET_KEY
        llm_handler = GeminiHandler(api_key=api_key, model_name=config.GEMINI_MODEL_NAME)
        logger.info("Gemini Handler initialized successfully.")
    except Exception as e:
        logger.exception("FATAL: Failed to initialize Gemini Handler.")
        llm_handler = None
        sys.exit(1) # Exit if LLM fails

    # Load prompts
    try:
        system_prompt = utils.load_prompt_from_template(config.SYSTEM_PROMPT_TEMPLATE)
        teacher_prompt = utils.load_prompt_from_template(config.TEACHER_PROMPT_TEMPLATE)
        sentence_proposer_prompt = utils.load_prompt_from_template(config.SENTENCE_PROPOSER_PROMPT)
        sentence_validator_prompt = utils.load_prompt_from_template(config.SENTENCE_VALIDATOR_PROMPT)
        logger.info("Core prompts loaded successfully.")
    except FileNotFoundError as e:
        logger.error(f"FATAL: Failed to load prompts - {e}")
        sys.exit(1) # Exit if prompts fail
    except Exception as e:
        logger.error(f"FATAL: An unexpected error occurred loading prompts: {e}")
        sys.exit(1)

    # Load initial 'learned' sentences (Optional) - Kept for now
    try:
        flashcard_file = getattr(config, 'ANKI_FLASHCARDS_FILE', None)
        if flashcard_file and os.path.exists(flashcard_file):
             learned_sentences = utils.load_flashcards(flashcard_file)
             logger.info(f"Loaded {len(learned_sentences)} known sentences from {flashcard_file}.")
        elif flashcard_file:
             logger.info(f"{flashcard_file} not found, starting with empty learned sentences list.")
        else:
             logger.info("ANKI_FLASHCARDS_FILE not defined, starting empty.")
        learned_sentences = learned_sentences if learned_sentences else []
    except Exception as e:
        logger.error(f"Failed to load initial learned sentences: {e}", exc_info=True)
        learned_sentences = []

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
# This is permissive for development. Tighten origins for production.
origins = [
    "http://localhost:5173", # Default Vite dev server port for Vue app
    "http://127.0.0.1:5173",
    # Add your production frontend URL here later
    # e.g., "https://your-frontend-app.on.cloudrun.app"
    # Consider adding your deployed backend URL if frontend needs to specify it
]
# Allow the existing static HTML frontend if still needed during transition
# Add its origin if it's served differently, e.g., "http://localhost:8000" if testing locally
# origins.append("http://localhost:8000") # If static files are served by FastAPI itself

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if "*" in origins else origins, # Allow configured origins or wildcard
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- OAuth2 Scheme ---
# Points to the '/token' endpoint for login
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# --- Dependency to Get Current User ---
async def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    """
    Dependency: Decodes token, validates user, returns user data (as dict).
    Raises HTTPException 401 if token invalid/expired or user not found.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = security.decode_access_token(token)
    if payload is None:
        logger.warning("Token decoding failed or token is invalid/expired.")
        raise credentials_exception

    user_id_str: str | None = payload.get("sub") # Assumes user_id stored in 'sub'
    if user_id_str is None:
        logger.warning("Token payload missing 'sub' (user ID).")
        raise credentials_exception

    try:
        user_id = int(user_id_str)
    except (ValueError, TypeError):
         logger.warning(f"Invalid user ID format in token 'sub': {user_id_str}")
         raise credentials_exception

    # Fetch user details (excluding password!) from database
    user = database.get_user_by_id(user_id)
    if user is None:
        logger.warning(f"User ID {user_id} from token not found in database.")
        raise credentials_exception

    logger.info(f"Authenticated user ID: {user_id}")
    return user # Return user dict {id, email, created_at}

async def get_current_active_user(current_user: dict = Depends(get_current_user)):
    """
    Dependency: Gets user from token via get_current_user.
    Placeholder for future 'is_active' checks. Returns user dict.
    """
    # Example: Add check if you add an 'is_active' field later
    # if not current_user.get("is_active", True): # Default to active if field missing
    #     raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
    return current_user # Return the user dictionary

# --- API Endpoints ---

# --- Authentication Endpoints ---

@app.post("/register", response_model=UserPublic, status_code=status.HTTP_201_CREATED)
async def register_user(user_data: UserCreate):
    """Registers a new user in the database."""
    logger.info(f"Registration attempt for email: {user_data.email}")
    existing_user = database.get_user_by_email(user_data.email)
    if existing_user:
        logger.warning(f"Registration failed: Email '{user_data.email}' already exists.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    hashed_password = security.get_password_hash(user_data.password)
    user_id = database.add_user_to_db(email=user_data.email, hashed_password=hashed_password)
    if user_id is None:
        logger.error(f"Failed to add user '{user_data.email}' to DB.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create user due to a server error."
        )

    # Fetch the created user to return public data (without password hash)
    created_user = database.get_user_by_id(user_id)
    if not created_user:
         logger.error(f"Could not retrieve user {user_id} immediately after creation.")
         raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve created user."
        )
    logger.info(f"User '{user_data.email}' registered successfully with ID: {user_id}")
    # Use Pydantic model for response validation and structure
    return UserPublic(**created_user)


@app.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """Provides a JWT token for valid username (email) and password (form data)."""
    logger.info(f"Login attempt for user: {form_data.username}") # username field holds email
    user = database.get_user_by_email(form_data.username)
    if not user or not security.verify_password(form_data.password, user["hashed_password"]):
        logger.warning(f"Login failed for user: {form_data.username} - Incorrect email or password.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Identity for the token ('sub' claim = subject = user ID)
    access_token_data = {"sub": str(user["id"])}
    access_token = security.create_access_token(data=access_token_data)
    logger.info(f"Login successful for user: {form_data.username}. Token issued.")
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/users/me", response_model=UserPublic)
async def read_users_me(current_user: dict = Depends(get_current_active_user)):
    """Returns the data for the currently authenticated user."""
    logger.info(f"Access to /users/me by user ID: {current_user.get('id')}")
    # The dependency already fetched the user dict.
    # Return it, relying on the UserPublic model for filtering/validation.
    return UserPublic(**current_user)

# --- Existing Chatbot/Explanation Endpoints (Unaffected by Auth for now) ---

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(payload: ChatMessage):
    """Handles receiving a chat message and returning the AI's reply."""
    logger.info(f"--- Entering /chat endpoint ---")
    # ... (keep existing implementation, session handling, LLM calls) ...
    # This endpoint remains public for now.
    logger.info(f"Received chat message for session: {payload.session_id}")

    if not llm_handler:
        logger.error("LLM Handler not initialized during chat request.")
        raise HTTPException(status_code=503, detail="Service Unavailable: LLM Handler not ready.")
    if not system_prompt:
        logger.error("System prompt not loaded during chat request.")
        raise HTTPException(status_code=500, detail="Server error: System prompt unavailable.")

    session_id = payload.session_id
    user_message = payload.message

    chat_session = None
    if session_id and session_id in chat_sessions_store:
        logger.info(f"Using existing chat session: {session_id}")
        chat_session = chat_sessions_store[session_id]
    else:
        logger.info("No valid session ID provided or found, creating new session.")
        session_id = str(uuid.uuid4())
        try:
            formatted_system_prompt = system_prompt.format(
                 learned_vocabulary="\n".join(learned_sentences[-20:]) # Example
            )
            chat_session = llm_handler.create_chat_session(formatted_system_prompt)
            if not chat_session:
                 raise Exception("LLM Handler failed to return a valid chat session object.")
            chat_sessions_store[session_id] = chat_session
            logger.info(f"New chat session created with ID: {session_id}")
        except Exception as e:
            logger.error(f"Failed to create new chat session: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Server error: Could not create chat session.")

    if chat_session is None:
         logger.error(f"Critical: chat_session is None for session {session_id} before sending message.")
         raise HTTPException(status_code=500, detail="Internal Server Error: Chat session invalid")

    try:
        logger.info(f"Sending message to LLM for session {session_id}...")
        ai_reply = await llm_handler.send_chat_message(chat_session, user_message)
        logger.info(f"Received reply from LLM for session {session_id}")

        if ai_reply is None or ai_reply.startswith("(Response blocked"):
            logger.warning(f"LLM Handler returned None/blocked for session: {session_id}. Reply: {ai_reply}")
            ai_reply = ai_reply or "(Sorry, the AI did not provide a response. Please try again.)"

        return ChatResponse(reply=ai_reply, session_id=session_id)

    except Exception as e:
        logger.error(f"Error during LLM call in /chat for session {session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error generating chat response: {e}")


@app.post("/explain", response_model=ExplainResponse)
async def explain_endpoint(explain_request: ExplainRequest):
    """Handles receiving a query for explanation. Returns structured JSON."""
    logger.info(f"--- Entering /explain endpoint ---")
    # ... (keep existing implementation, prompt formatting, LLM call, JSON parsing) ...
    # This endpoint remains public for now.
    topic_requested = explain_request.topic
    logger.info(f"Received explanation request for topic: '{topic_requested}'")

    if not llm_handler:
        logger.error("LLM Handler not initialized.")
        raise HTTPException(status_code=503, detail="Service Unavailable: LLM Handler not ready.")
    if not teacher_prompt:
         logger.error("Teacher prompt not loaded.")
         raise HTTPException(status_code=500, detail="Server error: Teacher prompt unavailable.")

    try:
        formatted_prompt = teacher_prompt.format(
            topic=topic_requested,
            context=explain_request.context or "No specific chat context provided."
        )
        logger.info("Formatted prompt prepared for LLM.")
    except KeyError as e:
         logger.error(f"KeyError during teacher_prompt.format(): Missing key {e}.")
         raise HTTPException(status_code=500, detail=f"Server config error: Prompt key error {e}")
    except Exception as e:
         logger.error(f"Error during prompt formatting: {e}", exc_info=True)
         raise HTTPException(status_code=500, detail="Server error formatting prompt.")

    try:
        logger.info(f"Sending explanation request to LLM for '{topic_requested}'...")
        llm_response_text = await llm_handler.generate_one_off(formatted_prompt)
        logger.info(f"Received raw explanation response from LLM Handler.")

        if not llm_response_text or llm_response_text.startswith("(Response blocked"):
            logger.warning(f"LLM response empty or blocked for topic '{topic_requested}'. Response: {llm_response_text}")
            raise HTTPException(status_code=502, detail=f"AI response was empty or blocked: {llm_response_text}")

        try:
            response_text_cleaned = llm_response_text.strip()
            if response_text_cleaned.startswith("```json"):
                response_text_cleaned = response_text_cleaned[7:-3].strip()
            elif response_text_cleaned.startswith("```"):
                 response_text_cleaned = response_text_cleaned[3:-3].strip()
            elif response_text_cleaned.startswith("`"):
                 response_text_cleaned = response_text_cleaned[1:-1].strip()

            parsed_data = json.loads(response_text_cleaned)
            logger.info("Successfully parsed JSON response from LLM.")

            if "explanation_text" not in parsed_data:
                logger.error(f"LLM JSON response missing 'explanation_text'. Raw: {llm_response_text}")
                raise ValueError("LLM response missing required 'explanation_text' key.")

            explanation_text = parsed_data["explanation_text"]
            examples = parsed_data.get("examples", [])

            first_example_spanish = None
            first_example_english = None

            if isinstance(examples, list) and len(examples) > 0:
                first_example = examples[0]
                if isinstance(first_example, dict) and "spanish" in first_example and "english" in first_example:
                    first_example_spanish = first_example["spanish"]
                    first_example_english = first_example["english"]
                    logger.info("Extracted first example sentence pair.")
                else:
                    logger.warning(f"First item in 'examples' list has incorrect format: {first_example}. Raw: {llm_response_text}")
            else:
                 logger.info("No valid examples provided in 'examples' list.")

            return ExplainResponse(
                explanation_text=explanation_text,
                topic=topic_requested,
                example_spanish=first_example_spanish,
                example_english=first_example_english
            )

        except json.JSONDecodeError as json_err:
            logger.error(f"Failed to parse JSON from LLM response in /explain: {json_err}")
            logger.error(f"LLM Raw Response was: {llm_response_text}")
            raise HTTPException(status_code=500, detail="Failed to parse explanation structure from AI.")
        except ValueError as val_err:
             logger.error(f"LLM JSON response validation error in /explain: {val_err}")
             logger.error(f"LLM Raw Response was: {llm_response_text}")
             raise HTTPException(status_code=500, detail=f"Invalid explanation structure from AI: {val_err}")
        except Exception as e:
             logger.error(f"Unexpected error processing LLM response: {e}", exc_info=True)
             raise HTTPException(status_code=500, detail="Server error processing AI response.")

    except HTTPException as http_exc: raise http_exc
    except Exception as e:
        logger.error(f"Error during LLM call in /explain for topic '{topic_requested}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error generating explanation: {e}")


# --- Interactive Flashcard Endpoints ---
# NOTE: These will need authentication (Depends(get_current_active_user)) added in Phase 1

@app.post("/propose_sentence", response_class=JSONResponse)
# async def propose_sentence_endpoint(request_data: ProposeSentenceRequest): # <<< Add Auth Later
async def propose_sentence_endpoint(request_data: ProposeSentenceRequest, current_user: dict = Depends(get_current_active_user)): # <<< TEMPORARY: Added Auth Now
    """
    Proposes a simple Spanish sentence using the target word.
    Requires authentication.
    """
    logger.info(f"--- Entering /propose_sentence endpoint by User ID: {current_user.get('id')} ---")
    logger.info(f"Received sentence proposal request for word: '{request_data.target_word}'")
    # ... (keep existing implementation: check LLM, format prompt, call LLM, parse JSON) ...
    if not llm_handler: raise HTTPException(status_code=503, detail="LLM Handler not initialized.")
    if not sentence_proposer_prompt: raise HTTPException(status_code=500, detail="Sentence proposer prompt not loaded.")

    target_word = request_data.target_word
    formatted_prompt = sentence_proposer_prompt.format(target_word=target_word)

    try:
        logger.info(f"Sending proposal request to LLM for '{target_word}'...")
        response_text = await llm_handler.generate_one_off(formatted_prompt)
        logger.info(f"Received proposal response from LLM.")

        if not response_text or response_text.startswith("(Response blocked"):
             logger.error(f"LLM returned empty/blocked response for sentence proposal. Response: {response_text}")
             raise HTTPException(status_code=500, detail=f"AI returned an empty or blocked response: {response_text}")

        try:
            response_text_cleaned = response_text.strip()
            if response_text_cleaned.startswith("```json"):
                response_text_cleaned = response_text_cleaned[7:-3].strip()
            elif response_text_cleaned.startswith("```"):
                 response_text_cleaned = response_text_cleaned[3:-3].strip()
            elif response_text_cleaned.startswith("`"):
                 response_text_cleaned = response_text_cleaned[1:-1].strip()

            response_data = json.loads(response_text_cleaned)

            if "proposed_spanish" not in response_data or "proposed_english" not in response_data:
                 logger.error(f"LLM response missing required keys (propose). Raw: {response_text}")
                 raise ValueError("LLM response missing required keys (proposed_spanish, proposed_english).")

            response_data["target_word"] = target_word
            return JSONResponse(content=response_data)

        except json.JSONDecodeError as json_err:
            logger.error(f"Failed to parse JSON (propose): {json_err}. Raw: {response_text}")
            raise HTTPException(status_code=500, detail="Failed to parse sentence proposal from AI.")
        except ValueError as val_err:
             logger.error(f"LLM response validation error (propose): {val_err}. Raw: {response_text}")
             raise HTTPException(status_code=500, detail=f"Invalid sentence proposal format from AI: {val_err}")

    except HTTPException as http_exc: raise http_exc
    except Exception as e:
        logger.error(f"Error during LLM call (propose): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error proposing sentence: {e}")


@app.post("/validate_translate_sentence", response_class=JSONResponse)
# async def validate_translate_sentence_endpoint(request_data: ValidateTranslateRequest): # <<< Add Auth Later
async def validate_translate_sentence_endpoint(request_data: ValidateTranslateRequest, current_user: dict = Depends(get_current_active_user)): # <<< TEMPORARY: Added Auth Now
    """
    Validates/corrects ('es') or translates ('en') the sentence using LLM.
    Requires authentication.
    """
    logger.info(f"--- Entering /validate_translate_sentence endpoint by User ID: {current_user.get('id')} ---")
    logger.info(f"Received validation/translation request for word: '{request_data.target_word}'")
    # ... (keep existing implementation: check LLM, format prompt, call LLM, parse JSON) ...
    if not llm_handler: raise HTTPException(status_code=503, detail="LLM Handler not initialized.")
    if not sentence_validator_prompt: raise HTTPException(status_code=500, detail="Sentence validator prompt not loaded.")

    formatted_prompt = sentence_validator_prompt.format(
        target_word=request_data.target_word,
        user_sentence=request_data.user_sentence,
        language=request_data.language
    )

    try:
        logger.info(f"Sending validation/translation request to LLM...")
        response_text = await llm_handler.generate_one_off(formatted_prompt)
        logger.info(f"Received validation/translation response from LLM.")

        if not response_text or response_text.startswith("(Response blocked"):
             logger.error(f"LLM returned empty/blocked response for validation/translation. Response: {response_text}")
             raise HTTPException(status_code=500, detail=f"AI returned an empty or blocked response: {response_text}")

        try:
            response_text_cleaned = response_text.strip()
            if response_text_cleaned.startswith("```json"):
                response_text_cleaned = response_text_cleaned[7:-3].strip()
            elif response_text_cleaned.startswith("```"):
                 response_text_cleaned = response_text_cleaned[3:-3].strip()
            elif response_text_cleaned.startswith("`"):
                 response_text_cleaned = response_text_cleaned[1:-1].strip()

            response_data = json.loads(response_text_cleaned)

            required_keys = ["final_spanish", "final_english", "is_valid", "feedback"]
            missing_keys = [key for key in required_keys if key not in response_data]
            if missing_keys:
                logger.error(f"LLM response missing required keys (validate): {missing_keys}. Raw: {response_text}")
                raise ValueError(f"LLM response missing required keys: {missing_keys}")

            if not isinstance(response_data.get("is_valid"), bool):
                 valid_str = str(response_data.get("is_valid")).lower()
                 if valid_str == 'true': response_data['is_valid'] = True
                 elif valid_str == 'false': response_data['is_valid'] = False
                 else: raise ValueError("LLM response 'is_valid' key is not a boolean.")

            return JSONResponse(content=response_data)

        except json.JSONDecodeError as json_err:
            logger.error(f"Failed to parse JSON (validate): {json_err}. Raw: {response_text}")
            raise HTTPException(status_code=500, detail="Failed to parse sentence validation/translation from AI.")
        except ValueError as val_err:
             logger.error(f"LLM response validation error (validate): {val_err}. Raw: {response_text}")
             raise HTTPException(status_code=500, detail=f"Invalid validation/translation format from AI: {val_err}")

    except HTTPException as http_exc: raise http_exc
    except Exception as e:
        logger.error(f"Error during LLM call (validate): {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error validating/translating sentence: {e}")


@app.post("/save_final_card", response_class=JSONResponse)
# async def save_final_card_endpoint(request_data: SaveCardRequest): # <<< Add Auth Later
async def save_final_card_endpoint(request_data: SaveCardRequest, current_user: dict = Depends(get_current_active_user)): # <<< PHASE 1 Target: Needs Auth
    """
    Saves the final Spanish front, English back, and tags for a new card
    to the database, associated with the logged-in user.
    Requires authentication.
    """
    user_id = current_user.get("id")
    logger.info(f"--- Entering /save_final_card endpoint by User ID: {user_id} ---")
    logger.info(f"Received request to save final card. Front: '{request_data.spanish_front[:30]}...'")
    try:
        # Update database function call to include user_id
        card_id = database.add_new_card_to_db(
            user_id=user_id, # <<< Pass user_id
            front=request_data.spanish_front,
            back=request_data.english_back,
            tags=request_data.tags
        )
        if card_id:
            logger.info(f"Successfully saved new card to DB with ID: {card_id} for User ID: {user_id}")
            return JSONResponse(content={"success": True, "card_id": card_id, "message": "Card saved to database."})
        else:
            logger.error(f"Failed to save card to database for user {user_id}, add_new_card_to_db returned None.")
            # Check database.py logic for why None might be returned (e.g., DB error not caught?)
            raise HTTPException(status_code=500, detail="Failed to save card to database. Check server logs.")

    except Exception as e:
        logger.error(f"Error saving card to database for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Database error saving card: {e}")


# --- Anki Sync Endpoints (Consider removing or heavily adapting later) ---
# These are less relevant now we're building an integrated SRS.
# They also need authentication if kept/adapted.

@app.post("/sync_anki_deck")
async def sync_anki_deck_endpoint(payload: AnkiDeckUpdateRequest):
    """(Likely Deprecated) Receives sentences from Anki plugin."""
    global learned_sentences
    logger.warning(f"--- Endpoint /sync_anki_deck accessed (potentially deprecated) ---")
    logger.info(f"Received sync_anki_deck request with {len(payload.sentences)} sentences.")
    learned_sentences = payload.sentences # Still update global for potential use by /chat?
    return {"message": f"Updated learned sentences list.", "success": True}


@app.get("/get_new_chatbot_cards", response_model=GetNewCardsResponse)
# async def get_new_chatbot_cards_endpoint(): # <<< Add Auth Later if needed
async def get_new_chatbot_cards_endpoint(current_user: dict = Depends(get_current_active_user)): # <<< Needs Auth if kept
    """(Likely Deprecated/Needs Change) Provides pending cards for Anki plugin."""
    user_id = current_user.get("id")
    logger.warning(f"--- Endpoint /get_new_chatbot_cards accessed by User ID {user_id} (potentially deprecated) ---")
    try:
        # Update database function to filter by user_id AND status='pending'
        # cards = database.get_pending_cards_for_user(user_id) # <<< Example modification needed in database.py
        cards = database.get_pending_cards(user_id=user_id) # <<< Assuming get_pending_cards is updated
        logger.info(f"Returning {len(cards)} pending cards for user {user_id}.")
        return GetNewCardsResponse(cards=cards)
    except Exception as e:
        logger.error(f"Database error retrieving pending cards for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve pending cards from database.")


@app.post("/mark_cards_synced", response_class=JSONResponse)
# async def mark_cards_synced_endpoint(payload: MarkSyncedRequest): # <<< Add Auth Later if needed
async def mark_cards_synced_endpoint(payload: MarkSyncedRequest, current_user: dict = Depends(get_current_active_user)): # <<< Needs Auth if kept
    """(Likely Deprecated/Needs Change) Marks cards as synced for Anki."""
    user_id = current_user.get("id")
    logger.warning(f"--- Endpoint /mark_cards_synced accessed by User ID {user_id} (potentially deprecated) ---")
    card_ids = payload.card_ids
    if not card_ids:
        return JSONResponse(content={"success": True, "message": "No card IDs provided."}, status_code=200)

    logger.info(f"Received request from user {user_id} to mark {len(card_ids)} cards as synced: {card_ids}")
    try:
        # Update database function to ensure cards belong to the user before marking
        # success = database.mark_cards_as_synced_for_user(user_id, card_ids) # <<< Example modification
        success = database.mark_cards_as_synced(card_ids, user_id=user_id) # <<< Assuming updated function
        if success:
            logger.info(f"Marking cards {card_ids} for user {user_id} reported successful.")
            return JSONResponse(content={"success": True, "message": f"Successfully marked {len(card_ids)} cards as synced."})
        else:
            logger.warning(f"Marking cards {card_ids} failed for user {user_id}.")
            # May fail if cards don't exist, don't belong to user, or DB error
            return JSONResponse(content={"success": False, "message": f"Failed to mark {len(card_ids)} cards as synced. Check logs/permissions."}, status_code=400) # 400 or 500 depending on cause
    except Exception as e:
        logger.error(f"Error during /mark_cards_synced for user {user_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Server error while updating card statuses.")


# --- Serve Static Files ---
# Option 1: Keep serving old static files for now
# app.mount("/static", StaticFiles(directory="static"), name="static")
# @app.get("/", response_class=HTMLResponse)
# async def get_index_legacy(request: Request):
#     logger.info("Serving legacy index.html from /")
#     index_path = os.path.join("static", "index.html")
#     if not os.path.exists(index_path):
#          raise HTTPException(status_code=404, detail="Legacy index.html not found")
#     return FileResponse(index_path)

# Option 2: Prepare to serve the Vue app build output (RECOMMENDED for later)
# You will run `npm run build` in the frontend directory, creating a `dist` folder.
# Point StaticFiles to that `dist` folder. The `index.html` within it handles routing.
vue_app_build_dir = os.path.join("..", "frontend", "dist") # Adjust path as needed

# Check if Vue build exists, otherwise fallback or raise error
if os.path.exists(vue_app_build_dir):
    logger.info(f"Vue app build directory found at: {vue_app_build_dir}")
    app.mount("/assets", StaticFiles(directory=os.path.join(vue_app_build_dir, "assets")), name="vue-assets")

    @app.get("/{full_path:path}", response_class=HTMLResponse)
    async def serve_vue_app(request: Request, full_path: str):
        """Serves the Vue app's index.html for any non-API path."""
        index_path = os.path.join(vue_app_build_dir, "index.html")
        logger.info(f"Serving Vue app index.html for path: /{full_path}")
        if not os.path.exists(index_path):
            logger.error(f"Vue index.html not found at {index_path}")
            raise HTTPException(status_code=404, detail="Application not found.")
        return FileResponse(index_path)
else:
    logger.warning(f"Vue app build directory NOT found at {vue_app_build_dir}. Serving API only.")
    # Add a simple root endpoint if no static files are served
    @app.get("/")
    async def read_root():
        return {"message": "Spanish Learning Chatbot API is running. Frontend not found."}


# --- Main Execution Guard (for local testing) ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000)) # Default to 8000 for local dev
    logger.info(f"Starting Uvicorn server locally on http://0.0.0.0:{port} with reload enabled")
    # Note: Cloud Run uses its own web server (like Gunicorn) and manages the port via $PORT env var.
    # The reload=True flag is only for local development.
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=True)