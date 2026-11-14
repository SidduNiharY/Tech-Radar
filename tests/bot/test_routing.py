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


def test_route_briefing_take() -> None:
    res = route_update(
        42,
        "My take on the market",
        42,
        reply_to_message_id=101,
        active_briefing_message_ids={101, 102},
    )
    assert res == Routed("take", "My take on the market")

    res_flag = route_update(42, "Another take", 42, is_briefing_reply=True)
    assert res_flag == Routed("take", "Another take")

    res_unrelated = route_update(
        42,
        "Random reply",
        42,
        reply_to_message_id=999,
        active_briefing_message_ids={101, 102},
    )
    assert res_unrelated == Routed("ignore")

    res_unauth = route_update(
        7,
        "Stranger take",
        42,
        reply_to_message_id=101,
        active_briefing_message_ids={101, 102},
    )
    assert res_unauth == Routed("ignore")


def test_route_quarantine_owner_only() -> None:
    assert route_update(42, "/quarantine", 42) == Routed("quarantine")
    assert route_update(42, "/quarantine@TechRadarBrainBot", 42) == Routed("quarantine")
    assert route_update(7, "/quarantine", 42) == Routed("ignore")
    # An approved study group may use other commands, never the quarantine.
    assert route_update(-100, "/quarantine", 42, group_ids=frozenset({-100})) == Routed("ignore")
