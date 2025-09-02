#function to see if user already exists
import database.models as models
from sqlalchemy.future import select
from core.security import get_password_hash
from sqlalchemy.ext.asyncio import AsyncSession
import schemas
from typing import Optional,List    
import logging
import time
logger = logging.getLogger(__name__)
from sqlalchemy.orm import joinedload
import pytz
import datetime
import uuid


DIRECTION_FORWARD = 0 # field1 -> field2
DIRECTION_REVERSE = 1 # field2 -> field1

async def get_user_by_email(db_session: AsyncSession,email: str):
    query = select(models.User).where(models.User.email == email)
    result = await db_session.execute(query)
    user = result.scalar_one_or_none()
    return user

async def create_user(db_session:AsyncSession,user:schemas.UserCreate):
    # Create a new User instance
    hashed_password = get_password_hash(user.password)
    new_user = models.User (email=user.email, hashed_password=hashed_password)
    db_session.add(new_user)
   

    #create awards row
    new_award = models.UserAwards(user=new_user)
    db_session.add(new_award)

    await db_session.commit()
    await db_session.refresh(new_user)
    return new_user

async def get_user_by_id(db_session: AsyncSession, user_id: uuid.UUID):
    query = select(models.User).where(models.User.id == user_id)
    result = await db_session.execute(query)
    user = result.scalar_one_or_none()
    return user




async def get_chat_history(
        db_session: AsyncSession, 
        user_id: uuid.UUID, session_id: str,  
        limit: Optional[int])-> List[models.ChatMessage]:

    query = select(models.ChatMessage).where(
        models.ChatMessage.user_id == user_id,
        models.ChatMessage.session_id == session_id
    )
    query = query.order_by(models.ChatMessage.timestamp.desc())

    if limit:
        query = query.limit(limit)

    result= await db_session.execute(query)
    as_list = list(result.unique().scalars().all())
    return as_list

async def add_chat_message(
    db_session: AsyncSession,
    chat_message: schemas.ChatMessageCreate,
) -> models.ChatMessage:
    """
    Adds a chat message to the database.
    Returns the ID of the inserted message or None on failure.
    """
    logger.info(f"Adding chat message for User ID {chat_message.user_id}, Session ID {chat_message.session_id}, Role '{chat_message.role}'")

    #insert new chat message 
    new_message= models.ChatMessage(
        user_id=chat_message.user_id,
        session_id=chat_message.session_id,
        role=chat_message.role,
        content=chat_message.content,
        message_type=chat_message.message_type
    )
    db_session.add(new_message)
    await db_session.commit()
    await db_session.refresh(new_message)
    return new_message

async def get_all_notes_for_user(
        db_session: AsyncSession,
        user_id: uuid.UUID
)-> List[models.Note]:
    query=select(models.Note).where(models.Note.user_id == user_id).order_by(models.Note.created_at.desc())
    result= await db_session.execute(query)
    as_list = list(result.scalars().all())
    return as_list
    


async def add_note_with_cards(
        db_session: AsyncSession, 
        user_id: uuid.UUID,  
        note_to_add: schemas.NoteContent
) -> models.Note:
    """
    Adds a new note and its corresponding forward and reverse cards to the database.
    The reverse card (field2 -> field1, direction 1) is made due immediately.
    The forward card (field1 -> field2, direction 0) is made due the next day (buried).
    Returns the note_id on success, None on failure.
    """
    tags_str= ""
    if note_to_add.tags:
        tags_str = tags_str.join(tag.strip() for tag in note_to_add.tags if tag.strip())
    current_timestamp = int(time.time())
    tomorrow_timestamp = current_timestamp + 86400 # Simple 1 day bury

    default_ease = 2.5
    default_interval = 0.0
    default_learning_step = 0

    logger.info(f"Attempting to add note and cards for User ID {user_id}: Field1='{note_to_add.field1[:30]}...'")


    new_note = models.Note(
        user_id=user_id,
        field1=note_to_add.field1,
        field2=note_to_add.field2,
        tags=tags_str
    )

    #create cards
    card1= models.Card(
    
        direction= DIRECTION_FORWARD,
        due= current_timestamp,
        ivl=default_interval,
        ease=default_ease,
        reps=default_learning_step,
        note=new_note
    )

    #create cards
    card2= models.Card(
       
        direction= DIRECTION_REVERSE,
        due= tomorrow_timestamp,
        ivl=default_interval,
        ease=default_ease,
        reps=default_learning_step,
        note=new_note
    
    )

    db_session.add_all([card1, card2, new_note])
    await db_session.commit()
    await db_session.refresh(new_note)
    logger.info(f"Note added with ID {new_note.id} for User ID {user_id}")

    return new_note
    


    

