import datetime
import uuid
from typing import List, Optional, Dict, Any
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import (
    ForeignKey,
    String,
    Text,
    DateTime,
    Float,
    CheckConstraint,
    Integer,
    SmallInteger,
    Boolean,
    Double,
    func,
    Enum,
    UUID,
    Date,
    ARRAY,
    Table,
    Column,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database.session import Base


# reviewed and approved
class LearningHack(Base):
    __tablename__ = "learning_hacks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    type: Mapped[str] = mapped_column(
        Enum(
            "RULE",
            "MNEMONIC",
            "CONSTRUCTION",
            "PATTERN",
            "DISTINCTION",
            "CONNECTOR",
            name="hack_type_enum",
        ),
        nullable=False,
    )
    cefr_level: Mapped[str] = mapped_column(
        Enum("A1", "A2", "B1", "B2", "C1", "C2", name="cefr_level_enum"), nullable=False
    )
    short_description: Mapped[str] = mapped_column(Text, nullable=False)
    example_front: Mapped[str] = mapped_column(Text, nullable=False)
    example_back: Mapped[str] = mapped_column(Text, nullable=False)
    long_description: Mapped[Optional[str]] = mapped_column(Text)

    hack_to_tag_relationships: Mapped[List["HackToTagRelationship"]] = relationship(
        "HackToTagRelationship", back_populates="hack"
    )


# reviewed and approved
class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False
    )
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    subcategory: Mapped[str] = mapped_column(String(50), nullable=False)
    cefr_level: Mapped[str] = mapped_column(
        Enum("A1", "A2", "B1", "B2", "C1", "C2", name="cefr_level_enum"), nullable=False
    )
    visibility: Mapped[str] = mapped_column(
        Enum("INTERNAL", "BETA", "PUBLIC", name="visibility_enum"),
        nullable=False,
        server_default="INTERNAL",
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(True), nullable=False, server_default=func.now()
    )
    logic_group: Mapped[Optional[str]] = mapped_column(String(50))
    description: Mapped[Optional[str]] = mapped_column(Text)

    lemmas: Mapped[List["VerbLemma"]] = relationship(
        "VerbLemma", secondary="tag_archetype_lemmas", back_populates="tags"
    )
    hack_to_tag_relationships: Mapped[List["HackToTagRelationship"]] = relationship(
        "HackToTagRelationship", back_populates="tag"
    )
    tag_relationships_as_source: Mapped[List["TagRelationship"]] = relationship(
        "TagRelationship",
        foreign_keys="[TagRelationship.source_tag_id]",
        back_populates="source_tag",
    )
    tag_relationships_as_target: Mapped[List["TagRelationship"]] = relationship(
        "TagRelationship",
        foreign_keys="[TagRelationship.target_tag_id]",
        back_populates="target_tag",
    )
    user_tag_scores: Mapped[List["UserTagScore"]] = relationship(
        "UserTagScore", back_populates="tag"
    )
    note_tags: Mapped[List["NoteTag"]] = relationship("NoteTag", back_populates="tag")


# okay
class VerbLemma(Base):
    __tablename__ = "verb_lemmas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lemma: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False
    )

    tags: Mapped[List["Tag"]] = relationship(
        "Tag", secondary="tag_archetype_lemmas", back_populates="lemmas"
    )
    frequent_verb_forms: Mapped[List["FrequentVerbForm"]] = relationship(
        "FrequentVerbForm", back_populates="lemma"
    )


# okay
class FrequentVerbForm(Base):
    __tablename__ = "frequent_verb_forms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lemma_id: Mapped[int] = mapped_column(
        ForeignKey("verb_lemmas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    form: Mapped[str] = mapped_column(String(50), nullable=False)
    is_survival_essential: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    tense: Mapped[Optional[str]] = mapped_column(String(50))
    person: Mapped[Optional[str]] = mapped_column(String(50))
    example: Mapped[Optional[str]] = mapped_column(Text)
    usage_notes: Mapped[Optional[str]] = mapped_column(Text)
    lemma: Mapped["VerbLemma"] = relationship(
        "VerbLemma", back_populates="frequent_verb_forms"
    )


# okay
class HackToTagRelationship(Base):
    __tablename__ = "hack_to_tag_relationships"

    hack_id: Mapped[int] = mapped_column(
        ForeignKey("learning_hacks.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )
    relationship_type: Mapped[str] = mapped_column(
        Enum(
            "TEACHES", "REQUIRES", "REMEDIATES", name="hack_tag_relationship_type_enum"
        ),
        primary_key=True,
    )

    hack: Mapped["LearningHack"] = relationship(
        "LearningHack", back_populates="hack_to_tag_relationships"
    )
    tag: Mapped["Tag"] = relationship("Tag", back_populates="hack_to_tag_relationships")

    # okay

class TagRelationship(Base):
    __tablename__ = "tag_relationships"

    source_tag_id: Mapped[int] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )
    target_tag_id: Mapped[int] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )
    relationship_type: Mapped[str] = mapped_column(
        Enum(
            "PREREQUISITE",
            "DEPENDENCY",
            "ANALOGY",
            "CO-REQUISITE",
            "IS_PARENT_OF",
            name="tag_relationship_type_enum",
        ),
        primary_key=True,
    )

    #  potential future use. atm all weights are set to 1.0
    weight: Mapped[float] = mapped_column(
        Double(53), nullable=False, server_default="1.0"
    )

    source_tag: Mapped["Tag"] = relationship(
        "Tag",
        foreign_keys=[source_tag_id],
        back_populates="tag_relationships_as_source",
    )
    target_tag: Mapped["Tag"] = relationship(
        "Tag",
        foreign_keys=[target_tag_id],
        back_populates="tag_relationships_as_target",
    )


# okay
class UserTagScore(Base):
    __tablename__ = "user_tag_scores"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )
    score: Mapped[float] = mapped_column(
        Double(53), nullable=False, default=0.0, server_default="0.0"
    )
    opportunity_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    total_lapses: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    hard_grades_on_success: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    total_successes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_five_outcomes: Mapped[Optional[List[bool]]] = mapped_column(
        ARRAY(Boolean), server_default="{}"
    )
    last_updated: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    tag: Mapped["Tag"] = relationship("Tag", back_populates="user_tag_scores")
    user: Mapped["User"] = relationship("User", back_populates="user_tag_scores")


