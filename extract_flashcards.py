import requests
import json

# AnkiConnect API settings
url = "http://localhost:8765"


def request(action, **params):
    return requests.post(
        url, json={"action": action, "version": 6, "params": params}
    ).json()


# Fetch all cards in your deck (replace "Spanish" with your deck name)
deck_name = "Santander"
card_ids = request("findCards", query=f"deck:{deck_name}")["result"]
cards_info = request("cardsInfo", cards=card_ids)["result"]

# Save flashcards to a JSON file
flashcards = []
for card in cards_info:
    front = card["fields"]["Front"]["value"]
    back = card["fields"]["Back"]["value"]
    flashcards.append({"front": front, "back": back})

with open("flashcards.json", "w", encoding="utf-8") as f:
    json.dump(flashcards, f, ensure_ascii=False, indent=2)

print("✅ Flashcards saved to 'flashcards.json'!")
