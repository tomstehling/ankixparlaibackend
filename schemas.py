from pydantic import BaseModel, Field, EmailStr, field_validator
from typing import Optional, List, Dict, Any, Union
from typing import Literal # For grade type
import datetime # Import datetime for proper type hint if needed
import json # For optional validator

# --- User Models ---
class UserBase(BaseModel):
    email: EmailStr

class UserCreate(UserBase):
    password: str

class UserLogin(UserBase):
    password: str

class UserPublic(UserBase):
    id: int
    email: EmailStr # Make sure email is included here
    whatsapp_number: Optional[str] = None # Include linked number if available
    created_at: Optional[datetime.datetime] = None
    class Config:
        from_attributes = True # Updated from orm_mode=True for Pydantic v2

# --- Token Models ---
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    user_id: Union[int, None] = None

# --- /chat endpoint models ---
class ChatMessage(BaseModel):
    id: int
    user_id: int
    session_id: str
    role: str
    content: str
    timestamp: datetime.datetime
    message_type: Optional[str]=None

class ChatMessageCreate(BaseModel):
    user_id: int
    session_id: str
    role: str
    content: str
    message_type: Optional[str]=None

    

class ExplainRequest(BaseModel):
    topic: str
    context: Optional[str] = None

# --- Define Response Models (Matching Frontend Expectation) ---
class ExamplePair(BaseModel):
    """Represents a single Spanish/English example pair."""
    spanish: str
    english: str

class ExplainResponse(BaseModel):
    """Structured response for an explanation."""
    topic: str
    explanation_text: str # This should contain ONLY the text part
    examples: Optional[List[ExamplePair]] = None # List of examples or None


# --- Interactive Card Creation Models ---
class ProposeSentenceRequest(BaseModel):
    target_word: str = Field(..., examples=["correr"])

class ValidateTranslateRequest(BaseModel):
    target_word: str = Field(..., examples=["libro"])
    user_sentence: str = Field(..., examples=["Quiero leer un libro.", "I want to read a book."])
    language: Literal['es', 'en'] = Field(..., examples=["es", "en"])

class SaveCardRequest(BaseModel):
    spanish_front: str = Field(..., examples=["Me gusta el perro."])
    english_back: str = Field(..., examples=["I like the dog."])
    tags: List[str] = Field(default_factory=list, examples=[["vocabulario", "chatbot"]])



# --- SRS / Card Models ---
class CardGradeRequest(BaseModel):
    grade: Literal['again', 'good', 'easy']

class SRS(BaseModel):
    status: str
    due_timestamp: int
    interval_days: float
    ease_factor: float
    learning_step: int
    class Config:
         from_attributes = True 


# Model for returning card details, including SRS info
class CardPublic(BaseModel):
     id: int
     user_id: int
     front: str
     back: str
     tags: Optional[str] = None 
     
     created_at: Optional[datetime.datetime] = None 
     srs: SRS
     class Config:
         from_attributes = True 

class NoteContent(BaseModel):
    field1: str # e.g., Spanish
    field2: str # e.g., English
    tags: Optional[str] = None # DB stores as space-separated string
    created_at: Optional[datetime.datetime] = None

class NotePublic(BaseModel):
    id: int
    user_id: int
    note_data: NoteContent
    model_config = { # Pydantic v2 config
        "from_attributes": True
    }
   


class DueCardResponseItem(BaseModel):
    card_id: int # Specific ID of the card to be reviewed/graded
    note_id: int
    user_id: int
    direction: int # 0 for forward (field1->field2), 1 for reverse (field2->field1)
    srs: SRS # SRS info for the card
    field1: str # Content from the joined note table
    field2: str # Content from the joined note table
    tags: Optional[str] = None # Tags from the joined note table
    note_created_at: Optional[datetime.datetime] = None

    model_config = { # Pydantic v2 config
        "from_attributes": True
    }
   


class DueCardsResponse(BaseModel):
    cards: List[DueCardResponseItem]

# Optional: Rename CardUpdate to NoteUpdate for clarity, or keep as is and map fields
class NoteUpdate(BaseModel):
    field1: Optional[str] = None
    field2: Optional[str] = None
    tags: Optional[List[str]] = None # Keep accepting list, convert in endpoint/db func




# --- WhatsApp Linking Model ---
class WhatsappLinkCodeResponse(BaseModel):
    """Response model containing the generated WhatsApp link code."""
    link_code: str = Field(..., examples=["LINK 123456"], description="The full code (prefix + numbers) to send via WhatsApp.")
    expires_in_seconds: int = Field(..., examples=[300], description="Number of seconds the code is valid for.")

class AnkiImportSummary(BaseModel):
    imported_count: int
    skipped_count: int # For future use (e.g., duplicates)
    error_count: int
    error_message: Optional[str] = None

class QuickAddRequest(BaseModel):
    topic: str
    context: Optional[str] = None

class QuickAddResponse(BaseModel):
    """Response model for quick add operation."""
    success: bool
    message: str = Field(..., examples=["Word added successfully."])
    note_id: Optional[int] = Field(None, examples=[1], description="ID of the added word, if applicable.")
    user_id: int = Field(..., examples=[1], description="ID of the user")
    field1: str = Field(..., examples=["perro"])
    field2: str = Field(..., examples=["dog"])
    created_at: Optional[datetime.datetime] = None
    
