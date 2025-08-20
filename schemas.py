import uuid
import datetime
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List, Union
from typing import Literal

class UserBase(BaseModel):
    email: EmailStr

class UserCreate(UserBase):
    password: str

class UserLogin(UserBase):
    password: str

class UserPublic(UserBase):
    id: uuid.UUID
    email: EmailStr
    created_at: Optional[datetime.datetime] = None
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    user_id: Union[uuid.UUID, None] = None

class ChatMessage(BaseModel):
    id: int
    user_id: uuid.UUID
    session_id: str
    role: str
    content: str
    timestamp: datetime.datetime
    message_type: Optional[str] = None

class ChatMessageCreate(BaseModel):
    user_id: uuid.UUID
    session_id: str
    role: str
    content: str
    message_type: Optional[str] = None

class ExplainRequest(BaseModel):
    topic: str
    context: Optional[str] = None

class ExamplePair(BaseModel):
    spanish: str
    english: str

class ExplainResponse(BaseModel):
    topic: str
    explanation_text: str
    examples: Optional[List[ExamplePair]] = None

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

class CardGradeRequest(BaseModel):
    grade: Literal['again', 'good', 'easy']
    timezone: str = Field(default="Europe/Berlin", description="User's IANA timezone identifier, e.g., 'America/New_York'")

class SRS(BaseModel):
    status: str
    due_timestamp: int
    interval_days: float
    ease_factor: float
    learning_step: int
    class Config:
        from_attributes = True

class CardPublic(BaseModel):
    id: int
    user_id: uuid.UUID
    front: str
    back: str
    tags: Optional[str] = None
    created_at: Optional[datetime.datetime] = None
    srs: SRS
    class Config:
        from_attributes = True

class NoteContent(BaseModel):
    field1: str
    field2: str
    tags: Optional[List[str]] = None
    created_at: Optional[datetime.datetime] = None

class NotePublic(BaseModel):
    id: int
    user_id: uuid.UUID
    note_content: NoteContent
    model_config = {
        "from_attributes": True
    }

class DueCardResponseItem(BaseModel):
    card_id: int
    note_id: int
    user_id: uuid.UUID
    direction: int
    srs: SRS
    note_content: NoteContent
    model_config = {
        "from_attributes": True
    }

class DueCardsResponse(BaseModel):
    cards: List[DueCardResponseItem]

class AnkiImportSummary(BaseModel):
    imported_count: int
    skipped_count: int
    error_count: int
    error_message: Optional[str] = None

class QuickAddRequest(BaseModel):
    topic: str
    context: Optional[str] = None

class QuickAddResponse(BaseModel):
    success: bool
    message: str = Field(..., examples=["Word added successfully."])
    note_id: Optional[int] = Field(None, examples=[1], description="ID of the added word, if applicable.")
    user_id: uuid.UUID = Field(..., examples=["a1b2c3d4-..."], description="ID of the user")
    field1: str = Field(..., examples=["perro"])
    field2: str = Field(..., examples=["dog"])
    created_at: Optional[datetime.datetime] = None

class FeedbackResponse(BaseModel):
    success: bool
    message: str
    timestamp: datetime.datetime

class FeedbackRequest(BaseModel):
    user_id: uuid.UUID
    content: str

class GradeCardResponse(BaseModel):
    success: bool
    message: str
    current_streak: int
    longest_streak: int