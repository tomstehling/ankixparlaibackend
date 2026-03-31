import time
from typing import Dict, Any
from core.config import settings
import schemas

# --- SRS Constants (from config) ---
LEARNING_STEPS_MINUTES = settings.LEARNING_STEPS_MINUTES
DEFAULT_EASY_INTERVAL_DAYS = settings.DEFAULT_EASY_INTERVAL_DAYS
MIN_EASE_FACTOR = settings.MIN_EASE_FACTOR
LAPSE_INTERVAL_MULTIPLIER = settings.LAPSE_INTERVAL_MULTIPLIER
DEFAULT_INTERVAL_MODIFIER = settings.DEFAULT_INTERVAL_MODIFIER
DEFAULT_EASE_FACTOR = settings.DEFAULT_EASE_FACTOR
EASY_BONUS = settings.EASY_BONUS

def calculate_srs_review(
    current_state: Dict[str, Any],
    grade: str,
) -> schemas.SRS:
    """
    Calculates the next SRS state for a card based on its current state and a user's grade.
    Returns a schemas.SRS object with the updated values.
    """
    state_to_status = {0: "new", 1: "learning", 2: "review", 3: "lapsed"}
    current_status = state_to_status.get(current_state.get("state", 0), "review")
    
    current_interval = float(current_state.get("stability") or 0.0)
    current_ease = float(current_state.get("difficulty") or DEFAULT_EASE_FACTOR)
    learning_step_index = int(current_state.get("pedagogical_difficulty") or 0)
    
    now = int(time.time())
    seconds_per_day = 86400
    seconds_per_minute = 60

    new_status = current_status
    new_interval = current_interval
    new_ease = current_ease
    next_due = now
    new_learning_step = learning_step_index

    if current_status in ("new", "learning", "lapsed"):
        if grade == "again":
            new_learning_step = 0
            step_minutes = LEARNING_STEPS_MINUTES[new_learning_step]
            next_due = now + step_minutes * seconds_per_minute
            new_status = "learning"
        elif grade == "good":
            new_learning_step = learning_step_index + 1
            if new_learning_step >= len(LEARNING_STEPS_MINUTES):
                # Graduate from learning
                new_status = "review"
                new_interval = 1.0  # First review interval (days)
                next_due = now + int(new_interval * seconds_per_day)
                new_learning_step = 0
            else:
                # Advance learning step
                step_minutes = LEARNING_STEPS_MINUTES[new_learning_step]
                next_due = now + step_minutes * seconds_per_minute
                new_status = "learning"
        elif grade == "easy":
            # Graduate immediately to review with easy interval
            new_status = "review"
            new_interval = DEFAULT_EASY_INTERVAL_DAYS
            next_due = now + int(new_interval * seconds_per_day)
            new_learning_step = 0

    elif current_status == "review":
        if grade == "again":
            # Lapse
            new_status = "learning"
            new_ease = max(MIN_EASE_FACTOR, current_ease - 0.20)
            new_interval = (
                current_interval * LAPSE_INTERVAL_MULTIPLIER
            )
            new_learning_step = 0
            step_minutes = LEARNING_STEPS_MINUTES[new_learning_step]
            next_due = now + step_minutes * seconds_per_minute
        elif grade == "good":
            # Standard review interval calculation
            new_status = "review"
            # If it was 0 (new), start at 1.0
            if current_interval < 1.0:
                new_interval = 1.0
            else:
                new_interval = current_interval * current_ease * DEFAULT_INTERVAL_MODIFIER
            
            next_due = now + int(new_interval * seconds_per_day)
            new_learning_step = 0
        elif grade == "easy":
            # Easy review calculation
            if current_interval < 1.0:
                new_interval = DEFAULT_EASY_INTERVAL_DAYS
            else:
                new_interval = (
                    current_interval * current_ease * DEFAULT_INTERVAL_MODIFIER * EASY_BONUS
                )
            new_ease = current_ease + 0.15
            next_due = now + int(new_interval * seconds_per_day)
            new_learning_step = 0

    # Apply bounds and floors
    new_interval = max(0.01, new_interval)
    new_ease = max(MIN_EASE_FACTOR, new_ease)

    return schemas.SRS(
        status=new_status,
        due_timestamp=next_due,
        interval_days=new_interval,
        ease_factor=new_ease,
        learning_step=new_learning_step,
    )
