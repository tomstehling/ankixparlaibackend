"""
Handles SQLite database operations for storing user data and flashcards,
including Spaced Repetition System (SRS) parameters, WhatsApp linking, and imports.
"""
import sqlite3
import logging
import os
import time # Import time for timestamps
from typing import List, Tuple, Optional, Dict, Any, cast

# Import config for DATABASE_FILE, assuming it's defined there
import config as app_config

logger = logging.getLogger(__name__)

# --- Database Configuration ---
# Use DATABASE_FILE from config if available, otherwise default
DATABASE_FILE = getattr(app_config, 'DATABASE_FILE', 'chatbot_cards.db')
logger.info(f"Using database file: {DATABASE_FILE}")

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
    Creates or updates the necessary tables ('users', 'cards') if they don't exist
    or have missing columns required for user accounts, SRS, and WhatsApp linking.
    Uses PRAGMA statements for idempotent column additions and index creation.
    """
    logger.info(f"Initializing database '{DATABASE_FILE}'...")
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # --- Users Table ---
            # Create table statement includes UNIQUE constraint for fresh DBs
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    hashed_password TEXT NOT NULL,
                    whatsapp_number TEXT UNIQUE, -- Added for WhatsApp linking
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # --- Add Columns (Idempotent) ---
            # Add whatsapp_number column *without* UNIQUE constraint if it doesn't exist
            # The UNIQUE constraint will be enforced by the index creation below.
            _add_column_if_not_exists(cursor, "users", "whatsapp_number", "TEXT")

            # --- Add Indexes (Idempotent) ---
            # These indexes enforce uniqueness. Creating the index handles the check on existing data (if any).
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users (email)")
            # Index creation will fail if non-unique whatsapp_numbers exist, handle if needed
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_whatsapp_number ON users (whatsapp_number) WHERE whatsapp_number IS NOT NULL")
            logger.info("Table 'users' checked/created/updated.")


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

            # --- Add Columns to Cards (Idempotent) ---
            # Using default values ensures existing rows get sensible defaults if columns are added
            _add_column_if_not_exists(cursor, table_name, "user_id", "INTEGER NOT NULL DEFAULT -1 REFERENCES users(id) ON DELETE CASCADE")
            _add_column_if_not_exists(cursor, table_name, "due_timestamp", "INTEGER NOT NULL DEFAULT 0")
            _add_column_if_not_exists(cursor, table_name, "interval_days", "REAL DEFAULT 0.0")
            _add_column_if_not_exists(cursor, table_name, "ease_factor", "REAL DEFAULT 2.5")
            _add_column_if_not_exists(cursor, table_name, "learning_step", "INTEGER DEFAULT 0")
            _add_column_if_not_exists(cursor, table_name, "created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP") # Shouldn't be needed if table created with it

            # --- Add Indexes to Cards (Idempotent) ---
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
        if column not in columns:
             logger.info(f"Column '{column}' not found in table '{table}'. Attempting to add it with type '{col_type}'...")
             # Use NO CHECK constraint initially if adding FOREIGN KEY with default to avoid issues on existing rows
             # The FK relationship itself is the main goal.
             alter_sql = f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"
             cursor.execute(alter_sql)
             logger.info(f"Successfully added column '{column}' to table '{table}'.")
        # else: logger.debug(f"Column '{column}' already exists in table '{table}'.") # Optional debug log

    except sqlite3.Error as e:
        # Check for specific error messages if needed (e.g., "duplicate column name")
        if "duplicate column name" in str(e).lower():
             logger.warning(f"Attempted to add column '{column}' to '{table}', but it seems to already exist (Error: {e}).")
        else:
             logger.error(f"Error adding column '{column}' to '{table}': {e}", exc_info=True)
             raise # Re-raise the exception so initialization fails clearly


# --- User Operations ---

def add_user_to_db(email: str, hashed_password: str) -> Optional[int]:
    """Adds a new user to the database."""
    logger.info(f"Attempting to add user with email: {email}")
    # Initialize whatsapp_number as NULL explicitly
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
    # Include whatsapp_number in the selection
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
                # If linking, check if number is taken by someone else
                if whatsapp_number:
                    cursor.execute("SELECT id FROM users WHERE whatsapp_number = ? AND id != ?", (whatsapp_number, user_id))
                    existing_user = cursor.fetchone()
                    if existing_user:
                         logger.warning(f"Update failed: WhatsApp number {whatsapp_number} is already linked to another User ID ({existing_user['id']}).")
                    else:
                         logger.warning(f"Update failed for User ID {user_id}: User not found or no changes needed.")
                else: # If unlinking
                     logger.warning(f"Update failed for User ID {user_id}: User not found or number already unlinked.")
                return False
    except sqlite3.IntegrityError as ie:
         # This will catch the UNIQUE constraint violation if the number is already linked
         if whatsapp_number and ('users.whatsapp_number' in str(ie).lower() or 'unique constraint failed: users.whatsapp_number' in str(ie).lower()):
              logger.warning(f"Update failed: WhatsApp number {whatsapp_number} is already linked to another user account.")
         else:
              logger.error(f"Integrity error updating WhatsApp number for User ID {user_id}: {ie}", exc_info=True)
         return False
    except sqlite3.Error as e:
        logger.exception(f"Database error updating WhatsApp number for User ID {user_id}: {e}")
        return False


# --- Card Operations ---

def add_new_card_to_db(user_id: int, front: str, back: str, tags: List[str]) -> Optional[int]:
    """Adds a new card created via the web UI or API with default SRS state."""
    tags_str = " ".join(tag.strip() for tag in tags if tag.strip()) # Ensure tags are space-separated string
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

def add_card_from_import(user_id: int, front: str, back: str) -> Optional[int]:
    """
    Adds a new card from an import process (like Anki) with default SRS settings.
    Does NOT require tags. Sets card as 'new' and due immediately.
    Returns the new card ID on success, None on failure.
    Raises exceptions on commit errors to be handled by the caller.
    """
    current_timestamp = int(time.time()) # Due immediately
    status = 'new'
    default_ease = 2.5
    default_interval = 0.0
    default_learning_step = 0

    sql = """
        INSERT INTO cards (user_id, front, back, tags, status, due_timestamp, interval_days, ease_factor, learning_step)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    # Logger message can be handled in the calling function (import router) for bulk imports
    # logger.debug(f"Adding imported card for User ID {user_id}: Front='{front[:30]}...'")
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (
                user_id, front, back, None, status, # Tags are None for this import
                current_timestamp, default_interval, default_ease, default_learning_step
            ))
            conn.commit() # Commit happens here
            new_id = cursor.lastrowid
            return new_id # Return ID if successful
    except sqlite3.Error as e:
        # Log is less useful here as the router logs the error better with context
        # logger.exception(f"DB error adding imported card for User ID {user_id}: {e}")
        raise # Re-raise to be caught by the import router logic


