
import sqlite3
import logging
import time # Import time for timestamps
from typing import List, Tuple, Optional, Dict, Any, cast

# Import config for DATABASE_FILE, assuming it's defined there
from core.config import settings

logger = logging.getLogger(__name__)

# --- Database Configuration ---
# Use DATABASE_FILE from config if available, otherwise default
DATABASE_FILE = getattr(settings, 'DATABASE_FILE', 'chatbot_cards.db')
logger.info(f"Using database file: {DATABASE_FILE}")

# --- Constants ---
DIRECTION_FORWARD = 0 # field1 -> field2
DIRECTION_REVERSE = 1 # field2 -> field1

# --- Database Connection ---

def get_db_connection() -> sqlite3.Connection:
    """Establishes a connection to the SQLite database."""
    try:
        # Increased timeout, added check_same_thread=False for potential multithreading scenarios with FastAPI
        # Consider using WAL mode for better concurrency if needed: conn.execute("PRAGMA journal_mode=WAL;")
        conn = sqlite3.connect(DATABASE_FILE, timeout=15, check_same_thread=False)
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logger.exception(f"Failed to connect to database '{DATABASE_FILE}': {e}")
        raise

# --- Initialization ---

def initialize_database():
    """
    Creates or updates the necessary tables ('users', 'notes', 'cards') if they don't exist
    to match the target Note/Card schema.
    """
    logger.info(f"Initializing database '{DATABASE_FILE}' - ensuring target schema exists...")
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()



                     # --- Users Table ---
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    hashed_password TEXT NOT NULL,
                    whatsapp_number TEXT UNIQUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
            """)
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users (email)")
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_whatsapp_number ON users (whatsapp_number) WHERE whatsapp_number IS NOT NULL")
            logger.info("Table 'users' schema checked/created.")

            # --- Notes Table ---
            notes_table = "notes"
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {notes_table} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    field1 TEXT NOT NULL, -- e.g., Spanish side
                    field2 TEXT NOT NULL, -- e.g., English side
                    tags TEXT, -- Space-separated tags, associated with the note concept
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
                )
            """)
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{notes_table}_user_id ON {notes_table} (user_id)")
            logger.info(f"Table '{notes_table}' schema checked/created.")

            # --- Cards Table ---
            cards_table = "cards"
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {cards_table} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    note_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL, -- Keep for efficient review querying
                    direction INTEGER NOT NULL, -- 0: Forward, 1: Reverse
                    status TEXT NOT NULL DEFAULT 'new', -- 'new', 'learning', 'review', 'suspended'
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
                    -- SRS Fields
                    due_timestamp INTEGER NOT NULL DEFAULT 0, -- Unix timestamp when card is next due
                    interval_days REAL DEFAULT 0.0, -- Current interval in days
                    ease_factor REAL DEFAULT 2.5, -- Factor affecting interval calculation
                    learning_step INTEGER DEFAULT 0, -- Current step in learning phase (if used)

                    FOREIGN KEY (note_id) REFERENCES notes (id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
                )
            """)

             # --- Chat History Table ---
            chat_messages_table = "chat_messages"
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {chat_messages_table} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    session_id TEXT NOT NULL, -- Can be a UUID string
                    role TEXT NOT NULL CHECK(role IN ('user', 'ai', 'model', 'system')), -- 'model' for Gemini
                    content TEXT NOT NULL,
                    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    message_type TEXT, -- Optional: 'tandem_chat', 'teacher_explanation', etc.
                    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
                )
            """)
            # Indexes for chat_messages
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{chat_messages_table}_user_session_ts ON {chat_messages_table} (user_id, session_id, timestamp)")
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{chat_messages_table}_user_ts ON {chat_messages_table} (user_id, timestamp)")
            logger.info(f"Table '{chat_messages_table}' schema checked/created.")
            logger.info("Database initialization/schema check complete.")
  
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{cards_table}_user_status_due ON {cards_table} (user_id, status, due_timestamp)")
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{cards_table}_note_id ON {cards_table} (note_id)")
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{cards_table}_user_id ON {cards_table} (user_id)")
            logger.info(f"Table '{cards_table}' schema checked/created.")

            conn.commit()
            logger.info("Database initialization/schema check complete.")
    except sqlite3.Error as e:
        logger.exception(f"Database initialization/schema check error: {e}")
        raise


