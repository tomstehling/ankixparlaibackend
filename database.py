"""
Handles SQLite database operations for storing user data and flashcards,
including Spaced Repetition System (SRS) parameters.
"""
import sqlite3
import logging
import os
from typing import List, Tuple, Optional, Dict, Any, cast
import time # Import time for timestamps

logger = logging.getLogger(__name__)

# Make DATABASE_FILE configurable via config.py or environment variable later if needed
DATABASE_FILE = getattr(__import__('config', fromlist=['DATABASE_FILE']), 'DATABASE_FILE', 'chatbot_cards.db')

# --- Database Connection ---

def get_db_connection() -> sqlite3.Connection:
    """Establishes a connection to the SQLite database."""
    try:
        conn = sqlite3.connect(DATABASE_FILE, timeout=10) # Add timeout
        conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logger.exception(f"Failed to connect to database '{DATABASE_FILE}': {e}")
        raise

# --- Initialization ---

def initialize_database():
    """
    Creates or updates the necessary tables ('users', 'cards') if they don't exist
    or have missing columns required for user accounts and SRS.
    """
    logger.info(f"Initializing database '{DATABASE_FILE}'...")
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # --- Users Table ---
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    hashed_password TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users (email)")
            logger.info("Table 'users' checked/created.")

            # --- Cards Table ---
            table_name = "cards"
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {table_name} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    front TEXT NOT NULL,
                    back TEXT NOT NULL,
                    tags TEXT,
                    status TEXT NOT NULL DEFAULT 'new',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    due_timestamp INTEGER NOT NULL DEFAULT 0,
                    interval_days REAL DEFAULT 0.0,
                    ease_factor REAL DEFAULT 2.5,
                    learning_step INTEGER DEFAULT 0,
                    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
                )
            """)
            logger.info(f"Table '{table_name}' checked/created.")

            # --- Add Columns (Idempotent) ---
            _add_column_if_not_exists(cursor, table_name, "user_id", "INTEGER NOT NULL DEFAULT -1 REFERENCES users(id) ON DELETE CASCADE")
            _add_column_if_not_exists(cursor, table_name, "due_timestamp", "INTEGER NOT NULL DEFAULT 0")
            _add_column_if_not_exists(cursor, table_name, "interval_days", "REAL DEFAULT 0.0")
            _add_column_if_not_exists(cursor, table_name, "ease_factor", "REAL DEFAULT 2.5")
            _add_column_if_not_exists(cursor, table_name, "learning_step", "INTEGER DEFAULT 0")
            _add_column_if_not_exists(cursor, table_name, "created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")


            # --- Add Indexes (Idempotent) ---
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_user_status_due ON {table_name} (user_id, status, due_timestamp)")
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_user_id ON {table_name} (user_id)")

            conn.commit()
            logger.info("Database initialization/update complete.")
    except sqlite3.Error as e:
        logger.exception(f"Database initialization/update error: {e}")
        raise

def _add_column_if_not_exists(cursor: sqlite3.Cursor, table: str, column: str, col_type: str):
    """Helper function to add a column only if it doesn't exist."""
    try:
        cursor.execute(f"PRAGMA table_info({table})")
        columns = [info['name'] for info in cursor.fetchall()]
        if column in columns:
             return

        logger.info(f"Column '{column}' not found in table '{table}'. Adding it...")
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
        logger.info(f"Successfully added column '{column}' to table '{table}'.")

    except sqlite3.Error as e:
        logger.error(f"Error checking or adding column '{column}' to '{table}': {e}")


# --- User Operations ---
# (Keep add_user_to_db, get_user_by_email, get_user_by_id as they are)
def add_user_to_db(email: str, hashed_password: str) -> Optional[int]:
    # ... (implementation as before) ...
    logger.info(f"Attempting to add user with email: {email}")
    sql = "INSERT INTO users (email, hashed_password) VALUES (?, ?)"
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (email, hashed_password))
            conn.commit()
            user_id = cursor.lastrowid
            logger.info(f"User added successfully with ID: {user_id}")
            return user_id
    except sqlite3.IntegrityError:
         logger.warning(f"Attempt failed: User with email '{email}' already exists.")
         return None
    except sqlite3.Error as e:
        logger.exception(f"Database error adding user '{email}': {e}")
        return None

