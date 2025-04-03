# database.py
"""
Handles SQLite database operations for storing user data and flashcards,
including Spaced Repetition System (SRS) parameters.
"""
import sqlite3
import logging
import os
from typing import List, Tuple, Optional, Dict, Any
import time # Import time for timestamps

logger = logging.getLogger(__name__)

# Make DATABASE_FILE configurable via config.py or environment variable later if needed
DATABASE_FILE = getattr(__import__('config', fromlist=['DATABASE_FILE']), 'DATABASE_FILE', 'chatbot_cards.db')

# --- Database Connection ---

def get_db_connection() -> sqlite3.Connection:
    """Establishes a connection to the SQLite database."""
    try:
        conn = sqlite3.connect(DATABASE_FILE, timeout=10) # Add timeout
        # Enable Foreign Key support
        conn.execute("PRAGMA foreign_keys = ON")
        # Return rows as dictionary-like objects
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        logger.exception(f"Failed to connect to database '{DATABASE_FILE}': {e}")
        raise # Propagate error if connection fails

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
            # Add index on email for faster lookups
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users (email)")
            logger.info("Table 'users' checked/created.")

            # --- Cards Table (formerly new_cards) ---
            table_name = "cards" # Let's rename for clarity
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {table_name} (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    front TEXT NOT NULL,
                    back TEXT NOT NULL,
                    tags TEXT,                 -- Store tags as space-separated string
                    status TEXT NOT NULL DEFAULT 'new', -- 'new', 'learning', 'review', 'lapsed'
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    due_timestamp INTEGER NOT NULL DEFAULT 0, -- Unix timestamp for next review
                    interval_days REAL DEFAULT 0.0, -- Interval in days (float for fractions)
                    ease_factor REAL DEFAULT 2.5,   -- SM-2 Ease Factor (default 2.5)
                    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
                )
            """)
            logger.info(f"Table '{table_name}' checked/created.")

            # Add necessary columns if they don't exist (for backward compatibility)
            # This is a simple approach; more robust migration tools exist for complex changes
            _add_column_if_not_exists(cursor, table_name, "user_id", "INTEGER NOT NULL DEFAULT -1 REFERENCES users(id) ON DELETE CASCADE") # Default -1 helps identify old rows if needed
            _add_column_if_not_exists(cursor, table_name, "due_timestamp", "INTEGER NOT NULL DEFAULT 0")
            _add_column_if_not_exists(cursor, table_name, "interval_days", "REAL DEFAULT 0.0")
            _add_column_if_not_exists(cursor, table_name, "ease_factor", "REAL DEFAULT 2.5")
            # Update status default if table existed before? Maybe not needed if default is handled on insert.
            # Consider updating old rows without user_id or due_timestamp if necessary

            # Add indexes for performance
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_user_status_due ON {table_name} (user_id, status, due_timestamp)")
            cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_user_id ON {table_name} (user_id)")


            # --- Handle Renaming (Optional - Run only once if needed) ---
            # Check if old table exists and rename it
            # cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='new_cards'")
            # if cursor.fetchone() and table_name != "new_cards":
            #     logger.info("Found old table 'new_cards', attempting to rename to 'cards'...")
            #     try:
            #         # Need to disable foreign keys briefly for rename in some SQLite versions
            #         cursor.execute("PRAGMA foreign_keys=off;")
            #         conn.commit() # Commit schema changes before rename
            #         cursor.execute("ALTER TABLE new_cards RENAME TO cards")
            #         conn.commit() # Commit rename
            #         cursor.execute("PRAGMA foreign_keys=on;")
            #         conn.commit() # Re-enable FKs
            #         logger.info("Successfully renamed 'new_cards' to 'cards'.")
            #     except sqlite3.Error as rename_err:
            #         logger.error(f"Failed to rename 'new_cards' to 'cards': {rename_err}")
            #         # May need manual intervention if rename fails

            conn.commit()
            logger.info("Database initialization/update complete.")
    except sqlite3.Error as e:
        logger.exception(f"Database initialization/update error: {e}")
        raise

def _add_column_if_not_exists(cursor: sqlite3.Cursor, table: str, column: str, col_type: str):
    """Helper function to add a column only if it doesn't exist."""
    try:
        cursor.execute(f"SELECT {column} FROM {table} LIMIT 1")
        # logger.debug(f"Column '{column}' already exists in table '{table}'.")
    except sqlite3.OperationalError:
        # Column doesn't exist, add it
        logger.info(f"Column '{column}' not found in table '{table}'. Adding it...")
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            logger.info(f"Successfully added column '{column}' to table '{table}'.")
        except sqlite3.Error as add_err:
            logger.error(f"Failed to add column '{column}' to '{table}': {add_err}")
            # Potentially raise here depending on how critical the column is


# --- User Operations ---

def add_user_to_db(email: str, hashed_password: str) -> Optional[int]:
    """Adds a new user to the database."""
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
         return None # Indicate user already exists
    except sqlite3.Error as e:
        logger.exception(f"Database error adding user '{email}': {e}")
        return None

