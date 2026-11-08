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
