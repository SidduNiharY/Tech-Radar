from techradar.bot.routing import route_update


def test_route_owner_commands():
    assert route_update(42, "/status", 42) == "status"
    assert route_update(42, "/start", 42) == "start"


def test_route_commands_with_bot_suffix():
    assert route_update(42, "/status@bot", 42) == "status"
    assert route_update(42, "/start@bot", 42) == "start"
    assert route_update(42, "/status@TechRadarBrainBot", 42) == "status"


def test_route_stranger_ignored():
    assert route_update(7, "/status", 42) == "ignore"
    assert route_update(7, "/start", 42) == "ignore"


def test_route_update_ignores_non_text():
    assert route_update(42, None, 42) == "ignore"
    assert route_update(42, "hello", 42) == "ignore"
    assert route_update(42, "", 42) == "ignore"
    assert route_update(42, "   ", 42) == "ignore"
    assert route_update(42, "/help", 42) == "ignore"
