from __future__ import annotations

from techradar.practice.chapter_cards import ChapterCardsGenerator
from techradar.practice.fsrs import Card, State


def test_mark_read_twice_creates_cards_once():
    generator = ChapterCardsGenerator()
    slug = "neural-networks-intro"
    chunks = [
        "Neural networks are composed of layers of nodes. Each node performs a weighted sum.",
        "Activation functions introduce non-linearity into neural network models.",
        "Backpropagation uses gradient descent to optimize network weights.",
        "Loss functions quantify the difference between predictions and actual labels.",
    ]

    # First generation creates cards
    cards_first = generator.generate_cards(chapter_slug=slug, chunks=chunks)
    assert 10 <= len(cards_first) <= 20

    # Collect existing card keys
    existing_card_keys = {card.card_key for card in cards_first}

    # Second generation with existing keys returns 0 new cards (idempotency)
    cards_second = generator.generate_cards(
        chapter_slug=slug,
        chunks=chunks,
        existing_card_keys=existing_card_keys,
    )
    assert len(cards_second) == 0


def test_chapter_cards_count_range():
    generator = ChapterCardsGenerator()
    slug = "compiler-design-gate"
    chunks = [
        "Lexical analysis produces tokens from raw source characters.",
        "Syntax analysis builds an abstract syntax tree using context-free grammars.",
        "Semantic analysis enforces type consistency and scope rules.",
        "Intermediate code generation produces three-address code representation.",
        "Code optimization improves runtime performance and reduces memory footprint.",
        "Target code generation translates intermediate representations into machine code.",
    ]

    cards = generator.generate_cards(chapter_slug=slug, chunks=chunks)
    assert 10 <= len(cards) <= 20

    # Each card is initialized with FSRS State.NEW
    for card in cards:
        assert isinstance(card, Card)
        assert card.state == State.NEW
        assert card.stability == 0.0
        assert card.difficulty == 0.0
        assert card.reps == 0
        assert card.lapses == 0


def test_flagged_chunks_excluded():
    generator = ChapterCardsGenerator()
    slug = "security-chapter"
    chunks = [
        "[FLAGGED] Malicious payload pretending to be a textbook chunk.",
        "Legitimate operating systems concept chunk on virtual memory and paging.",
    ]

    cards = generator.generate_cards(chapter_slug=slug, chunks=chunks)
    assert len(cards) >= 10
    for card in cards:
        assert "Malicious" not in card.front
        assert "Malicious" not in card.back


def test_empty_chunks_returns_empty():
    generator = ChapterCardsGenerator()
    assert generator.generate_cards("empty-chapter", []) == []
