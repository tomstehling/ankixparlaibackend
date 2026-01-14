# function to see if user already exists
import database.models as models
from sqlalchemy.future import select
from core.security import get_password_hash
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
import schemas
from typing import Optional, List
import logging
import time

logger = logging.getLogger(__name__)
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy import func, delete
import pytz
import datetime
import uuid


DIRECTION_FORWARD = 0  # field1 -> field2
DIRECTION_REVERSE = 1  # field2 -> field1


async def get_user_by_email(db_session: AsyncSession, email: str):
    query = select(models.User).where(models.User.email == email).options(joinedload(models.User.awards))
    result = await db_session.execute(query)
    user = result.scalar_one_or_none()
    return user


async def create_user(db_session: AsyncSession, user: schemas.UserCreate):
    # Create a new User instance
    hashed_password = get_password_hash(user.password)
    new_user = models.User(email=user.email, hashed_password=hashed_password)
    db_session.add(new_user)

    # create awards row
    new_award = models.UserAward(user=new_user)
    db_session.add(new_award)

    await db_session.commit()
    await db_session.refresh(new_user)
    return new_user


async def get_user_by_id(db_session: AsyncSession, user_id: uuid.UUID):
    query = select(models.User).where(models.User.id == user_id).options(joinedload(models.User.awards))
    result = await db_session.execute(query)
    user = result.scalar_one_or_none()
    return user


async def get_chat_history(
    db_session: AsyncSession, user_id: uuid.UUID, session_id: str, limit: Optional[int]
) -> List[models.ChatMessage]:

    query = select(models.ChatMessage).where(
        models.ChatMessage.user_id == user_id,
        models.ChatMessage.session_id == session_id,
    )
    query = query.order_by(models.ChatMessage.timestamp.desc())

    if limit:
        query = query.limit(limit)

    result = await db_session.execute(query)
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
    logger.info(
        f"Adding chat message for User ID {chat_message.user_id}, Session ID {chat_message.session_id}, Role '{chat_message.role}'"
    )

    # insert new chat message
    new_message = models.ChatMessage(
        user_id=chat_message.user_id,
        session_id=chat_message.session_id,
        role=chat_message.role,
        content=chat_message.content,
        message_type=chat_message.message_type,
    )
    db_session.add(new_message)
    await db_session.commit()
    await db_session.refresh(new_message)
    return new_message


async def get_all_notes_for_user(
    db_session: AsyncSession, user_id: uuid.UUID
) -> List[models.Note]:
    query = (
        select(models.Note)
        .options(selectinload(models.Note.note_tags).joinedload(models.NoteTag.tag))
        .where(models.Note.user_id == user_id)
        .order_by(models.Note.created_at.desc())
    )
    result = await db_session.execute(query)
    as_list = list(result.scalars().all())
    return as_list


async def get_or_create_tag_by_name(db_session: AsyncSession, tag_name: str) -> models.Tag:
    """Gets an existing tag by name or creates a new one (to be added by caller)."""
    tag_name = tag_name.strip()
    result = await db_session.execute(select(models.Tag).where(models.Tag.name == tag_name))
    tag = result.scalar_one_or_none()

    if tag:
        return tag

    # Tag not found, create it
    logger.info(f"Tag '{tag_name}' not found, creating new tag instance.")
    new_tag = models.Tag(
        name=tag_name,
        category="user-generated", # Default category
        subcategory="custom",     # Default subcategory
        cefr_level="A1",         # Default CEFR level
        visibility="INTERNAL",    # Default visibility
    )
    
    db_session.add(new_tag)
    return new_tag


async def add_note_with_cards(
    db_session: AsyncSession, user_id: uuid.UUID, note_to_add: schemas.NoteContent
) -> models.Note:
    """
    Adds a new note and its corresponding forward and reverse cards to the database.
    Returns the note object. Caller must commit the session.
    """
    logger.info(
        f"Attempting to add note and cards for User ID {user_id}: Field1='{note_to_add.field1[:30]}...'"
    )

    current_timestamp = int(time.time())
    tomorrow_timestamp = current_timestamp + 86400

    new_note = models.Note(
        user_id=user_id,
        field1=note_to_add.field1,
        field2=note_to_add.field2,
    )

    # create cards
    card1 = models.Card(
        front=note_to_add.field1,
        back=note_to_add.field2,
        due_date=datetime.datetime.fromtimestamp(current_timestamp, tz=datetime.timezone.utc),
        stability=0.0,
        difficulty=0.0,
        state=0,
        review_count=0,
        lapse_count=0,
        pedagogical_difficulty=0,
        note=new_note,
    )

    # create cards
    card2 = models.Card(
        front=note_to_add.field2,
        back=note_to_add.field1,
        due_date=datetime.datetime.fromtimestamp(tomorrow_timestamp, tz=datetime.timezone.utc),
        stability=0.0,
        difficulty=0.0,
        state=0,
        review_count=0,
        lapse_count=0,
        pedagogical_difficulty=0,
        note=new_note,
    )

    db_session.add_all([card1, card2, new_note])

    # Handle tags after note creation
    if note_to_add.tags:
        for tag_name in note_to_add.tags:
            tag_obj = await get_or_create_tag_by_name(db_session, tag_name)
            # Use relationship instead of note_id to avoid needing a flush
            note_tag = models.NoteTag(note=new_note, tag=tag_obj, is_primary=False)
            db_session.add(note_tag)
    
    return new_note