# --- User Operations ---

def add_user_to_db(email: str, hashed_password: str) -> Optional[int]:
    """Adds a new user to the database."""
    logger.info(f"Attempting to add user with email: {email}")
    sql = "INSERT INTO users (email, hashed_password, whatsapp_number) VALUES (?, ?, NULL)"
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (email, hashed_password))
            conn.commit()
            user_id = cursor.lastrowid
            logger.info(f"User added successfully with ID: {user_id}")
            return user_id
    except sqlite3.IntegrityError as ie:
         if 'users.email' in str(ie).lower() or 'unique constraint failed: users.email' in str(ie).lower():
             logger.warning(f"Attempt failed: User with email '{email}' already exists.")
         else:
             logger.error(f"Integrity error adding user '{email}': {ie}", exc_info=True)
         return None
    except sqlite3.Error as e:
        logger.exception(f"Database error adding user '{email}': {e}")
        return None

def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Fetches a user by their email address."""
    logger.debug(f"Fetching user by email: {email}")
    sql = "SELECT id, email, hashed_password, whatsapp_number, created_at FROM users WHERE email = ?"
    user = None
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (email,))
            user_row = cursor.fetchone()
            if user_row:
                user = dict(user_row)
                logger.debug(f"User found for email: {email}")
            else:
                 logger.debug(f"No user found for email: {email}")
    except sqlite3.Error as e:
        logger.exception(f"Database error getting user by email '{email}': {e}")
    return user

def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    """Fetches a user by their ID (excluding password)."""
    logger.debug(f"Fetching user by ID: {user_id}")
    sql = "SELECT id, email, created_at, whatsapp_number FROM users WHERE id = ?"
    user = None
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (user_id,))
            user_row = cursor.fetchone()
            if user_row:
                user = dict(user_row)
                logger.debug(f"User found for ID: {user_id}")
            else:
                logger.debug(f"No user found for ID: {user_id}")
    except sqlite3.Error as e:
        logger.exception(f"Database error getting user by ID '{user_id}': {e}")
    return user

def get_user_by_whatsapp_number(whatsapp_number: str) -> Optional[Dict[str, Any]]:
    """Fetches a user record based on their linked WhatsApp number."""
    logger.debug(f"Fetching user by WhatsApp number: {whatsapp_number}")
    sql = "SELECT id, email, created_at, whatsapp_number FROM users WHERE whatsapp_number = ?"
    user = None
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (whatsapp_number,))
            user_row = cursor.fetchone()
            if user_row:
                user = dict(user_row)
                logger.debug(f"User found for WhatsApp number: {whatsapp_number} (User ID: {user['id']})")
            else:
                logger.debug(f"No user found for WhatsApp number: {whatsapp_number}")
    except sqlite3.Error as e:
        logger.exception(f"Database error getting user by WhatsApp number '{whatsapp_number}': {e}")
    return user

def update_user_whatsapp_number(user_id: int, whatsapp_number: Optional[str]) -> bool:
    """Updates or removes the whatsapp_number for a given user ID."""
    if whatsapp_number:
        logger.info(f"Attempting to link WhatsApp number {whatsapp_number} to User ID {user_id}")
        sql = "UPDATE users SET whatsapp_number = ? WHERE id = ?"
        params = (whatsapp_number, user_id)
    else:
        logger.info(f"Attempting to unlink WhatsApp number from User ID {user_id}")
        sql = "UPDATE users SET whatsapp_number = NULL WHERE id = ?"
        params = (user_id,)

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            conn.commit()
            rows_affected = cursor.rowcount
            if rows_affected == 1:
                logger.info(f"Successfully updated WhatsApp link status for User ID {user_id}")
                return True
            else:
                 # Check potential reasons for failure (mostly relevant for linking)
                 if whatsapp_number:
                     cursor.execute("SELECT id FROM users WHERE whatsapp_number = ? AND id != ?", (whatsapp_number, user_id))
                     existing_user = cursor.fetchone()
                     if existing_user:
                         logger.warning(f"Update failed: WhatsApp number {whatsapp_number} is already linked to another User ID ({existing_user['id']}).")
                     elif cursor.execute("SELECT 1 FROM users WHERE id = ?", (user_id,)).fetchone() is None:
                         logger.warning(f"Update failed for User ID {user_id}: User not found.")
                     else:
                         logger.warning(f"Update for User ID {user_id} affected 0 rows (no change needed or unexpected state).")
                 else: # Unlinking
                     logger.warning(f"Update failed for User ID {user_id}: User not found or number already unlinked.")
                 return False
    except sqlite3.IntegrityError as ie:
         # Catch UNIQUE constraint violation if the number is already linked
         if whatsapp_number and ('users.whatsapp_number' in str(ie).lower() or 'unique constraint failed: users.whatsapp_number' in str(ie).lower()):
              logger.warning(f"Update failed: WhatsApp number {whatsapp_number} is already linked to another user account.")
         else:
              logger.error(f"Integrity error updating WhatsApp number for User ID {user_id}: {ie}", exc_info=True)
         return False
    except sqlite3.Error as e:
        logger.exception(f"Database error updating WhatsApp number for User ID {user_id}: {e}")
        return False

# --- Note & Card Operations ---

def add_note_with_cards(user_id: int, field1: str, field2: str, tags: List[str]) -> Optional[int]:
    """
    Adds a new note and its corresponding forward and reverse cards to the database.
    The reverse card (field2 -> field1, direction 1) is made due immediately.
    The forward card (field1 -> field2, direction 0) is made due the next day (buried).
    Returns the note_id on success, None on failure.
    """
    tags_str = " ".join(tag.strip() for tag in tags if tag.strip())
    current_timestamp = int(time.time())
    tomorrow_timestamp = current_timestamp + 86400 # Simple 1 day bury

    status = 'new'
    default_ease = 2.5
    default_interval = 0.0
    default_learning_step = 0

    sql_insert_note = "INSERT INTO notes (user_id, field1, field2, tags) VALUES (?, ?, ?, ?)"
    sql_insert_card = """
        INSERT INTO cards (note_id, user_id, direction, status, due_timestamp, interval_days, ease_factor, learning_step)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    logger.info(f"Attempting to add note and cards for User ID {user_id}: Field1='{field1[:30]}...'")
    note_id: Optional[int] = None

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # --- 1. Insert Note ---
            cursor.execute(sql_insert_note, (user_id, field1, field2, tags_str))
            retrieved_note_id = cursor.lastrowid
            if retrieved_note_id is None:
                raise sqlite3.DatabaseError("Failed to get note_id after insert")
            note_id = retrieved_note_id

            # --- 2. Insert Reverse Card (Due Now) ---
            cursor.execute(sql_insert_card, (
                note_id, user_id, DIRECTION_FORWARD, status,
                current_timestamp, default_interval, default_ease, default_learning_step
            ))

            # --- 3. Insert Forward Card (Due Tomorrow) ---
            cursor.execute(sql_insert_card, (
                note_id, user_id, DIRECTION_REVERSE, status,
                tomorrow_timestamp, default_interval, default_ease, default_learning_step
            ))

            conn.commit() # Auto-commit via 'with' on success
            logger.info(f"Successfully added Note ID {note_id} and its 2 cards for User ID {user_id}")
            return note_id

    except sqlite3.Error as e:
        logger.exception(f"Database error adding note (ID: {note_id if note_id else 'N/A'}) and cards for User ID {user_id}: {e}")
        return None # Rollback is handled by 'with' on error

