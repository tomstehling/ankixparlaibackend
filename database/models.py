import datetime
from typing import List, Optional

from sqlalchemy import (
    ForeignKey,
    String,
    Text,
    Boolean,
    DateTime,
    Float,
    CheckConstraint,
    func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database.session import Base

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    notes: Mapped[List["Note"]] = relationship("Note", back_populates="user", cascade="all, delete-orphan")
    chat_messages: Mapped[List["ChatMessage"]] = relationship("ChatMessage", back_populates="user", cascade="all, delete-orphan")


class Note(Base):
    __tablename__ = "notes"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    field1: Mapped[str] = mapped_column(Text, nullable=False)
    field2: Mapped[str] = mapped_column(Text, nullable=False)
    user: Mapped["User"] = relationship("User", back_populates="notes")
    cards: Mapped[List["Card"]] = relationship("Card", back_populates="note", cascade="all, delete-orphan")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

class Card(Base):
    __tablename__ = "cards"
    id: Mapped[int] = mapped_column(primary_key=True)
    note_id: Mapped[int] = mapped_column(ForeignKey("notes.id"), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(3), nullable=False)
    due: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ivl: Mapped[int] = mapped_column(default=0, server_default="0", nullable=False)
    ease: Mapped[float] = mapped_column(Float, default=2.5, server_default="2.5", nullable=False)
    reps: Mapped[int] = mapped_column(default=0, server_default="0", nullable=False)
    note: Mapped["Note"] = relationship("Note", back_populates="cards")

class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    message_type: Mapped[Optional[str]] = mapped_column(String(50))
    user: Mapped["User"] = relationship("User", back_populates="chat_messages")
    __table_args__ = (CheckConstraint(role.in_(['user', 'model', 'ai', 'system', 'error'])),)