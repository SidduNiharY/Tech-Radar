"""Interactive profile setup choices and button generation."""

from __future__ import annotations

from typing import Any

from techradar.feedback.patterns import Mode
from techradar.feedback.rules import StyleField, StyleRule
from techradar.messaging.outbox import Button

SETUP_QUESTIONS: list[dict[str, Any]] = [
    {
        "field": "length",
        "question": "How long should typical answers be?",
        "options": [
            ("short", "Short (<120w)"),
            ("medium", "Medium (~250w)"),
            ("long", "Comprehensive"),
        ],
    },
    {
        "field": "order",
        "question": "How should concepts be introduced?",
        "options": [
            ("formula_first", "Formula first"),
            ("example_first", "Example first"),
            ("definition_first", "Definition first"),
        ],
    },
    {
        "field": "examples",
        "question": "How many examples do you prefer?",
        "options": [
            ("none", "None"),
            ("one", "One example"),
            ("two", "Two examples"),
        ],
    },
]


def get_setup_questions(mode: Mode) -> list[dict[str, Any]]:
    """Return setup questions for a mode."""
    return SETUP_QUESTIONS


def setup_buttons(mode: Mode, question_index: int) -> list[list[Button]]:
    """Build inline buttons for a setup question step with integer callback arguments."""
    if question_index < 0 or question_index >= len(SETUP_QUESTIONS):
        return []

    q = SETUP_QUESTIONS[question_index]
    options: list[tuple[str, str]] = q["options"]
    row: list[Button] = [
        Button(
            text=label,
            data=f"set_{mode.value}:{question_index}:{opt_idx}",
        )
        for opt_idx, (_, label) in enumerate(options)
    ]
    return [row]


def parse_setup_choice(
    mode: Mode,
    question_index: int,
    choice: int | str,
) -> StyleRule:
    """Convert setup answer selection into an active StyleRule."""
    if question_index < 0 or question_index >= len(SETUP_QUESTIONS):
        raise ValueError(f"Invalid question index {question_index}")

    q = SETUP_QUESTIONS[question_index]
    options: list[tuple[str, str]] = q["options"]

    if isinstance(choice, int) or (isinstance(choice, str) and choice.isdigit()):
        idx = int(choice)
        if 0 <= idx < len(options):
            val = options[idx][0]
        else:
            raise ValueError(f"Invalid choice index {choice}")
    else:
        val = str(choice)

    field_name: StyleField = q["field"]
    return StyleRule(
        mode=mode,
        field=field_name,
        value=val,
    )


# --- Phase 11 Task 7: /setup stores the owner's taps as active rules -------------------------

SETUP_MODES: list[Mode] = list(Mode)
SETUP_PREFIX = "set_"


def setup_mode(action: str) -> Mode | None:
    """The mode of a `set_<mode>` callback action, or None when it is not a setup action."""
    if not action.startswith(SETUP_PREFIX):
        return None
    try:
        return Mode(action.removeprefix(SETUP_PREFIX))
    except ValueError:
        return None


def setup_message(mode: Mode, question_index: int) -> tuple[str, list[list[Button]]]:
    """One setup question for one mode, with its buttons."""
    q = SETUP_QUESTIONS[question_index]
    return f"{mode.value}: {q['question']}", setup_buttons(mode, question_index)


def next_setup_step(mode: Mode, question_index: int) -> tuple[Mode, int] | None:
    """The question after this one: the mode's next, then the next mode's first, then done."""
    if question_index + 1 < len(SETUP_QUESTIONS):
        return mode, question_index + 1
    at = SETUP_MODES.index(mode)
    if at + 1 < len(SETUP_MODES):
        return SETUP_MODES[at + 1], 0
    return None


async def apply_setup_choice(
    session: Any, mode: Mode, question_index: int, choice: int, now: Any
) -> StyleRule:
    """My tap becomes an active rule (`evidence={"setup": true}`) and is kept in the profile.

    The rule comes only from the button's fixed option list, never from any text. A previous
    active rule of the same mode and field is replaced (set back to `undone`).
    """
    from sqlalchemy import select

    from techradar.db.models import ImprovementLog, PreferenceRule, StyleProfile

    rule = parse_setup_choice(mode, question_index, choice)
    found = await session.execute(
        select(PreferenceRule).where(
            PreferenceRule.status == "active",
            PreferenceRule.field == rule.field,
            PreferenceRule.mode == mode.value,
        )
    )
    old = list(found.scalars().all())
    for o in old:
        o.status = "undone"
    row = PreferenceRule(
        mode=mode.value,
        field=rule.field,
        value=rule.value,
        evidence={"setup": True},
        status="active",
        proposed_at=now,
        approved_at=now,
    )
    session.add(row)
    await session.flush()
    session.add(
        ImprovementLog(
            kind="rule",
            key=f"rule:{row.id}",
            before={"status": "proposed", "replaced": [o.id for o in old]},
            after={
                "status": "active",
                "mode": mode.value,
                "field": rule.field,
                "value": rule.value,
            },
            automatic=False,
            at=now,
        )
    )
    profile = await session.get(StyleProfile, mode.value)
    if profile is None:
        session.add(StyleProfile(mode=mode.value, setup={rule.field: rule.value}, updated_at=now))
    else:
        profile.setup = {**profile.setup, rule.field: rule.value}
        profile.updated_at = now
    await session.flush()
    return rule
