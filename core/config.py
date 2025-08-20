import os
from dotenv import load_dotenv
load_dotenv() # Load environment variables from .env file for local dev

class Settings:
    #################################################################################################
    ############################## CORE Configuration ###########################################
    #################################################################################################
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") 
    if not GEMINI_API_KEY:
        print("\n" + "*"*60)
        print("ERROR: GEMINI_API_KEY environment variable not set.")
        print("       The application requires a valid Gemini API key to function.")
        print("*"*60 + "\n")
    WEB_APP_BASE_URL = os.getenv("WEB_APP_BASE_URL", "http://localhost:5173")
    GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-1.5-flash-latest")
    




    #################################################################################################
    ############################## SECURITY Configuration ###########################################
    #################################################################################################
    AUTH_MASTER_KEY = os.getenv("AUTH_MASTER_KEY")
    ALGORITHM = "HS256" # JWT algorithm
    ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCSS_TOKEN_EXPIRE_MINUTES", 42000)) # Access token lifetime
    






    
    #################################################################################################
    ############################## SYSTEM PROMPTS Configuration #####################################
    #################################################################################################
    PROMPT_DIR = "system_prompts"
    SYSTEM_PROMPT_TEMPLATE = os.path.join(PROMPT_DIR, "system_prompt_template.txt")
    TEACHER_PROMPT_TEMPLATE = os.path.join(PROMPT_DIR, "teacher_prompt_template.txt")
    SENTENCE_PROPOSER_PROMPT = os.path.join(PROMPT_DIR, "sentence_proposer_prompt.txt")
    SENTENCE_VALIDATOR_PROMPT = os.path.join(PROMPT_DIR, "sentence_validator_prompt.txt")
    







    #################################################################################################
    ############################## SRS (FLASHCARD LEARNING) Configuration ###########################
    #################################################################################################
    LEARNING_STEPS_MINUTES: list[int] = [1, 10] # Intervals in minutes for learning phase
    DEFAULT_EASY_INTERVAL_DAYS: float = 4.0   # Initial interval (days) after graduating or 'easy' on new
    DEFAULT_EASE_FACTOR: float = 2.5          # Starting ease factor for new cards (Anki default)
    MIN_EASE_FACTOR: float = 1.3              # Minimum ease factor allowed
    LAPSE_INTERVAL_MULTIPLIER: float = 0.0    # Interval multiplier on 'again' (0=reset to learning steps)
    DEFAULT_INTERVAL_MODIFIER: float = 1.0    # Base multiplier for 'good' reviews (adjust as needed, 1.0 is neutral)
    EASY_BONUS: float = 1.3                   # Extra multiplier for 'easy' reviews (Anki default)







    #################################################################################################
    ############################## Database Configuration ###########################################
    #################################################################################################

     # production: load connection string, stored in secret manager, passed through production environment variables
    CONNECT_LOCALLY_TO_SUPABASE: str | None=os.getenv("CONNECT_LOCALLY_TO_SUPABASE")
    DATABASE_URL_PROD: str | None = os.getenv("DATABASE_URL_PROD")
    database_url: str| None = None
    if  DATABASE_URL_PROD:
        database_url = DATABASE_URL_PROD
    
    # local development: connect to supabase
    elif CONNECT_LOCALLY_TO_SUPABASE:
        SUPABASE_DATABASE_URL_IPV4: str|None = os.getenv("SUPABASE_DATABASE_URL_IPV4")
        if SUPABASE_DATABASE_URL_IPV4:
            database_url= SUPABASE_DATABASE_URL_IPV4
        
    else:
        # connect to locally hosted database
        DB_USER=os.getenv("DB_USER")
        DB_PASSWORD=os.getenv("DB_PASSWORD")
        DB_SERVER=os.getenv("DB_SERVER", "localhost")
        DB_PORT=os.getenv("DB_PORT", "5432") 
        DB_NAME=os.getenv("DB_NAME", "ankixparlai")
        database_url = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_SERVER}:{DB_PORT}/{DB_NAME}"

    DATABASE_URL = database_url



settings = Settings()