def add_card_from_import(user_id: int, field1: str, field2: str) -> Optional[int]:
    """
    Adds a new note and its cards from an import process (e.g., Anki).
    Reverse card due now, Forward card due tomorrow. No tags handled.
    Returns the note_id on success, None on failure. Re-raises DB errors for caller.
    """
    current_timestamp = int(time.time())
    tomorrow_timestamp = current_timestamp + 86400
    status = 'new'
    default_ease = 2.5
    default_interval = 0.0
    default_learning_step = 0

    sql_insert_note = "INSERT INTO notes (user_id, field1, field2, tags) VALUES (?, ?, ?, NULL)"
    sql_insert_card = """
        INSERT INTO cards (note_id, user_id, direction, status, due_timestamp, interval_days, ease_factor, learning_step)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    note_id: Optional[int] = None
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # 1. Insert Note
            cursor.execute(sql_insert_note, (user_id, field1, field2))
            retrieved_note_id = cursor.lastrowid
            if retrieved_note_id is None:
                 raise sqlite3.DatabaseError("Failed to get note_id after import insert")
            note_id = retrieved_note_id

            # 2. Insert Reverse Card (Due Now)
            cursor.execute(sql_insert_card, (
                note_id, user_id, DIRECTION_FORWARD, status,
                current_timestamp, default_interval, default_ease, default_learning_step
            ))

            # 3. Insert Forward Card (Due Tomorrow)
            cursor.execute(sql_insert_card, (
                note_id, user_id, DIRECTION_REVERSE, status,
                tomorrow_timestamp, default_interval, default_ease, default_learning_step
            ))

            conn.commit()
            return note_id
    except sqlite3.Error as e:
        # Let the calling function (e.g., import router) handle logging the error detail
        raise # Re-raise to be caught by the import router logic

def get_all_notes_for_user(user_id: int) -> List[Dict[str, Any]]:
    """
    Fetches all notes belonging to a specific user, ordered by creation date.
    This is suitable for a 'Manage Cards' view where each item represents a note.
    """
    logger.info(f"Fetching all notes for User ID {user_id}...")
    notes_list = []
    sql = """
        SELECT id, user_id, field1, field2, tags, created_at
        FROM notes
        WHERE user_id = ?
        ORDER BY created_at DESC
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (user_id,))
            rows = cursor.fetchall()
            notes_list = [dict(row) for row in rows]
            logger.info(f"Fetched {len(notes_list)} total notes for User ID {user_id}.")
    except sqlite3.Error as e:
        logger.exception(f"Error fetching all notes for User ID {user_id}: {e}")
    return notes_list

