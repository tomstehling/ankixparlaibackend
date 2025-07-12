#function to see if user already exists
from database.models import User, ChatMessage,Note
from sqlalchemy.future import select
from core.security import get_password_hash
from sqlalchemy.ext.asyncio import AsyncSession
from schemas import UserCreate, ChatMessageCreate
from typing import Optional
import logging
logger = logging.getLogger(__name__)

async def get_user_by_email(db_session: AsyncSession,email: str):
    query = select(User).where(User.email == email)
    result = await db_session.execute(query)
    user = result.scalar_one_or_none()
    return user

async def create_user(db_session:AsyncSession,user:UserCreate):
    # Create a new User instance
    hashed_password = get_password_hash(user.password)
    new_user = User (email=user.email, hashed_password=hashed_password)
    db_session.add(new_user)
    await db_session.commit()
    await db_session.refresh(new_user)
    return new_user

async def get_user_by_id(db_session: AsyncSession, user_id: int):
    query = select(User).where(User.id == user_id)
    result = await db_session.execute(query)
    user = result.scalar_one_or_none()
    return user

async def get_chat_history(
        db_session: AsyncSession, 
        user_id: int, session_id: str,  
        limit: Optional[int]):
    """
    Fetches chat messages for a specific user and session.
    Returns a list of chat messages.
    """
    if limit is None:
        query = select(ChatMessage).where(
            ChatMessage.user_id == user_id,
            ChatMessage.session_id == session_id
        ).order_by(ChatMessage.timestamp.asc())
       
    else:
        subquery = select(ChatMessage).where(
                ChatMessage.user_id == user_id,
                ChatMessage.session_id == session_id
            ).order_by(ChatMessage.timestamp.desc()).subquery()
        
        query = select(subquery).order_by(subquery.c.timestamp.asc())


    result = await db_session.execute(query)


    return result.scalars().all()


async def add_chat_message(
    db_session: AsyncSession,
    chat_message: ChatMessageCreate,
) -> ChatMessage:
    """
    Adds a chat message to the database.
    Returns the ID of the inserted message or None on failure.
    """
    logger.info(f"Adding chat message for User ID {chat_message.user_id}, Session ID {chat_message.session_id}, Role '{chat_message.role}'")

    #insert new chat message 
    new_message= ChatMessage(
        user_id=chat_message.user_id,
        session_id=chat_message.session_id,
        role=chat_message.role,
        content=chat_message.content,
        message_type=chat_message.message_type
    )
    await db_session.add(new_message)
    await db_session.commit()
    await db_session.refresh(new_message)
    return new_message

async def get_all_notes_for_user(
        db_session: AsyncSession,
        user_id: int
):
    query=select(Note).where(Note.user_id == user_id).order_by(Note.created_at.desc())
    result= await db_session.execute(query)
    return result.scalars().all()
    