async def get_due_cards(
    db_session: AsyncSession, user_id: uuid.UUID, limit: int = 20
) -> list[models.Card]:

    query = (
        select(models.Card)
        .join(models.Note)
        .options(
            joinedload(models.Card.note).selectinload(models.Note.note_tags).joinedload(models.NoteTag.tag)
        )
        .where(models.Card.due_date <= func.now())
        .where(models.Note.user_id == user_id)
        .order_by(models.Card.due_date.asc())
        .limit(limit)
    )

    result = await db_session.execute(query)
    due_cards = list(result.scalars())
    logger.info(f"Retrieved {len(due_cards)} due cards for User ID {user_id}")
    return due_cards


async def get_card_by_id(
    db_session: AsyncSession, user_id: uuid.UUID, card_id: int
) -> Optional[models.Card]:
    query = (
        select(models.Card)
        .join(models.Note)
        .where(models.Note.user_id == user_id)
        .where(models.Card.id == card_id)
    )
    result = await db_session.execute(query)
    card = result.scalar_one_or_none()
    if card is None:
        logger.warning(f"Card with ID {card_id} not found for User ID {user_id}")
    else:
        logger.info(f"Retrieved card with ID {card_id} for User ID {user_id}")
    return card


async def get_note_by_id(
    db_session: AsyncSession, user_id: uuid.UUID, note_id: int
) -> Optional[models.Note]:
    query = (
        select(models.Note)
        .options(
            joinedload(models.Note.cards),
            selectinload(models.Note.note_tags).joinedload(models.NoteTag.tag)
        )
        .where(models.Note.id == note_id, models.Note.user_id == user_id)
    )
    result = await db_session.execute(query)
    note = result.unique().scalar_one_or_none()
    if note is None:
        logger.warning(f"Note with ID {note_id} not found for User ID {user_id}")
        return None
    else:
        return note


async def delete_note(
    db_session: AsyncSession, user_id: uuid.UUID, note_id: int
) -> bool:
    logger.info(f"Attempting to delete Note ID {note_id} for User ID {user_id}")
    note_to_delete = await get_note_by_id(db_session, user_id, note_id)
    if note_to_delete:
        try:
            # Delete the note (cards and note_tags will be deleted via cascade)
            await db_session.delete(note_to_delete)
            
            await db_session.commit()
            logger.info(f"Successfully deleted Note ID {note_id} and its associated records.")
            return True
        except Exception as e:
            logger.error(f"Error during note deletion (ID {note_id}): {e}", exc_info=True)
            await db_session.rollback()
            raise
    else:
        logger.warning(f"Note ID {note_id} not found or access denied for User ID {user_id}")
        return False


async def update_note_details(
    db_session: AsyncSession,
    user_id: uuid.UUID,
    note_id: int,
    note_details: schemas.NoteContent,
) -> Optional[models.Note]:
    try:
        note_to_update = await get_note_by_id(db_session, user_id, note_id)
        if note_to_update:
            # Keep track of old values to know if we need to update cards
            old_field1 = note_to_update.field1
            old_field2 = note_to_update.field2
            
            note_to_update.field1 = note_details.field1
            note_to_update.field2 = note_details.field2
            
            # Update cards if fields changed
            if note_details.field1 != old_field1 or note_details.field2 != old_field2:
                for card in note_to_update.cards:
                    # If this was the forward card (front was old field1)
                    if card.front == old_field1:
                        card.front = note_details.field1
                        card.back = note_details.field2
                    # If this was the reverse card (front was old field2)
                    elif card.front == old_field2:
                        card.front = note_details.field2
                        card.back = note_details.field1
            
            # Update tags
            if note_details.tags is not None:
                # Delete existing tags
                stmt = delete(models.NoteTag).where(models.NoteTag.note_id == note_id)
                await db_session.execute(stmt)
                
                # Add new tags
                for tag_name in note_details.tags:
                    if tag_name.strip():
                        tag_obj = await get_or_create_tag_by_name(db_session, tag_name.strip())
                        note_tag = models.NoteTag(note_id=note_to_update.id, tag_id=tag_obj.id, is_primary=False)
                        db_session.add(note_tag)

        await db_session.commit()
        
        # Re-fetch with tags loaded to avoid lazy loading issues in the router
        return await get_note_by_id(db_session, user_id, note_id)
    except Exception as e:
        logger.error(f"Error in update_note_details for Note ID {note_id}: {e}", exc_info=True)
        await db_session.rollback()
        raise e


