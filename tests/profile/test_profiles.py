"""Unit tests for user profiles, style templates, mastery levels, and setup."""

from __future__ import annotations

import re

from techradar.feedback.patterns import Mode
from techradar.feedback.rules import StyleRule
from techradar.profile.mastery import mastery_level, mastery_line
from techradar.profile.setup import parse_setup_choice, setup_buttons
from techradar.profile.style import INVARIANT_LINE, mode_for, render_profile_block


def test_profile_block_uses_only_templates():
    """Verify profile block starts with header, fixed templates, and ends with invariant line."""
    block = render_profile_block([StyleRule(mode=Mode.GATE, field="order", value="formula_first")])
    assert block.splitlines() == [
        "My preferences:",
        "Start with the formula, then a worked example, then common traps.",
        INVARIANT_LINE,
    ]


def test_mode_rule_overrides_global_on_same_field():
    """Mode-specific rule overrides global rule on the same style field."""
    rules = [
        StyleRule(mode=None, field="length", value="long"),
        StyleRule(mode=Mode.GATE, field="length", value="short"),
    ]
    block = render_profile_block(rules)
    assert "Keep the answer under 120 words." in block
    assert "comprehensive" not in block.lower()


def test_skip_section_in_profile_block():
    """Verify skip_section rule renders into Leave out a section instruction."""
    rules = [
        StyleRule(mode=Mode.TECH, field="skip_section", value="Historical Context"),
    ]
    block = render_profile_block(rules)
    assert 'Leave out a section called "Historical Context".' in block


def test_mastery_levels():
    """Verify mastery tier calculation thresholds."""
    assert mastery_level(0.95, 70, 30) == "mastered"
    assert mastery_level(0.85, 25, 20) == "exam_ready"
    assert mastery_level(None, None, 1) == "new"
    assert mastery_level(0.60, 10, 15) == "learning"


def test_mastery_line():
    """Verify mastery skip-basics guidance line for mastered topics only."""
    levels = {"algorithms": "mastered", "graphs": "exam_ready", "sorting": "mastered"}
    line = mastery_line(levels, ["algorithms", "graphs"])
    assert line == "I already know these well, so skip their basics: algorithms."

    line_none = mastery_line(levels, ["graphs", "heaps"])
    assert line_none is None


def test_mode_for_detection():
    """Verify context-based mode detection precedence."""
    assert mode_for({"screen": "gate_prep"}) == Mode.GATE
    assert mode_for({"screen": "world_economy"}) == Mode.ECONOMY
    assert mode_for({"session_kind": "gate"}) == Mode.GATE
    assert mode_for({"session_kind": "gov", "exam_tag": "bank_po"}) == Mode.BANK
    assert mode_for({"session_kind": "gov", "exam_tag": "ssc_cgl"}) == Mode.SSC_GK
    assert mode_for({"session_kind": "dev"}) == Mode.TECH
    assert mode_for({"session_kind": "english"}) == Mode.ENGLISH
    assert mode_for({"exam_tags": ["gate_cs"]}) == Mode.GATE
    assert mode_for({}) == Mode.NEWS


def test_setup_buttons_and_parse():
    """Verify setup buttons conform to button regex and parse into valid StyleRule."""
    buttons = setup_buttons(Mode.GATE, 0)
    assert len(buttons) == 1
    assert len(buttons[0]) == 3
    for b in buttons[0]:
        assert re.fullmatch(r"^[a-z_]{1,20}(:[0-9]{1,12}){1,2}$", b.data)

    rule = parse_setup_choice(Mode.GATE, 0, 0)
    assert rule.mode == Mode.GATE
    assert rule.field == "length"
    assert rule.value == "short"