def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Retrieves a user by their email, including the hashed password."""
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
    """Retrieves a user by their ID (excluding password)."""
    logger.debug(f"Fetching user by ID: {user_id}")
    # Select specific fields to avoid returning password hash unintentionally
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
    """
    Adds a new card to the database for a specific user.
    Initializes status to 'new' and due_timestamp to now.
    """
    tags_str = " ".join(tags) # Store as space-separated string
    current_timestamp = int(time.time()) # Due immediately
    status = 'new'
    default_ease = 2.5
    default_interval = 0.0

    logger.info(f"Attempting to add card for User ID {user_id}: Front='{front[:30]}...', Status='{status}'")
    sql = """
        INSERT INTO cards (user_id, front, back, tags, status, due_timestamp, interval_days, ease_factor)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (
                user_id, front, back, tags_str, status,
                current_timestamp, default_interval, default_ease
            ))
            conn.commit()
            new_id = cursor.lastrowid
            logger.info(f"Successfully added card to DB with ID: {new_id} for User ID: {user_id}")
            return new_id
    except sqlite3.Error as e:
        logger.exception(f"Error adding card for User ID {user_id}: {e}")
        return None

def get_due_cards(user_id: int, limit: int = 20) -> List[Dict[str, Any]]:
    """
    Retrieves cards that are due for review for a specific user.
    Orders by due date (oldest first).
    """
    logger.info(f"Fetching due cards for User ID {user_id} (limit {limit})...")
    current_timestamp = int(time.time())
    cards = []
    # Select necessary fields for review
    sql = """
        SELECT id, front, back, tags, status, due_timestamp, interval_days, ease_factor
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
        logger.exception(f"Error fetching due cards for User ID {user_id}: {e}")
    return cards

def update_card_srs(
    card_id: int,
    user_id: int,
    new_status: str,
    new_due_timestamp: int,
    new_interval_days: float,
    new_ease_factor: float
) -> bool:
    """
    Updates the SRS parameters (status, due date, interval, ease) for a specific card
    belonging to the user. Verifies ownership.
    """
    logger.info(f"Updating SRS for Card ID {card_id} (User ID {user_id}): Status='{new_status}', Due='{new_due_timestamp}', Interval='{new_interval_days}', Ease='{new_ease_factor}'")
    sql = """
        UPDATE cards
        SET status = ?, due_timestamp = ?, interval_days = ?, ease_factor = ?
        WHERE id = ? AND user_id = ?
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (
                new_status, new_due_timestamp, new_interval_days, new_ease_factor,
                card_id, user_id
            ))
            conn.commit()
            rows_affected = cursor.rowcount
            if rows_affected == 1:
                logger.info(f"Successfully updated SRS for Card ID {card_id}.")
                return True
            elif rows_affected == 0:
                 logger.warning(f"Failed to update SRS for Card ID {card_id}: Card not found or does not belong to User ID {user_id}.")
                 return False
            else:
                 # Should not happen with PRIMARY KEY constraint
                 logger.error(f"Unexpected number of rows affected ({rows_affected}) updating SRS for Card ID {card_id}.")
                 return False
    except sqlite3.Error as e:
        logger.exception(f"Database error updating SRS for Card ID {card_id}: {e}")
        return False

# --- Functions below are related to the old Anki Sync - Adapt or Remove ---

def get_pending_cards(user_id: int) -> List[Dict[str, Any]]:
    """
    (Potentially Deprecated/Needs Change) Retrieves cards marked 'pending' for Anki sync for a user.
    Consider if 'pending' status is still relevant with integrated SRS. Maybe remove.
    If kept, it should filter by user_id and status='pending'.
    """
    logger.warning(f"Function 'get_pending_cards' called for User ID {user_id} (Potentially Deprecated).")
    cards = []
    # Example: Assuming 'pending' is still a valid status distinct from SRS states
    sql = "SELECT id, front, back, tags FROM cards WHERE user_id = ? AND status = ?"
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # You might need a dedicated 'sync_status' column if 'status' is purely for SRS
            cursor.execute(sql, (user_id, 'pending')) # Check if 'pending' makes sense
            rows = cursor.fetchall()
            cards = [dict(row) for row in rows]
            logger.info(f"Fetched {len(cards)} 'pending' cards for User ID {user_id}.")
    except sqlite3.Error as e:
        logger.exception(f"Error fetching 'pending' cards for User ID {user_id}: {e}")
    return cards

def mark_cards_as_synced(card_ids: List[int], user_id: int) -> bool:
    """
    (Potentially Deprecated/Needs Change) Updates card status to 'synced' for Anki.
    Consider if 'synced' status is still relevant. Verifies ownership.
    """
    logger.warning(f"Function 'mark_cards_as_synced' called for User ID {user_id} (Potentially Deprecated).")
    if not card_ids:
        logger.info("No card IDs provided to mark as synced.")
        return False # Changed from False to True, arguably shouldn't be called with empty list

    logger.info(f"Attempting to mark {len(card_ids)} cards as synced for User ID {user_id}: {card_ids}")
    placeholders = ', '.join('?' * len(card_ids))
    # Update status to 'synced' only if they belong to the user
    # Again, consider if 'synced' status interferes with SRS statuses ('new', 'learning' etc.)
    sql = f"UPDATE cards SET status = 'synced' WHERE id IN ({placeholders}) AND user_id = ?"

    params = card_ids + [user_id] # Combine IDs and user_id for query parameters

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            conn.commit()
            rows_affected = cursor.rowcount
            logger.info(f"Marked {rows_affected} cards as synced in DB for User ID {user_id}.")
            if rows_affected != len(card_ids):
                 logger.warning(f"Attempted to mark {len(card_ids)} cards as synced for user {user_id}, but only {rows_affected} rows were updated (check ownership/existence).")
                 # Return False if not all were updated? Depends on desired strictness.
                 # return False
            return True
    except sqlite3.Error as e:
        logger.exception(f"Error marking cards as synced for User ID {user_id}: {e}")
        return False