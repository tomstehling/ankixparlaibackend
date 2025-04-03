# models.py

from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List, Dict, Any

# --- User Models ---
class UserBase(BaseModel):
    email: EmailStr # Use EmailStr for basic email format validation

class UserCreate(UserBase):
    password: str # Password will be handled by backend logic (hashing)

class UserLogin(UserBase): # Often same as UserBase + password, but separate for clarity
    password: str

class UserPublic(UserBase):
    id: int
    # Add any other non-sensitive fields you might want to expose about a user
    # email: EmailStr # Already inherited from UserBase

    class Config:
        orm_mode = True # Helps Pydantic work with ORM objects if needed later


# --- Token Models ---
class Token(BaseModel):
    access_token: str
    token_type: str # Typically "bearer"

class TokenData(BaseModel):
    # Represents the data encoded within the JWT token's payload
    # 'sub' (subject) is standard for user identifier
    user_id: Optional[int] = None # Match the type of your user ID (int)


# --- /chat endpoint models ---
class ChatMessage(BaseModel):
    message: str
    session_id: Optional[str] = None # Allow frontend to maintain session

class ChatResponse(BaseModel):
    reply: str
    session_id: str # Send back session ID (new or existing)


# --- /explain endpoint models ---
class ExplainRequest(BaseModel):
    topic: str
    context: Optional[str] = None # Optional chat context

class ExplainResponse(BaseModel):
    explanation_text: str             # The main explanation text
    topic: str                        # The original topic requested (useful for frontend)
    example_spanish: Optional[str] = None # Optional first example sentence (Spanish)
    example_english: Optional[str] = None # Optional first example sentence (English)


# --- Interactive Card Creation Models ---
class ProposeSentenceRequest(BaseModel):
    target_word: str = Field(..., examples=["correr"]) # Required field with example

class ValidateTranslateRequest(BaseModel):
    target_word: str = Field(..., examples=["libro"])
    user_sentence: str = Field(..., examples=["Quiero leer un libro.", "I want to read a book."])
    # Use Literal type for stricter validation ('es' or 'en' only)
    # from typing import Literal
    # language: Literal['es', 'en'] = Field(...)
    language: str = Field(..., pattern="^(es|en)$", examples=["es", "en"]) # Regex pattern works too

class SaveCardRequest(BaseModel):
    spanish_front: str = Field(..., examples=["Me gusta el perro."])
    english_back: str = Field(..., examples=["I like the dog."])
    tags: List[str] = Field(default_factory=list, examples=[["vocabulario", "chatbot"]]) # Default to empty list


# --- Anki Sync Models (Potentially Deprecated/Needs Change) ---
class AnkiDeckUpdateRequest(BaseModel):
    sentences: List[str]

class GetNewCardsResponse(BaseModel):
    # Define the structure of a card as returned by the API
    class CardDetail(BaseModel):
        id: int
        front: str
        back: str
        tags: str # Or List[str] depending on how DB stores/returns it
        # Add other fields like 'status' if needed by Anki plugin
        # status: str

    cards: List[CardDetail] # List of card dictionaries/objects

class MarkSyncedRequest(BaseModel):
    card_ids: List[int]