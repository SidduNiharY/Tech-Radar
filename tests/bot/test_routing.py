import pytest

from techradar.bot.routing import Routed, route_update


def test_route_owner_commands() -> None:
    assert route_update(42, "/status", 42) == Routed("status")
    assert route_update(42, "/start", 42) == Routed("start")


def test_route_ask() -> None:
    assert route_update(42, "/ask what is repo rate", 42) == Routed("ask", "what is repo rate")
    assert route_update(7, "/ask x", 42).action == "ignore"


def test_route_commands_with_bot_suffix() -> None:
    assert route_update(42, "/status@bot", 42) == Routed("status")
    assert route_update(42, "/start@bot", 42) == Routed("start")
    assert route_update(42, "/status@TechRadarBrainBot", 42) == Routed("status")


def test_route_stranger_ignored() -> None:
    assert route_update(7, "/status", 42) == Routed("ignore")
    assert route_update(7, "/start", 42) == Routed("ignore")


def test_route_update_ignores_non_text() -> None:
    assert route_update(42, None, 42) == Routed("ignore")
    assert route_update(42, "hello", 42) == Routed("ignore")
    assert route_update(42, "", 42) == Routed("ignore")
    assert route_update(42, "   ", 42) == Routed("ignore")
    assert route_update(42, "/help", 42) == Routed("ignore")


def test_route_interactive_commands() -> None:
    assert route_update(42, "/quiz", 42) == Routed("quiz")
    assert route_update(42, "/cards", 42) == Routed("cards")
    assert route_update(42, "/grammar", 42) == Routed("grammar")
    assert route_update(42, "/inbox", 42) == Routed("inbox")
    assert route_update(42, "/plan", 42) == Routed("plan")
    assert route_update(42, "/quiz@bot", 42) == Routed("quiz")
    assert route_update(42, "/cards@bot", 42) == Routed("cards")
    assert route_update(42, "/grammar@bot", 42) == Routed("grammar")
    assert route_update(42, "/inbox@bot", 42) == Routed("inbox")
    assert route_update(42, "/plan@bot", 42) == Routed("plan")


def test_route_interactive_commands_unauthorized() -> None:
    assert route_update(7, "/quiz", 42) == Routed("ignore")
    assert route_update(7, "/cards", 42) == Routed("ignore")
    assert route_update(7, "/grammar", 42) == Routed("ignore")
    assert route_update(7, "/inbox", 42) == Routed("ignore")
    assert route_update(7, "/plan", 42) == Routed("ignore")


def test_take_only_for_known_briefing_message() -> None:
    assert route_update(
        42, "Rates will fall", 42, reply_to_purpose="briefing", reply_to_ref=3
    ) == Routed("take", "Rates will fall")
    assert (
        route_update(42, "Rates will fall", 42, reply_to_purpose="answer", reply_to_ref=9).action
        == "ignore"
    )
    assert route_update(42, "Rates will fall", 42).action == "ignore"
    # a briefing target without its id is not a known briefing
    assert route_update(42, "x", 42, reply_to_purpose="briefing").action == "ignore"


def test_take_never_for_strangers_or_groups_or_commands() -> None:
    kw = {"reply_to_purpose": "briefing", "reply_to_ref": 3}
    assert route_update(7, "Stranger take", 42, **kw) == Routed("ignore")
    assert route_update(-100, "Group take", 42, group_ids=frozenset({-100}), **kw) == Routed(
        "ignore"
    )
    # a command written as a reply stays a command
    assert route_update(42, "/quiz", 42, **kw) == Routed("quiz")


def test_route_quarantine_owner_only() -> None:
    assert route_update(42, "/quarantine", 42) == Routed("quarantine")
    assert route_update(42, "/quarantine@TechRadarBrainBot", 42) == Routed("quarantine")
    assert route_update(7, "/quarantine", 42) == Routed("ignore")
    # An approved study group may use other commands, never the quarantine.
    assert route_update(-100, "/quarantine", 42, group_ids=frozenset({-100})) == Routed("ignore")


def test_route_phase5_commands_owner_only() -> None:
    assert route_update(42, "/study gate os", 42) == Routed("study", "gate os")
    assert route_update(42, "/stop", 42) == Routed("stop", "")
    assert route_update(42, "/skill FastAPI learning", 42) == Routed("skill", "FastAPI learning")
    assert route_update(42, "/study@bot gate os", 42) == Routed("study", "gate os")
    # a study group is allowed to ask, but never to touch the owner's tracker
    for text in ("/study gate os", "/stop", "/skill FastAPI learning"):
        assert route_update(-100, text, 42, group_ids=frozenset({-100})) == Routed("ignore")
        assert route_update(7, text, 42) == Routed("ignore")


def test_practice_commands_are_the_owners_alone() -> None:
    group = frozenset({-100})
    for cmd in ("/quiz", "/cards", "/grammar", "/inbox"):
        assert route_update(42, cmd, 42).action == cmd[1:]
        assert route_update(-100, cmd, 42, group_ids=group) == Routed("ignore")


# --- Phase 3 Task 3 + Phase 6: a long reply is never taken for a pasted text ------------------

LONG = "I think the policy change matters because " + "word " * 60  # 200+ chars, no URL


def test_long_text_alone_is_a_paste() -> None:
    assert len(LONG.strip()) >= 200
    assert route_update(42, LONG, 42).action == "paste"


@pytest.mark.parametrize(
    ("kwargs", "action"),
    [
        ({"reply_to_purpose": "briefing", "reply_to_ref": 3}, "take"),
        ({"reply_to_purpose": "essay", "reply_to_ref": 3}, "essay_reply"),
        ({"reply_to_purpose": "reflection"}, "reflection_reply"),
        ({"ready_message_ids": frozenset({11})}, "ask_book"),
        ({"prediction_message_ids": frozenset({11})}, "prediction_reply"),
        ({"story_open": True}, "story_reply"),
    ],
)
def test_reply_targets_and_an_open_story_win_over_the_paste_rule(
    kwargs: dict[str, object], action: str
) -> None:
    routed = route_update(42, LONG, 42, reply_to_message_id=11, **kwargs)  # type: ignore[arg-type]
    assert routed == Routed(action, LONG.strip())  # type: ignore[arg-type]


def test_a_reply_that_is_one_link_still_goes_to_its_target() -> None:
    kw = {"reply_to_purpose": "briefing", "reply_to_ref": 3}
    assert route_update(42, "https://pib.gov.in/x", 42, reply_to_message_id=11, **kw) == Routed(
        "take", "https://pib.gov.in/x"
    )


def test_commands_win_over_the_paste_rule() -> None:
    assert route_update(42, "/polish " + LONG, 42).action == "polish"
    assert route_update(42, "/ask " + LONG, 42).action == "ask"


def test_a_group_reply_is_never_a_paste_or_a_story() -> None:
    group = frozenset({-100})
    assert route_update(-100, LONG, 42, group_ids=group, story_open=True) == Routed("ignore")
