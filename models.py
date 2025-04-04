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
    class Config:
        from_attributes = True

# --- Token Models ---
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    user_id: Union[int, None] = None

# --- /chat endpoint models ---
class ChatMessage(BaseModel):
    message: str
    session_id: Optional[str] = None

class ChatResponse(BaseModel):
    reply: str
    session_id: str

# --- /explain endpoint models ---
class ExplainRequest(BaseModel):
    topic: str
    context: Optional[str] = None

class ExplainResponse(BaseModel):
    explanation_text: str
    topic: str
    example_spanish: Optional[str] = None
    example_english: Optional[str] = None

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

# --- Anki Sync Models (Deprecated) ---
# ... (keep if needed, otherwise remove)

# --- SRS / Card Models ---
class CardGradeRequest(BaseModel):
    grade: Literal['again', 'good', 'easy']

# Model for returning card details, including SRS info
class CardPublic(BaseModel):
     id: int
     user_id: int
     front: str
     back: str
     tags: Optional[str] = None # DB stores as space-separated string
     status: str
     created_at: Optional[datetime.datetime] = None # Allow None if sometimes missing
     due_timestamp: int
     interval_days: float
     ease_factor: float
     learning_step: Optional[int] = 0

     class Config:
         from_attributes = True


class DueCardsResponse(BaseModel):
    cards: List[CardPublic]


# --- Card Update Model ---
class CardUpdate(BaseModel):
    """Model for updating card front, back, and tags."""
    # Use Optional if you want to allow partial updates, otherwise make them required
    front: Optional[str] = Field(None, examples=["El gato duerme."])
    back: Optional[str] = Field(None, examples=["The cat sleeps."])
    tags: Optional[List[str]] = Field(None, examples=[["animales", "verbos"]])

    # Add validator to ensure at least one field is provided for update? Optional.
    # @field_validator('*') # Check if needed, requires more logic
    # def check_at_least_one_field(cls, values):
    #     if not any(values.values()):
    #         raise ValueError("At least one field (front, back, tags) must be provided for update")
    #     return values