def get_due_cards(user_id: int, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Fetches cards that are due for review for a specific user, including note content.
    Returns a list of dictionaries, each representing a card ready for review.
    """
    logger.info(f"Fetching due cards for User ID {user_id} (limit {limit})...")
    current_timestamp = int(time.time())
    due_cards = []
    # Select columns from both cards (c) and notes (n)
    sql = """
        SELECT
            c.id AS card_id, c.note_id, c.user_id, c.direction, c.status,
            c.due_timestamp, c.interval_days, c.ease_factor, c.learning_step,
            n.field1, n.field2, n.tags, n.created_at as note_created_at
        FROM cards c
        JOIN notes n ON c.note_id = n.id
        WHERE c.user_id = ? AND c.due_timestamp <= ?
        ORDER BY c.due_timestamp ASC
        LIMIT ?
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (user_id, current_timestamp, limit))
            rows = cursor.fetchall()
            # Convert rows to dicts. Note alias 'card_id' for clarity.
            due_cards = [dict(row) for row in rows]
            logger.info(f"Fetched {len(due_cards)} due cards for User ID {user_id}.")
    except sqlite3.Error as e:
        logger.exception(f"SQLite error fetching due cards for User ID {user_id}: {e}")
    except Exception as e:
        logger.exception(f"Unexpected error fetching due cards for User ID {user_id}: {e}")
    return due_cards

