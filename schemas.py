# generic api response schema
from pydantic import BaseModel
from typing import TypeVar, Generic, Literal
from pydantic.generics import GenericModel
from fsrs import State  # type: ignore

T = TypeVar("T")


class APIResponse(GenericModel, Generic[T]):
    status: Literal["success", "fail", "error"]
    data: T


# rest of schemas
import uuid
import datetime
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List, Union
from typing import Literal


class FSRSUpdate(BaseModel):
    due: datetime.datetime
    stability: float
    difficulty: float
    state: State
    review_count: int
    lapse_count: int
    last_review: datetime.datetime


class TokenPayload(BaseModel):
    sub: str
    exp: datetime.datetime


class UserAwardsPublic(BaseModel):
    current_streak: int
    longest_streak: int

    class Config:
        from_attributes = True


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
    awards: UserAwardsPublic

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
    user_sentence: str = Field(
        ..., examples=["Quiero leer un libro.", "I want to read a book."]
    )
    language: Literal["es", "en"] = Field(..., examples=["es", "en"])


class SaveCardRequest(BaseModel):
    spanish_front: str = Field(..., examples=["Me gusta el perro."])
    english_back: str = Field(..., examples=["I like the dog."])
    tags: List[str] = Field(default_factory=list, examples=[["vocabulario", "chatbot"]])


class SRS(BaseModel):
    status: str
    due_timestamp: int
    interval_days: float
    ease_factor: float
    learning_step: int


class CardGradeRequest(BaseModel):
    grade: Literal["again", "hard", "good", "easy"]
    timezone: str = Field(
        default="Europe/Berlin",
        description="User's IANA timezone identifier, e.g., 'America/New_York'",
    )


class FSRS(BaseModel):
    due_date: datetime.datetime
    due_timestamp: int
    stability: Optional[float]
    difficulty: Optional[float]
    last_review: Optional[datetime.datetime]
    state: int
    status: str
    review_count: int
    lapse_count: int
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
    fsrs: FSRS

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
    created_at: Optional[datetime.datetime] = None
    model_config = {"from_attributes": True}


class FetchNotesResponse(BaseModel):
    notes: List[NotePublic]


class DueCardResponseItem(BaseModel):
    card_id: int
    note_id: int
    user_id: uuid.UUID
    created_at: Optional[datetime.datetime] = None
    direction: int
    fsrs: FSRS
    note_content: NoteContent
    model_config = {"from_attributes": True}


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
    note_id: Optional[int] = Field(
        None, examples=[1], description="ID of the added word, if applicable."
    )
    user_id: uuid.UUID = Field(
        ..., examples=["a1b2c3d4-..."], description="ID of the user"
    )
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


class CreateFromTopicRequest(BaseModel):
    topic: str
    custom_instructions: Optional[str] = None
    card_amount: int


class CreateFromTextRequest(BaseModel):
    text: str
    custom_instructions: Optional[str] = None


class StudioCard(BaseModel):
    front: str
    back: str
    tags: List[str]


class LLMStudioResponse(BaseModel):
    cards: List[StudioCard]


class TranslateRequest(BaseModel):
    text: str
    translation_mode: Literal["standard", "smart"] = "standard"


class TranslateResponse(BaseModel):
    translation: NoteContent
    translation_type: Literal["standard", "smart"]
