# anki_handler.py
"""
Handles interaction with the AnkiConnect API (requires Anki running with the add-on).
"""

import requests
import json
from typing import List, Optional, Dict, Any

class AnkiConnector:
    """A class to interact with AnkiConnect."""

    def __init__(self, anki_connect_url: str, deck_name: str, model_name: str, field_front: str, field_back: str):
        """
        Initializes the AnkiConnector.

        Args:
            anki_connect_url: The URL where AnkiConnect is running (e.g., "http://localhost:8765").
            deck_name: The target Anki deck name.
            model_name: The Anki Note Type name.
            field_front: The name of the field for the front of the card in the Note Type.
            field_back: The name of the field for the back of the card in the Note Type.
        """
        self.url = anki_connect_url
        self.default_deck = deck_name
        self.default_model = model_name
        self.field_front = field_front
        self.field_back = field_back
        print(f"AnkiConnector initialized for deck '{deck_name}', model '{model_name}'.")

    def _invoke(self, action: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Sends a request to the AnkiConnect API.

        Args:
            action: The AnkiConnect action to perform (e.g., "addNote", "version").
            params: Optional parameters for the action.

        Returns:
            A dictionary containing the JSON response from AnkiConnect.
            Includes "error" and "result" keys.

        Raises:
            requests.exceptions.RequestException: If the connection fails or times out.
            Exception: For other unexpected errors during the request.
        """
        payload = {'action': action, 'version': 6}
        if params:
            payload['params'] = params

        try:
            # Using a timeout is crucial
            response = requests.post(self.url, json=payload, timeout=5)
            # Raise an exception for bad status codes (4xx or 5xx)
            response.raise_for_status()
            # Parse the JSON response
            response_json = response.json()
            # Check for application-level errors reported by AnkiConnect
            if response_json.get("error"):
                print(f"AnkiConnect API Error for action '{action}': {response_json['error']}")
            return response_json
        except requests.exceptions.Timeout:
            print(f"Error: Timeout connecting to AnkiConnect at {self.url}.")
            raise # Re-raise the specific exception
        except requests.exceptions.ConnectionError:
            print(f"Error: Connection refused by AnkiConnect at {self.url}. Is Anki running?")
            raise # Re-raise the specific exception
        except requests.exceptions.RequestException as e:
            print(f"Error during AnkiConnect request ({action}): {e}")
            raise # Re-raise the specific exception
        except json.JSONDecodeError:
             print(f"Error: Could not decode JSON response from AnkiConnect ({action}).")
             raise # Re-raise the specific exception
        except Exception as e:
            print(f"An unexpected error occurred during AnkiConnect invoke ({action}): {e}")
            raise # Re-raise other exceptions


    def check_connection(self) -> bool:
        """Checks if a connection can be established with AnkiConnect and prints status."""
        print(f"Checking AnkiConnect connection at {self.url}...")
        try:
            response_data = self._invoke('version')
            if response_data.get("error") is None and response_data.get("result") is not None:
                print(f"AnkiConnect connection successful (Version: {response_data.get('result')}).")
                return True
            else:
                 # Error already printed by _invoke
                 return False
        except requests.exceptions.RequestException:
            # Error already printed by _invoke
            print("Ensure Anki is running with the AnkiConnect add-on installed and enabled.")
            return False
        except Exception as e:
             print(f"An unexpected error occurred checking Anki connection: {e}")
             return False


    def add_note(self, front: str, back: str, tags: List[str]) -> Optional[int]:
        """
        Attempts to add a new note (card) to Anki.

        Args:
            front: Text for the front field.
            back: Text for the back field.
            tags: A list of tags to add to the note.

        Returns:
            The note ID if successfully added, otherwise None.
        """
        print(f"Attempting to add card to Anki deck '{self.default_deck}'...")
        note_params = {
            "note": {
                "deckName": self.default_deck,
                "modelName": self.default_model,
                "fields": {
                    self.field_front: front,
                    self.field_back: back
                },
                "options": {
                    "allowDuplicate": False # Prevent adding exact duplicates
                },
                "tags": tags
            }
        }
        try:
            response_data = self._invoke("addNote", note_params)
            note_id = response_data.get("result")
            if note_id is not None and response_data.get("error") is None:
                print(f"Successfully added card to Anki! (Note ID: {note_id})")
                return note_id
            elif response_data.get("error"):
                # Specific error handled in _invoke, just log failure here
                print("Failed to add card due to AnkiConnect error.")
                return None
            else:
                print("AnkiConnect returned an unexpected response for addNote.")
                return None
        except Exception as e:
            # Catch exceptions raised by _invoke or other unexpected issues
            print(f"Failed to add card to Anki due to an exception: {e}")
            return None