def update_card_srs(
    card_id: int,
    user_id: int, # Ensure the card belongs to the user updating it
    new_status: str,
    new_due_timestamp: int,
    new_interval_days: float,
    new_ease_factor: float,
    new_learning_step: int
) -> bool:
    """Updates the SRS parameters for a specific card after a review."""
    logger.info(f"Updating SRS for Card ID {card_id} (User ID {user_id}): Status='{new_status}', Due='{new_due_timestamp}', Interval='{new_interval_days:.2f}', Ease='{new_ease_factor:.2f}', Step='{new_learning_step}'")
    sql = """
        UPDATE cards
        SET status = ?, due_timestamp = ?, interval_days = ?, ease_factor = ?, learning_step = ?
        WHERE id = ? AND user_id = ?
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (
                new_status, new_due_timestamp, new_interval_days, new_ease_factor, new_learning_step,
                card_id, user_id
            ))
            conn.commit()
            rows_affected = cursor.rowcount
            if rows_affected == 1:
                 logger.debug(f"SRS update successful for Card ID {card_id}.")
                 return True
            else:
                 logger.warning(f"SRS update failed for Card ID {card_id} (User ID {user_id}): Card not found or not owned by user.")
                 return False
    except sqlite3.Error as e:
        logger.exception(f"Database error updating SRS for Card ID {card_id}: {e}")
        return False

def get_card_by_id(card_id: int, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """
    Fetches a single card by its ID, joining with the note data.
    Optionally checks ownership if user_id is provided.
    """
    logger.debug(f"Fetching card by ID: {card_id} (User ID check: {user_id})")
    card_data = None
    sql = """
        SELECT
            c.id AS card_id, c.note_id, c.user_id, c.direction, c.status,
            c.due_timestamp, c.interval_days, c.ease_factor, c.learning_step,
            c.created_at AS card_created_at,
            n.field1, n.field2, n.tags, n.created_at AS note_created_at
        FROM cards c
        JOIN notes n ON c.note_id = n.id
        WHERE c.id = ?
    """
    params: Tuple[Any, ...] = (card_id,)
    if user_id is not None:
        sql += " AND c.user_id = ?"
        params += (user_id,)

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            row = cursor.fetchone()
            if row:
                card_data = dict(row)
                logger.debug(f"Card found for ID: {card_id}")
            else:
                logger.debug(f"No card found for ID: {card_id} (User ID check: {user_id})")
    except sqlite3.OperationalError as op_err:
        # Catch potential issues if schema is wrong (e.g., during development)
        logger.error(f"Potential schema error fetching card {card_id}: {op_err} - Check table schema and JOINs.")
    except sqlite3.Error as e:
        logger.exception(f"Database error getting card by ID '{card_id}': {e}")
    return card_data

def delete_note(note_id: int, user_id: int) -> bool:
    """
    Deletes a specific note belonging to a user.
    Cascades to delete associated cards due to FOREIGN KEY constraints.
    """
    logger.info(f"Attempting to delete Note ID {note_id} for User ID {user_id}")
    sql = "DELETE FROM notes WHERE id = ? AND user_id = ?"
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (note_id, user_id))
            conn.commit()
            rows_affected = cursor.rowcount
            if rows_affected == 1:
                logger.info(f"Successfully deleted Note ID {note_id} and its associated cards for User ID {user_id}.")
                return True
            else:
                logger.warning(f"Delete failed: Note ID {note_id} not found or does not belong to User ID {user_id}.")
                return False
    except sqlite3.Error as e:
        # Foreign key errors *shouldn't* happen here unless constraint failed, but log just in case
        logger.exception(f"Database error deleting Note ID {note_id} for User ID {user_id}: {e}")
        return False

def update_note_details(
    note_id: int,
    user_id: int,
    field1: Optional[str] = None,
    field2: Optional[str] = None,
    tags: Optional[List[str]] = None # Accepts list, converts to string
) -> bool:
    """Updates the text content (field1, field2, tags) of a specific note."""
    logger.info(f"Attempting to update details for Note ID {note_id} by User ID {user_id}")

    fields_to_update: Dict[str, Any] = {}
    if field1 is not None:
        fields_to_update['field1'] = field1.strip()
    if field2 is not None:
        fields_to_update['field2'] = field2.strip()
    if tags is not None:
        # Convert list of tags back to space-separated string for DB storage
        fields_to_update['tags'] = " ".join(tag.strip() for tag in tags if tag.strip())

    if not fields_to_update:
        logger.warning(f"Update requested for Note ID {note_id} but no valid fields provided.")
        return False

    set_clause = ", ".join(f"{key} = ?" for key in fields_to_update.keys())
    sql = f"UPDATE notes SET {set_clause} WHERE id = ? AND user_id = ?"

    params = list(fields_to_update.values()) + [note_id, user_id]

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            conn.commit()
            rows_affected = cursor.rowcount
            if rows_affected == 1:
                logger.info(f"Successfully updated details for Note ID {note_id}.")
                return True
            else:
                logger.warning(f"Update failed for Note ID {note_id}: Not found or not owned by user.")
                return False
    except sqlite3.Error as e:
        logger.exception(f"Database error updating details for Note ID {note_id}: {e}")
        return False

def get_note_by_id(note_id: int, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Fetches a single note by its ID, optionally checking ownership."""
    logger.debug(f"Fetching note by ID: {note_id} (User ID check: {user_id})")
    note_data = None
    sql = """
        SELECT id, user_id, field1, field2, tags, created_at
        FROM notes
        WHERE id = ?
    """
    params: Tuple[Any, ...] = (note_id,)
    if user_id is not None:
        sql += " AND user_id = ?"
        params += (user_id,)

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            row = cursor.fetchone()
            if row:
                note_data = dict(row)
                logger.debug(f"Note found for ID: {note_id}")
            else:
                logger.debug(f"No note found for ID: {note_id} (User ID check: {user_id})")
    except sqlite3.Error as e:
        logger.exception(f"Database error getting note by ID '{note_id}': {e}")
    return note_data