def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    # ... (implementation as before) ...
    logger.debug(f"Fetching user by email: {email}")
    sql = "SELECT id, email, hashed_password FROM users WHERE email = ?"
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
    # ... (implementation as before) ...
    logger.debug(f"Fetching user by ID: {user_id}")
    sql = "SELECT id, email, created_at FROM users WHERE id = ?"
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


# --- Card Operations ---

def add_new_card_to_db(user_id: int, front: str, back: str, tags: List[str]) -> Optional[int]:
    # ... (implementation as before) ...
    tags_str = " ".join(tags)
    current_timestamp = int(time.time())
    status = 'new'
    default_ease = 2.5
    default_interval = 0.0
    default_learning_step = 0

    logger.info(f"Attempting to add card for User ID {user_id}: Front='{front[:30]}...', Status='{status}'")
    sql = """
        INSERT INTO cards (user_id, front, back, tags, status, due_timestamp, interval_days, ease_factor, learning_step)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (
                user_id, front, back, tags_str, status,
                current_timestamp, default_interval, default_ease, default_learning_step
            ))
            conn.commit()
            new_id = cursor.lastrowid
            logger.info(f"Successfully added card to DB with ID: {new_id} for User ID: {user_id}")
            return new_id
    except sqlite3.Error as e:
        logger.exception(f"Error adding card for User ID {user_id}: {e}")
        return None

def get_all_cards_for_user(user_id: int) -> List[Dict[str, Any]]:
    # ... (implementation as before) ...
    logger.info(f"Fetching all cards for User ID {user_id}...")
    cards = []
    sql = """
        SELECT id, user_id, front, back, tags, status, created_at, due_timestamp, interval_days, ease_factor, learning_step
        FROM cards
        WHERE user_id = ?
        ORDER BY created_at DESC
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (user_id,))
            rows = cursor.fetchall()
            cards = [dict(row) for row in rows]
            logger.info(f"Fetched {len(cards)} total cards for User ID {user_id}.")
    except sqlite3.Error as e:
        logger.exception(f"Error fetching all cards for User ID {user_id}: {e}")
    return cards