def get_all_cards_for_user(user_id: int) -> List[Dict[str, Any]]:
    """Fetches all cards belonging to a specific user, ordered by creation date."""
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
    """Fetches cards that are due for review for a specific user."""
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
            return rows_affected == 1
    except sqlite3.Error as e:
        logger.exception(f"Database error updating SRS for Card ID {card_id}: {e}")
        return False

def get_card_by_id(card_id: int, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Fetches a single card by its ID, optionally checking ownership."""
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
    """Deletes a specific card belonging to a user."""
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
    tags: Optional[List[str]] = None # Accepts list, converts to string
) -> bool:
    """Updates the text content (front, back, tags) of a specific card."""
    logger.info(f"Attempting to update details for Card ID {card_id} by User ID {user_id}")

    fields_to_update: Dict[str, Any] = {}
    if front is not None:
        fields_to_update['front'] = front.strip()
    if back is not None:
        fields_to_update['back'] = back.strip()
    if tags is not None:
        # Convert list of tags back to space-separated string for DB storage
        fields_to_update['tags'] = " ".join(tag.strip() for tag in tags if tag.strip())

    if not fields_to_update:
        logger.warning(f"Update requested for Card ID {card_id} but no valid fields provided.")
        return False

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
# These remain but log warnings if called.
def get_pending_cards(user_id: int) -> List[Dict[str, Any]]:
    logger.warning(f"Function 'get_pending_cards' called for User ID {user_id} (Potentially Deprecated).")
    return []
def mark_cards_as_synced(card_ids: List[int], user_id: int) -> bool:
    logger.warning(f"Function 'mark_cards_as_synced' called for User ID {user_id} (Potentially Deprecated).")
    return True

# --- Main Execution Guard (Example Usage/Testing) ---
if __name__ == "__main__":
    logger.info("Running database module directly for testing/initialization...")
    try:
        initialize_database()
        logger.info("Database initialization check complete.")
        # Add any test operations here if needed
        # e.g., add_user_to_db("test@example.com", "hashedpassword")
    except Exception as main_err:
        logger.error(f"Error during direct execution: {main_err}", exc_info=True)