def add_chat_message(
    user_id: int,
    session_id: str,
    role: str,
    content: str,
    message_type: Optional[str] = None
) -> Optional[int]:
    """
    Adds a chat message to the database.
    Returns the ID of the inserted message or None on failure.
    """
    logger.info(f"Adding chat message for User ID {user_id}, Session ID {session_id}, Role '{role}'")
    sql = """
        INSERT INTO chat_messages (user_id, session_id, role, content, timestamp, message_type)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (user_id, session_id, role, content, message_type))
            conn.commit()
            message_id = cursor.lastrowid
            logger.info(f"Chat message added successfully with ID: {message_id}")
            return message_id
    except sqlite3.Error as e:
        logger.exception(f"Database error adding chat message for User ID {user_id}: {e}")
        return None
    
def get_chat_history(
    user_id: int,
    session_id: str,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Fetches chat messages for a specific user and session.
    Returns a list of dictionaries representing the chat history.
    """
    logger.info(f"Fetching chat history for User ID {user_id}, Session ID {session_id}")
    sql = """
        SELECT id, user_id, session_id, role, content, timestamp, message_type
        FROM chat_messages
        WHERE user_id = ? AND session_id = ?
        ORDER BY timestamp ASC
    """
    params = (user_id, session_id)
    if limit is not None:
        sql = """
            SELECT * FROM (
                SELECT id, user_id, session_id, role, content, timestamp, message_type
                FROM chat_messages
                WHERE user_id = ? AND session_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ) AS latest_messages
            ORDER BY timestamp ASC;
        """
        params += (limit,)
    else:
        # If no limit is given, fetch all messages in chronological order.
        sql = """
            SELECT id, user_id, session_id, role, content, timestamp, message_type
            FROM chat_messages
            WHERE user_id = ? AND session_id = ?
            ORDER BY timestamp ASC;
        """
    


    chat_history = []
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            chat_history = [dict(row) for row in rows]
            logger.info(f"Fetched {len(chat_history)} chat messages for User ID {user_id}, Session ID {session_id}.")
    except sqlite3.Error as e:
        logger.exception(f"Database error fetching chat history for User ID {user_id}, Session ID {session_id}: {e}")
    return chat_history


def get_latest_chat_message_for_session(user_id: int, session_id: str) -> Optional[Dict[str, Any]]:
    """Fetches the single most recent message for a given user and session."""
    logger.debug(f"Fetching latest chat message for UserID: {user_id}, SessionID: {session_id[:8]}...")
    sql = """
        SELECT id, user_id, session_id, role, content, timestamp, message_type
        FROM chat_messages
        WHERE user_id = ? AND session_id = ?
        ORDER BY timestamp DESC
        LIMIT 1
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (user_id, session_id))
            row = cursor.fetchone() # Fetch a single row
            if row:
                return dict(row)
            return None
    except sqlite3.Error as e:
        logger.exception(f"DB error fetching latest chat message for UserID {user_id}, SessionID {session_id}: {e}")
        return None