def get_due_cards(user_id: int, limit: int = 20) -> List[Dict[str, Any]]:
    # ... (implementation as before - already corrected) ...
    logger.info(f"Fetching due cards for User ID {user_id} (limit {limit})...")
    current_timestamp = int(time.time())
    cards = []
    sql = """
        SELECT id, user_id, front, back, tags, status, created_at,
               due_timestamp, interval_days, ease_factor, learning_step
        FROM cards
        WHERE user_id = ? AND due_timestamp <= ?
        ORDER BY due_timestamp ASC
        LIMIT ?
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (user_id, current_timestamp, limit))
            rows = cursor.fetchall()
            cards = [dict(row) for row in rows]
            logger.info(f"Fetched {len(cards)} due cards for User ID {user_id}.")
    except sqlite3.Error as e:
        logger.exception(f"SQLite error fetching due cards for User ID {user_id}: {e}")
    except Exception as e:
        logger.exception(f"Unexpected error fetching due cards for User ID {user_id}: {e}")
    return cards

def update_card_srs(
    card_id: int,
    user_id: int,
    new_status: str,
    new_due_timestamp: int,
    new_interval_days: float,
    new_ease_factor: float,
    new_learning_step: int
) -> bool:
    # ... (implementation as before) ...
    logger.info(f"Updating SRS for Card ID {card_id} (User ID {user_id}): Status='{new_status}', Due='{new_due_timestamp}', Interval='{new_interval_days}', Ease='{new_ease_factor}', Step='{new_learning_step}'")
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
            return rows_affected == 1
    except sqlite3.Error as e:
        logger.exception(f"Database error updating SRS for Card ID {card_id}: {e}")
        return False

def get_card_by_id(card_id: int, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    # ... (implementation as before) ...
    logger.debug(f"Fetching card by ID: {card_id} (User ID check: {user_id})")
    card = None
    sql = """
        SELECT id, user_id, front, back, tags, status, created_at,
               due_timestamp, interval_days, ease_factor, learning_step
        FROM cards
        WHERE id = ?
    """
    params: Tuple[Any, ...] = (card_id,)
    if user_id is not None:
        sql += " AND user_id = ?"
        params += (user_id,)

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            row = cursor.fetchone()
            if row:
                card = dict(row)
                logger.debug(f"Card found for ID: {card_id}")
            else:
                logger.debug(f"No card found for ID: {card_id} (User ID check: {user_id})")
    except sqlite3.OperationalError as op_err:
        logger.error(f"Potential schema error fetching card {card_id}: {op_err} - Check table schema.")
    except sqlite3.Error as e:
        logger.exception(f"Database error getting card by ID '{card_id}': {e}")
    return card

def delete_card(card_id: int, user_id: int) -> bool:
    # ... (implementation as before) ...
    logger.info(f"Attempting to delete Card ID {card_id} for User ID {user_id}")
    sql = "DELETE FROM cards WHERE id = ? AND user_id = ?"
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (card_id, user_id))
            conn.commit()
            rows_affected = cursor.rowcount
            if rows_affected == 1:
                logger.info(f"Successfully deleted Card ID {card_id} for User ID {user_id}.")
                return True
            else:
                logger.warning(f"Delete failed: Card ID {card_id} not found or does not belong to User ID {user_id}.")
                return False
    except sqlite3.Error as e:
        logger.exception(f"Database error deleting Card ID {card_id} for User ID {user_id}: {e}")
        return False

def update_card_details(
    card_id: int,
    user_id: int,
    front: Optional[str] = None,
    back: Optional[str] = None,
    tags: Optional[List[str]] = None
) -> bool:
    """
    Updates the front, back, or tags of a specific card belonging to the user.
    Only updates fields that are not None.
    Returns True if the update was successful (card found and updated), False otherwise.
    """
    logger.info(f"Attempting to update details for Card ID {card_id} by User ID {user_id}")

    fields_to_update: Dict[str, Any] = {}
    if front is not None:
        fields_to_update['front'] = front
    if back is not None:
        fields_to_update['back'] = back
    if tags is not None:
        # Convert list of tags back to space-separated string for DB storage
        fields_to_update['tags'] = " ".join(tag.strip() for tag in tags if tag.strip())

    if not fields_to_update:
        logger.warning(f"Update requested for Card ID {card_id} but no fields provided.")
        return False # Or maybe True, as no update was needed? False seems safer.

    set_clause = ", ".join(f"{key} = ?" for key in fields_to_update.keys())
    sql = f"UPDATE cards SET {set_clause} WHERE id = ? AND user_id = ?"

    params = list(fields_to_update.values()) + [card_id, user_id]

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            conn.commit()
            rows_affected = cursor.rowcount
            if rows_affected == 1:
                logger.info(f"Successfully updated details for Card ID {card_id}.")
                return True
            else:
                logger.warning(f"Update failed for Card ID {card_id}: Not found or not owner.")
                return False
    except sqlite3.Error as e:
        logger.exception(f"Database error updating details for Card ID {card_id}: {e}")
        return False


# --- Deprecated Functions ---
# (get_pending_cards, mark_cards_as_synced can be removed or left as is)
def get_pending_cards(user_id: int) -> List[Dict[str, Any]]:
    logger.warning(f"Function 'get_pending_cards' called for User ID {user_id} (Potentially Deprecated).")
    return []
def mark_cards_as_synced(card_ids: List[int], user_id: int) -> bool:
    logger.warning(f"Function 'mark_cards_as_synced' called for User ID {user_id} (Potentially Deprecated).")
    return True