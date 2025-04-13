# routers/import_export.py
import zipfile
import sqlite3
import tempfile
import os
import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status # Keep status
from typing import List, Optional

# --- Setup Logging FIRST ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Project Imports ---
from database import add_card_from_import
from dependencies import get_current_active_user
import utils
try:
    from models import UserPublic, AnkiImportSummary
except ImportError as e:
    logger.error(f"Failed to import UserPublic or AnkiImportSummary from models: {e}", exc_info=True)
    raise RuntimeError("Could not import necessary models. Cannot start application.") from e

# --- Router Setup ---
# REMOVE the prefix here <<<--- FIX
router = APIRouter(
    # prefix="/import", # <<<--- REMOVE THIS LINE
    tags=["import"], # Keep the tag for documentation grouping
    dependencies=[Depends(get_current_active_user)]
)

# Helper to find the collection file within the zip
def find_anki_collection(zip_ref: zipfile.ZipFile) -> Optional[str]:
    """Finds the .anki2 or .anki21 file in the zip archive."""
    for filename in zip_ref.namelist():
        if filename.endswith(".anki21") or filename.endswith(".anki2"):
            return filename
    return None

# The path decorator should only contain the specific part for this route within the router
@router.post("/anki", response_model=AnkiImportSummary, status_code=status.HTTP_201_CREATED)
async def import_anki_deck(
    file: UploadFile = File(..., description="Anki Deck Package (.apkg file)"),
    current_user: UserPublic = Depends(get_current_active_user),
):
    # ... (rest of the function remains exactly the same) ...
    """
    Imports cards (Front/Back text only) from an Anki .apkg file.
    Ignores scheduling, tags, media, and deck structure. Strips basic HTML.
    """
    imported_count = 0
    skipped_count = 0
    error_count = 0
    notes_processed_count = 0
    overall_error_message = None
    notes_data = []

    if not file.filename or not file.filename.endswith(".apkg"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file format. Please upload an .apkg file."
        )
    logger.info(f"Received .apkg file: {file.filename} for user {current_user.id}")

    with tempfile.TemporaryDirectory() as tmpdir:
        try:
            temp_apkg_path = os.path.join(tmpdir, file.filename)
            with open(temp_apkg_path, "wb") as buffer:
                contents = await file.read()
                if not contents:
                     raise HTTPException(status_code=400, detail="Uploaded file is empty.")
                buffer.write(contents)
            logger.info(f"Saved uploaded file to {temp_apkg_path}")

            with zipfile.ZipFile(temp_apkg_path, 'r') as zip_ref:
                collection_filename = find_anki_collection(zip_ref)
                if not collection_filename:
                    raise HTTPException(status_code=400, detail="Could not find Anki collection file (.anki2 or .anki21) in the package.")

                collection_subpath = "collection.anki2"
                collection_path = os.path.join(tmpdir, collection_subpath)
                zip_ref.extract(collection_filename, tmpdir)
                os.rename(os.path.join(tmpdir, collection_filename), collection_path)
                logger.info(f"Extracted Anki DB to {collection_path}")

                anki_conn = None
                try:
                    anki_conn = sqlite3.connect(collection_path)
                    anki_cursor = anki_conn.cursor()
                    logger.info("Connected to extracted Anki database.")
                    anki_cursor.execute("SELECT id, flds FROM notes")
                    notes_data = anki_cursor.fetchall()
                    logger.info(f"Fetched {len(notes_data)} notes from Anki DB.")
                    notes_processed_count = len(notes_data)
                except sqlite3.Error as db_err:
                    logger.error(f"SQLite error accessing Anki DB: {db_err}", exc_info=True)
                    overall_error_message = f"Database error processing Anki file: {db_err}"
                    error_count = notes_processed_count
                    notes_data = []
                finally:
                    if anki_conn: anki_conn.close()

                if notes_data:
                    for note_id, flds in notes_data:
                        try:
                            fields = flds.split("\x1f")
                            if len(fields) >= 2:
                                front_text = utils.strip_html_bs4(fields[0].strip()) if utils.contains_html(fields[0]) else fields[0].strip()
                                back_text = utils.strip_html_bs4(fields[1].strip()) if utils.contains_html(fields[1]) else fields[1].strip()

                                if front_text and back_text:
                                    new_card_id = add_card_from_import(
                                        user_id=current_user.id,
                                        front=front_text,
                                        back=back_text
                                    )
                                    if new_card_id is not None: imported_count += 1
                                    else: error_count += 1
                                else:
                                    logger.warning(f"Skipping Anki note {note_id}: empty front/back field.")
                                    skipped_count += 1
                            else:
                                logger.warning(f"Skipping Anki note {note_id}: not enough fields.")
                                skipped_count += 1
                        except Exception as card_err:
                            logger.error(f"Error processing/inserting Anki note {note_id}: {card_err}", exc_info=True)
                            error_count += 1

        except zipfile.BadZipFile:
            logger.error("Uploaded file is not a valid zip archive.", exc_info=True)
            raise HTTPException(status_code=400, detail="Invalid .apkg file format (not a zip archive).")
        except HTTPException as http_exc:
             raise http_exc
        except Exception as e:
            logger.error(f"An unexpected error occurred during Anki import: {e}", exc_info=True)
            final_error_msg = overall_error_message or f"An unexpected error occurred: {e}"
            if not notes_data and notes_processed_count == 0 and error_count == 0: pass
            elif notes_processed_count > 0: error_count = notes_processed_count - imported_count - skipped_count
            return AnkiImportSummary(
                imported_count=imported_count, skipped_count=skipped_count,
                error_count=error_count, error_message=str(final_error_msg)
            )

    logger.info(f"Import summary for user {current_user.id}: Imported={imported_count}, Skipped={skipped_count}, Errors={error_count}")
    final_summary_error_msg = overall_error_message
    if error_count > 0 and not final_summary_error_msg:
        final_summary_error_msg = f"{error_count} notes encountered errors during processing or insertion."

    return AnkiImportSummary(
        imported_count=imported_count, skipped_count=skipped_count,
        error_count=error_count, error_message=final_summary_error_msg
    )