async def create_feedback(
    feedback: models.Feedback, db_session: AsyncSession
) -> models.Feedback:
    db_session.add(feedback)
    await db_session.commit()
    await db_session.refresh(feedback)
    return feedback


# consistency function, resets streak if applicable and returns correct streak
async def update_card_srs(
    db_session: AsyncSession,
    card_id: int,
    user_id: uuid.UUID,
    card_srs: schemas.SRS,
) -> bool:
    """Updates a card's SRS metadata after a review."""
    card = await get_card_by_id(db_session, user_id, card_id)
    if not card:
        return False

    # Map status string to state integer
    status_map = {"new": 0, "learning": 1, "review": 2, "lapsed": 3}
    card.state = status_map.get(card_srs.status, 2)
    
    # Map Anki-style fields to our Card model fields
    card.stability = card_srs.interval_days
    card.difficulty = card_srs.ease_factor
    card.due_date = datetime.datetime.fromtimestamp(card_srs.due_timestamp, tz=datetime.timezone.utc)
    card.last_review = datetime.datetime.now(datetime.timezone.utc)
    
    # Update counts
    card.review_count += 1
    if card_srs.status == "lapsed":
        card.lapse_count += 1

    await db_session.commit()
    return True


async def get_streak(
    db_session: AsyncSession, user: models.User, timezone: str
) -> models.User:
    # Ensure awards relationship is loaded (should be via joinedload already)
    if user.awards is None:
        # Fallback if not loaded
        result = await db_session.execute(
            select(models.UserAward).where(models.UserAward.user_id == user.id)
        )
        user.awards = result.scalar_one_or_none()
        
        if user.awards is None:
            new_award = models.UserAward(user_id=user.id)
            db_session.add(new_award)
            await db_session.flush()
            user.awards = new_award
    
    timezone_object = pytz.timezone(timezone)
    today = datetime.datetime.now(timezone_object).date()
    yesterday = today - datetime.timedelta(days=1)
    
    if (
        user.awards.streak_last_updated_date is None
        or user.awards.streak_last_updated_date < yesterday
    ):
        # If no last review date, or it was before yesterday, reset current streak
        user.awards.current_streak = 0
        await db_session.flush()
        
    return user


async def update_streak_on_grade(
    db_session: AsyncSession, user: models.User, timezone: str
):
    # Ensure awards relationship is loaded
    if user.awards is None:
        await db_session.refresh(user, attribute_names=["awards"])
        # If still None, create awards for this user
        if user.awards is None:
            new_award = models.UserAward(user=user)
            db_session.add(new_award)
            await db_session.commit()
            await db_session.refresh(user)
    
    timezone_object = pytz.timezone(timezone)
    today = datetime.datetime.now(timezone_object).date()
    
    if user.awards.last_review_day != today:
        user.awards.last_review_day = today
        user.awards.reviews_today = 0

    user.awards.reviews_today += 1
    # Streak increments every 10 reviews on a new day
    if (
        user.awards.reviews_today == 10
        and user.awards.streak_last_updated_date != today
    ):
        user.awards.current_streak += 1
        user.awards.streak_last_updated_date = today

        if user.awards.current_streak > user.awards.longest_streak:
            user.awards.longest_streak = user.awards.current_streak

    await db_session.commit()


async def add_notes_with_cards_bulk(
    db_session: AsyncSession, user: models.User, notes_to_add: list[schemas.NoteContent]
) -> list[models.Note]:

    current_timestamp = int(time.time())
    tomorrow_timestamp = current_timestamp + 86400
    mapped_notes: list[models.Note] = []
    
    for note in notes_to_add:
        new_note = models.Note(
            user_id=user.id, field1=note.field1, field2=note.field2
        )

        card1 = models.Card(
            front=note.field1,
            back=note.field2,
            due_date=datetime.datetime.fromtimestamp(current_timestamp, tz=datetime.timezone.utc),
            stability=0.0, difficulty=0.0, state=0, review_count=0, lapse_count=0, pedagogical_difficulty=0,
            note=new_note,
        )
        card2 = models.Card(
            front=note.field2,
            back=note.field1,
            due_date=datetime.datetime.fromtimestamp(tomorrow_timestamp, tz=datetime.timezone.utc),
            stability=0.0, difficulty=0.0, state=0, review_count=0, lapse_count=0, pedagogical_difficulty=0,
            note=new_note,
        )
        
        mapped_notes.append(new_note)
        
        if note.tags:
            for tag_name in note.tags:
                tag_obj = await get_or_create_tag_by_name(db_session, tag_name)
                note_tag = models.NoteTag(note=new_note, tag=tag_obj, is_primary=False)
                db_session.add(note_tag)

    db_session.add_all(mapped_notes)
    return mapped_notes
