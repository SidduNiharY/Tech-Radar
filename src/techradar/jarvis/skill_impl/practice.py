from __future__ import annotations


def speak_practice_due(cards_due: int, quiz_ready: bool) -> str:
    """Produce spoken text for practice status including due flashcards and quizzes."""
    if cards_due <= 0 and not quiz_ready:
        return "You have no flashcards due and no quizzes waiting. You are all caught up!"

    card_phrase = (
        f"{cards_due} flashcard{'s' if cards_due != 1 else ''} due for review"
        if cards_due > 0
        else "no flashcards due"
    )

    if cards_due > 0 and quiz_ready:
        return f"You have {card_phrase}, and your daily quiz is ready."
    elif cards_due > 0 and not quiz_ready:
        return f"You have {card_phrase}. No quiz is scheduled right now."
    else:  # cards_due <= 0 and quiz_ready
        return "You have no flashcards due right now, but your daily quiz is ready."
