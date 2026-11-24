from __future__ import annotations

import re

from pydantic import BaseModel, Field

from techradar.llm.client import Completer, complete_json
from techradar.llm.roles import Role
from techradar.security.untrusted import wrap_untrusted

_MOCK_SYSTEM = (
    "You are an assistant extracting mock test scorecard results from text. "
    "Extract the exam name, total score, max total, and section scores. "
    "Do NOT invent numbers; extract only numbers present in the text."
)


class SectionScore(BaseModel):
    name: str = Field(max_length=40)
    score: float
    max_score: float | None = None
    attempted: int | None = None
    correct: int | None = None
    time_min: float | None = None


class MockScore(BaseModel):
    exam: str = Field(default="Mock", max_length=40)
    total: float
    max_total: float | None = None
    sections: list[SectionScore] = Field(default_factory=list, max_length=8)


def extract_mock_regex(text: str) -> MockScore | None:
    """Extract mock score and sections using deterministic regex patterns."""
    lines = text.splitlines()

    total_score: float | None = None
    max_total: float | None = None
    exam_name = "Mock"

    # Pattern for Total Score:? <x> ?/ ?<y>
    total_pat = re.compile(
        r"(?:total\s*score|overall\s*score|total)\s*:?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:/\s*([0-9]+(?:\.[0-9]+)?))?",
        re.IGNORECASE,
    )
    # Pattern for section: <Section name> <score> / <max_score>
    sec_pat = re.compile(
        r"^([A-Za-z\s&]+?)\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?)\s*/\s*([0-9]+(?:\.[0-9]+)?)$",
    )

    attempted_pat = re.compile(r"^attempted\s*:?\s*([0-9]+)$", re.IGNORECASE)
    correct_pat = re.compile(r"^correct\s*:?\s*([0-9]+)$", re.IGNORECASE)

    sections: list[SectionScore] = []

    for line in lines:
        trimmed = line.strip()
        if not trimmed:
            continue

        # `Attempted: n` and `Correct: n` belong to the section just above them
        am, cm = attempted_pat.match(trimmed), correct_pat.match(trimmed)
        if am or cm:
            if sections:
                if am:
                    sections[-1].attempted = int(am.group(1))
                if cm:
                    sections[-1].correct = int(cm.group(1))
            continue

        # Check total
        tm = total_pat.search(trimmed)
        if tm:
            total_score = float(tm.group(1))
            if tm.group(2):
                max_total = float(tm.group(2))
            continue

        # Check section
        sm = sec_pat.match(trimmed)
        if sm:
            sec_name = sm.group(1).strip()
            # Exclude lines that say Total
            if "total" not in sec_name.lower():
                sec_score = float(sm.group(2))
                sec_max = float(sm.group(3))
                sections.append(
                    SectionScore(
                        name=sec_name[:40],
                        score=sec_score,
                        max_score=sec_max,
                    )
                )

    if total_score is None:
        return None

    return MockScore(
        exam=exam_name,
        total=total_score,
        max_total=max_total,
        sections=sections[:8],
    )


def _number_variants(val: float | int) -> list[str]:
    v_float = float(val)
    variants = [f"{v_float}"]
    if v_float == int(v_float):
        variants.append(f"{int(v_float)}")
        variants.append(f"{int(v_float)}.0")
    else:
        variants.append(f"{v_float:.1f}")
        variants.append(f"{v_float:.2f}")
    return list(set(variants))


def numbers_present(score: MockScore, text: str) -> bool:
    """Verify that every number in the score appears in the normalized OCR text."""
    # Normalize text: remove commas in numbers like 1,000 -> 1000
    norm_text = re.sub(r"(\d),(\d)", r"\1\2", text)

    # Collect numbers to check
    numbers_to_check: list[float] = [score.total]
    if score.max_total is not None:
        numbers_to_check.append(score.max_total)

    for s in score.sections:
        numbers_to_check.append(s.score)
        if s.max_score is not None:
            numbers_to_check.append(s.max_score)
        if s.attempted is not None:
            numbers_to_check.append(float(s.attempted))
        if s.correct is not None:
            numbers_to_check.append(float(s.correct))

    for num in numbers_to_check:
        variants = _number_variants(num)
        found = False
        for v in variants:
            # Word boundary check or substring check
            escaped = re.escape(v)
            if re.search(rf"(?<![0-9.]){escaped}(?![0-9.])", norm_text):
                found = True
                break
        if not found:
            return False

    return True


async def extract_mock(completer: Completer, text: str) -> MockScore | None:
    """Extract mock score via regex first, falling back to LLM with numbers_present check."""
    regex_res = extract_mock_regex(text)
    if regex_res is not None and numbers_present(regex_res, text):
        return regex_res

    # Fallback to model
    untrusted_user = f"Scorecard text (untrusted OCR):\n{wrap_untrusted(text)}"
    try:
        model_score = await complete_json(
            completer,
            Role.WORKER,
            _MOCK_SYSTEM,
            untrusted_user,
            MockScore,
        )
    except Exception:
        return None

    if numbers_present(model_score, text):
        return model_score

    return None


def _fmt_num(n: float) -> str:
    if n == int(n):
        return str(int(n))
    return f"{n:.1f}"


def render_mock_reply(
    m: MockScore,
    cutoff: float | None = None,
    category: str = "General",
) -> str:
    """Render friendly Telegram feedback for a saved mock scorecard."""
    total_str = _fmt_num(m.total)
    max_str = _fmt_num(m.max_total) if m.max_total is not None else ""
    line1 = f"📊 Mock saved: {total_str}/{max_str}." if max_str else f"📊 Mock saved: {total_str}."

    lines = [line1]

    if cutoff is not None:
        gap = abs(cutoff - m.total)
        gap_str = f"{gap:.1f}"
        cutoff_str = f"{cutoff:.1f}"
        direction = "below" if m.total < cutoff else "above"
        lines.append(
            f"You're {gap_str} marks {direction} last year's cutoff ({cutoff_str}, {category})."
        )

    if m.sections:
        # Find section with lowest score / max_score ratio
        valid_secs = [s for s in m.sections if s.max_score is not None and s.max_score > 0]
        if valid_secs:
            lowest_sec = min(valid_secs, key=lambda s: s.score / s.max_score)  # type: ignore[arg-type]
            s_str = _fmt_num(lowest_sec.score)
            sm_str = _fmt_num(lowest_sec.max_score)  # type: ignore[arg-type]
            lines.append(f"{lowest_sec.name} is where you can gain the most ({s_str}/{sm_str}).")

    return "\n".join(lines)
