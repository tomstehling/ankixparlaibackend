import datetime
from typing import Optional, Dict, Any, List
from schemas import FSRSUpdate

# Import the correct, modern FSRS components
from fsrs import FSRS, Card, Rating, State, SchedulingInfo  # type: ignore

# --- Default parameters for new users ---
# These are the standard FSRS-4.5 weights.
DEFAULT_FSRS_WEIGHTS = [
    0.212,
    1.2931,
    2.3065,
    8.2956,
    6.4133,
    0.8334,
    3.0194,
    0.001,
    1.8722,
    0.1666,
    0.796,
    1.4835,
    0.0614,
    0.2629,
    1.6483,
    0.6014,
    1.8729,
    0.5425,
    0.0912,
    0.0658,
    0.1542,
]

# --- Pydantic Model for Type Safety ---
# This model will help us pass data cleanly between the DB and the FSRS library


def get_scheduler(user_fsrs_weights: Optional[List[float]] = None) -> FSRS:
    """Initializes an FSRS scheduler with user-specific or default weights."""
    weights = user_fsrs_weights if user_fsrs_weights else DEFAULT_FSRS_WEIGHTS
    return FSRS(w=weights)


def calculate_srs_for_card(
    card_state: Dict[str, Any],  # A dictionary representing the card's current state
    grade: int,  # The user's input: 1=Again, 2=Hard, 3=Good, 4=Easy
    user_weights: Optional[List[float]] = None,
) -> FSRSUpdate:
    """
    Takes a card's current state, performs a review, and returns the updated state.
    """
    scheduler = get_scheduler(user_weights)
    now = datetime.datetime.now(datetime.timezone.utc)

    # The py-fsrs library uses a Card object. We create one from our DB state.
    # If a value is None (for a new card), the Card() constructor handles it.
    card = Card(
        due=card_state.get("due_date") or now,
        stability=card_state.get("stability") or 0.0,
        difficulty=card_state.get("difficulty") or 0.0,
        last_review=card_state.get("last_review"),
        state=State(card_state.get("state") or 0),
    )

    # The library expects a Rating enum
    rating = Rating(grade)

    # This is the core scheduling call from the library
    scheduling_cards: SchedulingInfo = scheduler.review_card(card, rating, now)

    # The result contains the updated card for the rating we provided
    updated_card = scheduling_cards[rating].card

    # We also need to manually update our own rep/lapse counters
    new_review_count = card_state.get("review_count", 0) + 1
    new_lapse_count = card_state.get("lapse_count", 0)
    if rating == Rating.Again:
        new_lapse_count += 1

    # Return the updated state in our Pydantic model for clean data transfer
    return FSRSUpdate(
        due=updated_card.due,
        stability=updated_card.stability,
        difficulty=updated_card.difficulty,
        state=updated_card.state,
        review_count=new_review_count,
        lapse_count=new_lapse_count,
        last_review=now,
    )