async def get_due_cards(
        db_session: AsyncSession,
        user_id: uuid.UUID,
        limit:int=20
) -> list[models.Card]:
    

    query = select(models.Card).join(models.Note) .options(joinedload(models.Card.note)).where(models.Card.due <= int(time.time())).where(models.Note.user_id == user_id).order_by(models.Card.due.asc()).limit(limit)

    result = await db_session.execute(query)
    due_cards = list(result.scalars())
    logger.info(f"Retrieved {len(due_cards)} due cards for User ID {user_id}")
    return due_cards


async def get_card_by_id(
    db_session: AsyncSession, 
    user_id: uuid.UUID,
    card_id: int
)->models.Card:
    query = select(models.Card).join(models.Note).where(models.Note.user_id==user_id).where(models.Card.id == card_id)
    result = await db_session.execute(query)
    card = result.scalar_one_or_none()
    if card is None:
        logger.warning(f"Card with ID {card_id} not found for User ID {user_id}")
    else:
        logger.info(f"Retrieved card with ID {card_id} for User ID {user_id}")
    return card

async def get_note_by_id(
        db_session: AsyncSession,
        user_id: uuid.UUID,
        note_id: int
) -> Optional[models.Note]:
    query = select(models.Note).options(joinedload(models.Note.cards)).where(models.Note.id == note_id, models.Note.user_id == user_id)
    result = await db_session.execute(query)
    note = result.unique().scalar_one_or_none()
    if note is None:
        logger.warning(f"Note with ID {note_id} not found for User ID {user_id}")
        return None
    else:   
        return note


    
async def delete_note(
        db_session: AsyncSession,
        user_id: uuid.UUID,
        note_id: int) -> bool:
    note_to_delete=await get_note_by_id(db_session, user_id, note_id)
    if note_to_delete:
        await db_session.delete(note_to_delete)
        await db_session.commit()
        logger.info(f"Deleted Note ID {note_id} for User ID {user_id}")
        return True
    else:
        logger.warning(f"Note ID {note_id} not found for User ID {user_id}")
        return False
    


async def update_card_srs(
        db_session: AsyncSession,
        user_id: uuid.UUID,
        card_id: int,
        card_srs:schemas.SRS
) -> Optional[models.Card]:
    result = await get_card_by_id(db_session, user_id, card_id)
    if result:
        result.status=card_srs.status
        result.due=card_srs.due_timestamp
        result.ivl=card_srs.interval_days
        result.ease=card_srs.ease_factor
        result.reps=card_srs.learning_step
        await db_session.commit()
        await db_session.refresh(result)
        logger.info(f"Updated SRS for Card ID {card_id} for User ID {user_id}")
        return result
    else:
        return None


async def update_note_details(
        db_session: AsyncSession,
        user_id: uuid.UUID,
        note_id: int,
        note_details: schemas.NoteContent
) -> Optional[models.Note]:
    note_to_update = await get_note_by_id(db_session, user_id, note_id)
    if note_to_update:
        note_to_update.field1 = note_details.field1
        note_to_update.field2 = note_details.field2
        note_to_update.tags = " ".join(tag.strip() for tag in note_details.tags) if note_details.tags else ""
        await db_session.commit()
        await db_session.refresh(note_to_update)
        logger.info(f"Updated Note ID {note_id} for User ID {user_id}")
       
        return note_to_update
        
    else:
        logger.warning(f"Note ID {note_id} not found for User ID {user_id}")
        return None


async def create_feedback(feedback:models.Feedback, db_session:AsyncSession)->models.Feedback:
    db_session.add(feedback)
    await db_session.commit()
    await db_session.refresh(feedback)
    return feedback


# consistency function, resets streak if applicable and returns correct streak
async def get_streak(db_session:AsyncSession, user: models.User, timezone:str)->models.User:
    timezone_object = pytz.timezone(timezone)
    today= datetime.datetime.now(timezone_object).date()
    yesterday= today - datetime.timedelta(days=1)
    if user.awards.streak_last_updated_date is None or user.awards.streak_last_updated_date < yesterday:
        # If no last review date, return current streak
        user.awards.current_streak = 0
        await db_session.commit()
        await db_session.refresh(user)
    return user
            
 
async def update_streak_on_grade(db_session:AsyncSession, user: models.User, timezone:str):
    timezone_object = pytz.timezone(timezone)
    today= datetime.datetime.now(timezone_object).date()
    if user.awards.current_review_date != today:
        user.awards.current_review_date = today
        user.awards.current_review_count = 0

    user.awards.current_review_count += 1
    if user.awards.current_review_count == 10 and user.awards.streak_last_updated_date != today:
        user.awards.current_streak += 1 
        user.awards.streak_last_updated_date = today


        if user.awards.current_streak > user.awards.longest_streak:
            user.awards.longest_streak = user.awards.current_streak
    

    await db_session.commit()



