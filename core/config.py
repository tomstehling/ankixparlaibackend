import os
from dotenv import load_dotenv
load_dotenv() # Load environment variables from .env file for local dev

class Settings:
    # --- Core Application Settings ---
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") 
    if not GEMINI_API_KEY:
        print("\n" + "*"*60)
        print("ERROR: GEMINI_API_KEY environment variable not set.")
        print("       The application requires a valid Gemini API key to function.")
        print("*"*60 + "\n")
    WEB_APP_BASE_URL = os.getenv("WEB_APP_BASE_URL", "http://localhost:5173") # Base URL for frontend
    
    # --- Gemini Model Configuration ---
    GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-1.5-flash-latest") # Your preferred model
    
    # --- Security Configuration ---
    AUTH_MASTER_KEY = os.getenv("AUTH_MASTER_KEY", "a_very_bad_default_secret_key_CHANGE_ME")
    ALGORITHM = "HS256" # JWT algorithm
    ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCSS_TOKEN_EXPIRE_MINUTES", 42000)) # Access token lifetime
    
    # --- Prompts ---
    PROMPT_DIR = "system_prompts"
    SYSTEM_PROMPT_TEMPLATE = os.path.join(PROMPT_DIR, "system_prompt_template.txt")
    TEACHER_PROMPT_TEMPLATE = os.path.join(PROMPT_DIR, "teacher_prompt_template.txt")
    SENTENCE_PROPOSER_PROMPT = os.path.join(PROMPT_DIR, "sentence_proposer_prompt.txt")
    SENTENCE_VALIDATOR_PROMPT = os.path.join(PROMPT_DIR, "sentence_validator_prompt.txt")
    
    # --- Spaced Repetition System (SRS) Configuration ---
    LEARNING_STEPS_MINUTES: list[int] = [1, 10] # Intervals in minutes for learning phase
    DEFAULT_EASY_INTERVAL_DAYS: float = 4.0   # Initial interval (days) after graduating or 'easy' on new
    DEFAULT_EASE_FACTOR: float = 2.5          # Starting ease factor for new cards (Anki default)
    MIN_EASE_FACTOR: float = 1.3              # Minimum ease factor allowed
    LAPSE_INTERVAL_MULTIPLIER: float = 0.0    # Interval multiplier on 'again' (0=reset to learning steps)
    DEFAULT_INTERVAL_MODIFIER: float = 1.0    # Base multiplier for 'good' reviews (adjust as needed, 1.0 is neutral)
    EASY_BONUS: float = 1.3                   # Extra multiplier for 'easy' reviews (Anki default)

    # --- Database Configuration ---
    DATABASE_URL_PROD: str | None = os.getenv("DATABASE_URL_PROD")
    if  DATABASE_URL_PROD:
        DATABASE_URL: str = DATABASE_URL_PROD
    else:
        DB_USER=os.getenv("DB_USER")
        DB_PASSWORD=os.getenv("DB_PASSWORD")
        DB_SERVER=os.getenv("DB_SERVER", "localhost")
        DB_PORT=os.getenv("DB_PORT", "5432") 
        DB_NAME=os.getenv("DB_NAME", "ankixparlai")
        DATABASE_URL: str = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_SERVER}:{DB_PORT}/{DB_NAME}"

    ##########################
    ###### Deprecated Start###
    ##########################
     # Optional file for Anki integration (if used by external scripts/sync)
    ANKI_FLASHCARDS_FILE = os.getenv("ANKI_FLASHCARDS_FILE", "flashcards.json")

    # --- Command Triggers ---
    # Command prefix for linking account via WhatsApp
    WHATSAPP_LINK_COMMAND_PREFIX = "LINK"
    # Command prefix for creating flashcards via WhatsApp
    WHATSAPP_CARD_COMMAND_PREFIX = "/"

    # --- AnkiConnect Configuration (Deprecated - Internal SRS used) ---
    ANKICONNECT_URL = os.getenv("ANKICONNECT_URL", "http://localhost:8765") # Default AnkiConnect URL
    ANKI_DECK_NAME = os.getenv("ANKI_DECK_NAME", "ankixparlai") # Target deck name in Anki
    ANKI_MODEL_NAME = os.getenv("ANKI_MODEL_NAME", "Basic (and reversed card)") # Note type in Anki
    ANKI_FIELD_FRONT = os.getenv("ANKI_FIELD_FRONT", "Front") # Field name for the front of the card
    ANKI_FIELD_BACK = os.getenv("ANKI_FIELD_BACK", "Back")   # Field name for the back of the card

    # --- Other Settings ---
    # Temporary storage for WhatsApp link codes. Structure: { "123456": {"user_id": 1, "expires_at": 1678886400.0}, ... }
    # WARNING: In-memory storage is lost on server restart. Use Redis/DB for production.
    TEMP_CODE_STORAGE: dict[str, dict] = {}
    LINK_CODE_EXPIRY_SECONDS = 300 # 5 minutes (300 seconds)
    LINK_CODE_LENGTH = 6 # Number of digits for the link code

    # --- Twilio Configuration ---
    TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
    TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
    TWILIO_WHATSAPP_NUMBER = os.getenv("TWILIO_WHATSAPP_NUMBER") # Your Twilio WhatsApp sender number (e.g., whatsapp:+14155238886)

    # Validate Twilio configuration
    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_NUMBER]):
        print("\n" + "*"*60)
        print("WARNING: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, or TWILIO_WHATSAPP_NUMBER")
        print("         environment variables are not set. WhatsApp integration will fail.")
        print("*"*60 + "\n")
    ##############################
    ##### Deprecated Finish ######
    ##############################


settings = Settings()