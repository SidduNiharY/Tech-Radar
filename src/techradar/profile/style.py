"""Style profile formatting, template mapping, and mode detection."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from techradar.feedback.patterns import Mode
from techradar.feedback.rules import StyleRule

TEMPLATES: dict[tuple[str, str], str] = {
    ("length", "short"): "Keep the answer under 120 words.",
    ("length", "medium"): "Keep the answer around 250 words.",
    ("length", "long"): "Provide a comprehensive, detailed answer.",
    ("format", "bullets"): "Use bullet points for key items.",
    ("format", "prose"): "Explain in clear, continuous prose paragraphs.",
    ("format", "table_first"): "Present a summary table first, followed by explanations.",
    ("depth", "simpler"): "Use simple words and short sentences.",
    ("depth", "standard"): "Use clear, standard technical explanations.",
    ("depth", "deeper"): "Go deep into underlying mechanisms and nuances.",
    ("examples", "none"): "Do not include examples; focus purely on the concept.",
    ("examples", "one"): "Include one short example.",
    ("examples", "two"): "Include two contrasting examples.",
    ("order", "formula_first"): "Start with the formula, then a worked example, then common traps.",
    ("order", "example_first"): (
        "Start with an intuitive example, then define the concept formally."
    ),
    ("order", "definition_first"): (
        "Start with a precise definition, followed by properties and applications."
    ),
    ("block_minutes", "25"): "Design study blocks for 25 minutes.",
    ("block_minutes", "45"): "Design study blocks for 45 minutes.",
    ("block_minutes", "60"): "Design study blocks for 60 minutes.",
}

INVARIANT_LINE: str = (
    "These preferences change only the form. "
    "Never change facts, numbers or sources, and cite as usual."
)


def _rule_text(rule: StyleRule) -> str | None:
    if rule.field == "skip_section":
        return f'Leave out a section called "{rule.value}".'
    return TEMPLATES.get((rule.field, rule.value))


def render_profile_block(rules: Sequence[StyleRule]) -> str:
    """Render structured style rules into prompt block using fixed templates.

    Global rules (mode is None) come first, followed by mode-specific rules.
    Mode-specific rules override global rules on the same field.
    """
    global_rules = [r for r in rules if r.mode is None]
    mode_rules = [r for r in rules if r.mode is not None]

    # Mode rule overrides global rule on same field
    mode_fields = {r.field for r in mode_rules}
    effective_global = [r for r in global_rules if r.field not in mode_fields]

    ordered_rules = effective_global + mode_rules
    template_lines: list[str] = []
    for r in ordered_rules:
        txt = _rule_text(r)
        if txt:
            template_lines.append(txt)

    lines = ["My preferences:"]
    lines.extend(template_lines)
    lines.append(INVARIANT_LINE)
    return "\n".join(lines)


def mode_for(context: Any) -> Mode:
    """Determine the active Mode from screen, command, session, or book context."""
    # 1. Screen or command
    screen = getattr(context, "screen", None) or (
        context.get("screen") if isinstance(context, dict) else None
    )
    if screen:
        screen_lower = str(screen).lower()
        if "gate" in screen_lower:
            return Mode.GATE
        if "ssc" in screen_lower:
            return Mode.SSC_GK
        if "bank" in screen_lower:
            return Mode.BANK
        if "world" in screen_lower or "econ" in screen_lower:
            return Mode.ECONOMY
        if "tech" in screen_lower or "dev" in screen_lower:
            return Mode.TECH
        if "english" in screen_lower:
            return Mode.ENGLISH

    # 2. Running study session
    session_kind = getattr(context, "session_kind", None) or (
        context.get("session_kind") if isinstance(context, dict) else None
    )
    if session_kind:
        sk = str(session_kind).lower()
        if sk == "gate":
            return Mode.GATE
        if sk == "gov":
            exam_tag = getattr(context, "exam_tag", None) or (
                context.get("exam_tag") if isinstance(context, dict) else ""
            )
            return Mode.BANK if "bank" in str(exam_tag).lower() else Mode.SSC_GK
        if sk == "dev":
            return Mode.TECH
        if sk == "english":
            return Mode.ENGLISH

    # 3. Asked book's exam tags
    exam_tags = getattr(context, "exam_tags", None) or (
        context.get("exam_tags") if isinstance(context, dict) else []
    )
    if exam_tags:
        tags_str = " ".join(str(t).lower() for t in exam_tags)
        if "gate" in tags_str:
            return Mode.GATE
        if "bank" in tags_str:
            return Mode.BANK
        if "ssc" in tags_str:
            return Mode.SSC_GK

    # 4. Default
    return Mode.NEWS


# --- Phase 11 Task 7: building the block an answer is given ----------------------------------


async def mode_of_doc(session: Any, doc_id: int | None) -> Mode:
    """The mode of a question: the asked book's exam tags, otherwise `NEWS` (see `mode_for`)."""
    if doc_id is None:
        return Mode.NEWS
    from techradar.db.models import LibraryDoc

    doc = await session.get(LibraryDoc, doc_id)
    return mode_for({"exam_tags": list(doc.exam_tags or []) if doc else []})


async def build_profile(session: Any, question: str, mode: Mode) -> str | None:
    """The "My preferences" block plus the mastery line for one question, or None.

    Every line comes from a fixed template or a stored level, never from content. The result
    goes into the answer's system prompt; citations are checked exactly as before.
    """
    from techradar.feedback.approval import active_style_rules
    from techradar.profile.mastery import load_levels, mastery_line, topics_in_question

    rules = await active_style_rules(session, mode)
    parts: list[str] = []
    if rules:
        parts.append(render_profile_block(rules))
    levels = await load_levels(session)
    line = mastery_line(levels, topics_in_question(question, levels))
    if line:
        parts.append(line)
    return "\n".join(parts) if parts else None
