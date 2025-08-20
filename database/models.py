import datetime
import uuid
from typing import List, Optional

from sqlalchemy import (
    ForeignKey,
    String,
    Text,
    DateTime,
    Float,
    CheckConstraint,
    func,
    Enum,
    UUID,
    Date,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database.session import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    notes: Mapped[List["Note"]] = relationship("Note", back_populates="user", cascade="all, delete-orphan")
    chat_messages: Mapped[List["ChatMessage"]] = relationship("ChatMessage", back_populates="user", cascade="all, delete-orphan")
    feedback: Mapped[List["Feedback"]] = relationship("Feedback", back_populates="user", cascade="all, delete-orphan")
    awards: Mapped["UserAwards"] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="joined"
    )
    def __repr__(self) -> str:
        return f"<User(id={self.id}, email='{self.email}')>"


class Note(Base):
    __tablename__ = "notes"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    field1: Mapped[str] = mapped_column(Text, nullable=False)
    field2: Mapped[str] = mapped_column(Text, nullable=False)
    user: Mapped["User"] = relationship("User", back_populates="notes")
    tags: Mapped[str] = mapped_column(Text, default="", server_default="", nullable=False)
    cards: Mapped[List["Card"]] = relationship("Card", back_populates="note", cascade="all, delete-orphan")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    def __repr__(self) -> str:
        field1_preview = f"{self.field1[:30]}..." if len(self.field1) > 30 else self.field1
        return f"<Note(id={self.id}, user_id={self.user_id}, field1='{field1_preview}')>"


class Card(Base):
    __tablename__ = "cards"
    id: Mapped[int] = mapped_column(primary_key=True)
    note_id: Mapped[int] = mapped_column(ForeignKey("notes.id"), nullable=False, index=True)
    direction: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(
        String(10), default="new", server_default="new", nullable=False
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    due: Mapped[int] = mapped_column(nullable=False)
    ivl: Mapped[float] = mapped_column(default=0, server_default="0", nullable=False)
    ease: Mapped[float] = mapped_column(Float, default=2.5, server_default="2.5", nullable=False)
    reps: Mapped[int] = mapped_column(default=0, server_default="0", nullable=False)
    note: Mapped["Note"] = relationship("Note", back_populates="cards")
    def __repr__(self) -> str:
        return f"<Card(id={self.id}, note_id={self.note_id}, status='{self.status}', due={self.due})>"


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    message_type: Mapped[Optional[str]] = mapped_column(String(50))
    user: Mapped["User"] = relationship("User", back_populates="chat_messages")
    __table_args__ = (CheckConstraint(role.in_(['user', 'model', 'ai', 'system', 'error'])),)
    def __repr__(self) -> str:
        content_preview = f"{self.content[:40]}..." if len(self.content) > 40 else self.content
        return f"<ChatMessage(id={self.id}, session_id='{self.session_id}', role='{self.role}', content='{content_preview}')>"


FeedbackStatus = Enum(
    'new', 'viewed', 'in_progress', 'resolved', 'archived', name='feedback_status'
)


class Feedback(Base):
    __tablename__ = "feedback"
    id: Mapped[int] = mapped_column(primary_key=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    user: Mapped[Optional["User"]] = relationship("User", back_populates="feedback")
    status: Mapped[str] = mapped_column(
        FeedbackStatus, default='new', server_default='new', nullable=False
    )
    def __repr__(self) -> str:
        return f"<Feedback(id={self.id}, user_id={self.user_id}, status='{self.status}')>"


class UserAwards(Base):
    __tablename__ = 'user_awards'
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id'), primary_key=True)
    current_streak: Mapped[int] = mapped_column(default=0, server_default='0', nullable=False)
    longest_streak: Mapped[int] = mapped_column(default=0, server_default='0', nullable=False)
    current_review_date: Mapped[Optional[datetime.date]] = mapped_column(Date, nullable=True)
    current_review_count: Mapped[int] = mapped_column(default=0, server_default='0', nullable=False)
    streak_last_updated_date:Mapped[Optional[datetime.date]] = mapped_column(Date, nullable=True)

    user: Mapped["User"] = relationship(back_populates="awards")

    def __repr__(self) -> str:
        return f"<UserAwards(user_id={self.user_id}, current_streak={self.current_streak})>"