# okay
class NoteTag(Base):
    __tablename__ = "note_tags"

    note_id: Mapped[int] = mapped_column(
        ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(
        ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )

    note: Mapped["Note"] = relationship("Note", back_populates="note_tags")
    tag: Mapped["Tag"] = relationship("Tag", back_populates="note_tags")


# okay
class ReviewLog(Base):
    __tablename__ = "review_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id"))
    review_time: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), default=func.now()
    )
    grade: Mapped[int] = mapped_column(SmallInteger)
    pre_review_state: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB)
    post_review_state: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB)

    card: Mapped["Card"] = relationship("Card", back_populates="review_logs")


# okay, keeping redundand info about reviews for efficiency
class UserAward(Base):
    __tablename__ = "user_awards"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    current_streak: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    longest_streak: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    last_review_day: Mapped[Optional[datetime.date]] = mapped_column(Date)
    reviews_today: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    streak_last_updated_date: Mapped[Optional[datetime.date]] = mapped_column(Date)

    user: Mapped["User"] = relationship(back_populates="awards")


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(
        String(120), unique=True, index=True, nullable=False
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    notes: Mapped[List["Note"]] = relationship(
        "Note", back_populates="user", cascade="all, delete-orphan"
    )
    chat_messages: Mapped[List["ChatMessage"]] = relationship(
        "ChatMessage", back_populates="user", cascade="all, delete-orphan"
    )
    feedback: Mapped[List["Feedback"]] = relationship(
        "Feedback", back_populates="user", cascade="all, delete-orphan"
    )
    awards: Mapped["UserAward"] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="joined",
    )
    user_tag_scores: Mapped[List["UserTagScore"]] = relationship(
        "UserTagScore", back_populates="user"
    )

    fsrs_params: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB)


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    field1: Mapped[str] = mapped_column(Text, nullable=False)
    field2: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    user: Mapped["User"] = relationship("User", back_populates="notes")
    cards: Mapped[List["Card"]] = relationship(
        "Card", back_populates="note", cascade="all, delete-orphan"
    )
    note_tags: Mapped[List["NoteTag"]] = relationship("NoteTag", back_populates="note", cascade="all, delete-orphan")


# okay
class Card(Base):
    __tablename__ = "cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    note_id: Mapped[int] = mapped_column(
        ForeignKey("notes.id"), nullable=False, index=True
    )
    front: Mapped[str] = mapped_column(Text)
    back: Mapped[str] = mapped_column(Text)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(True), nullable=False, server_default=func.now()
    )

    due_date: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    stability: Mapped[Optional[float]] = mapped_column(Float)
    difficulty: Mapped[Optional[float]] = mapped_column(Float)
    last_review: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True)
    )
    state: Mapped[int] = mapped_column(
        SmallInteger, default=0, server_default="0", nullable=False
    )
    review_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    lapse_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    pedagogical_difficulty: Mapped[Optional[int]] = mapped_column(SmallInteger)

    note: Mapped["Note"] = relationship("Note", back_populates="cards")
    review_logs: Mapped[List["ReviewLog"]] = relationship(
        "ReviewLog", back_populates="card"
    )


# leave as is - okay
class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    message_type: Mapped[Optional[str]] = mapped_column(String(50))

    user: Mapped["User"] = relationship("User", back_populates="chat_messages")
    __table_args__ = (
        CheckConstraint(role.in_(["user", "model", "ai", "system", "error"])),
    )


FeedbackStatus = Enum(
    "new", "viewed", "in_progress", "resolved", "archived", name="feedback_status"
)


# left as is- okay
class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    status: Mapped[str] = mapped_column(
        FeedbackStatus, default="new", server_default="new", nullable=False
    )

    user: Mapped[Optional["User"]] = relationship("User", back_populates="feedback")


tag_archetype_lemmas = Table(
    "tag_archetype_lemmas",
    Base.metadata,
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "lemma_id", ForeignKey("verb_lemmas.id", ondelete="CASCADE"), primary_key=True
    ),
)
