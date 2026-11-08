from techradar.bot.auth import is_allowed


def test_is_allowed():
    assert is_allowed(42, 42) and not is_allowed(7, 42) and not is_allowed(None, 42)
    assert is_allowed(-100, 42, frozenset({-100}))


def test_is_allowed_empty_groups():
    assert not is_allowed(-100, 42)
    assert not is_allowed(100, 42, frozenset({200, 300}))
