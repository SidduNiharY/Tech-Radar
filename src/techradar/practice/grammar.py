# WIRING(claude): worker/tasks.py needs grammar_job and vocab_job
from __future__ import annotations

import logging
import re
from collections.abc import Iterator, Sequence
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from techradar.db.models import GrammarItem as DBGrammarItem
from techradar.llm.client import Completer, complete_json
from techradar.llm.roles import Role

logger = logging.getLogger(__name__)

_LINK_RE = re.compile(r"(?i)(https?://|www\.|\]\(|!\[|<\s*(a|img|script|iframe)\b|data:)")


def _contains_link(text: str) -> bool:
    """Returns True if the text contains URLs or link markdown/HTML patterns."""
    return bool(_LINK_RE.search(text))


def reject_links(value: str) -> str:
    """Rejects strings that contain link markdown, HTML or URLs (SEC-20)."""
    if _LINK_RE.search(value):
        raise ValueError("links are not allowed")
    return value


NoLinks = Annotated[str, AfterValidator(reject_links)]


class GrammarRule(StrEnum):
    """Grammar rules evaluated in daily practice sets."""

    TENSE = "tense"
    ARTICLES = "articles"
    PREPOSITIONS = "prepositions"
    SUBJECT_VERB = "subject_verb"
    PRONOUNS = "pronouns"
    MODIFIERS = "modifiers"
    CONJUNCTIONS = "conjunctions"
    PARALLELISM = "parallelism"
    VOICE = "voice"
    NARRATION = "narration"

    @classmethod
    def _missing_(cls, value: object) -> GrammarRule | None:
        if isinstance(value, str):
            val_lower = value.lower()
            for member in cls:
                if member.value == val_lower or member.name.lower() == val_lower:
                    return member
        return None


class GrammarItem(BaseModel):
    """Checked grammar practice item verified by two independent models."""

    kind: Literal["error_spotting", "sentence_improvement", "fill_blank"]
    prompt: Annotated[
        str,
        Field(min_length=10, max_length=300),
        AfterValidator(reject_links),
    ]
    options: list[
        Annotated[
            str,
            Field(min_length=1, max_length=120),
            AfterValidator(reject_links),
        ]
    ]
    answer_index: Annotated[int, Field(ge=0, le=3)]
    rule: GrammarRule
    explanation: Annotated[
        str,
        Field(max_length=400),
        AfterValidator(reject_links),
    ] = ""

    @field_validator("options")
    @classmethod
    def validate_options(cls, v: list[str]) -> list[str]:
        if len(v) != 4:
            raise ValueError("options must contain exactly 4 items")
        if len(set(v)) != 4:
            raise ValueError("options must be unique")
        return v

    @field_validator("answer_index")
    @classmethod
    def validate_answer_index(cls, v: int) -> int:
        if v < 0 or v > 3:
            raise ValueError("answer_index must be between 0 and 3")
        return v


class _GrammarCheckerAnswer(BaseModel):
    answer_index: int


async def make_grammar_item(
    completer: Completer,
    rule: GrammarRule,
    kind: str,
) -> GrammarItem | None:
    """Worker model writes grammar question; checker model verifies answer_index.

    Returns None on checker disagreement, schema violation, or generation error.
    """
    rule_enum = GrammarRule(rule) if isinstance(rule, str) else rule

    worker_system = (
        "You are an English exam question creator for competitive exams (GATE, SSC, Bank PO). "
        f"Generate a '{kind}' grammar question testing the rule '{rule_enum.value}'. "
        "Provide exactly 4 unique options, a 0-based answer_index (0 to 3), and an explanation. "
        "Do not include any URLs, web addresses, or markdown links."
    )
    worker_user = (
        f"Create a single '{kind}' grammar question testing rule: {rule_enum.value}.\n"
        "Ensure prompt is between 10 and 300 characters, options are exactly 4 unique choices, "
        "and explanation is concise."
    )

    try:
        item = await complete_json(
            completer,
            Role.WORKER,
            worker_system,
            worker_user,
            GrammarItem,
            attempts=1,
        )
    except Exception as exc:
        logger.debug("Worker failed to generate grammar item: %s", exc)
        return None

    # Checker verifies the answer independently
    options_text = "\n".join(f"{idx}: {opt}" for idx, opt in enumerate(item.options))
    checker_system = (
        "You are an independent English grammar checker. "
        "Analyze the provided question and options, and return the index (0, 1, 2, or 3) "
        "of the correct answer."
    )
    checker_user = (
        f"Question Prompt:\n{item.prompt}\n\n"
        f"Options:\n{options_text}\n\n"
        f"Target Rule: {item.rule.value}\n\n"
        "Return the 0-based index of the correct option as JSON: {'answer_index': <int>}."
    )

    try:
        checker_ans = await complete_json(
            completer,
            Role.CHECKER,
            checker_system,
            checker_user,
            _GrammarCheckerAnswer,
            attempts=1,
        )
    except Exception as exc:
        logger.debug("Checker failed to verify grammar item: %s", exc)
        return None

    if checker_ans.answer_index != item.answer_index:
        logger.info(
            "Grammar checker disagreed: worker=%d, checker=%d",
            item.answer_index,
            checker_ans.answer_index,
        )
        return None

    return item


class GrammarResult(BaseModel):
    """Result of running daily grammar job."""

    items_created: int = 0
    items: list[GrammarItem] = Field(default_factory=list)
    skipped_reason: str | None = None


async def run_grammar(
    session: AsyncSession,
    completer: Completer,
    *,
    now: datetime,
    limit: int = 10,
) -> GrammarResult:
    """Body of grammar_job. Generates verified grammar questions and persists to database."""
    created_items: list[GrammarItem] = []
    rules = list(GrammarRule)
    kinds: list[Literal["error_spotting", "sentence_improvement", "fill_blank"]] = [
        "fill_blank",
        "sentence_improvement",
        "error_spotting",
    ]

    rule_idx = 0
    kind_idx = 0
    attempts = 0
    max_attempts = limit * 4

    while len(created_items) < limit and attempts < max_attempts:
        rule = rules[rule_idx % len(rules)]
        kind = kinds[kind_idx % len(kinds)]
        rule_idx += 1
        kind_idx += 1
        attempts += 1

        try:
            item = await make_grammar_item(completer, rule, kind)
        except IndexError, StopIteration:
            break
        except Exception as exc:
            logger.debug("Grammar item creation attempt encountered error: %s", exc)
            item = None

        if item is not None:
            created_items.append(item)
            db_item = DBGrammarItem(
                kind=item.kind,
                prompt=item.prompt,
                options=item.options,
                answer_index=item.answer_index,
                rule=str(item.rule.value if isinstance(item.rule, GrammarRule) else item.rule),
                explanation=item.explanation,
                created_at=now,
            )
            session.add(db_item)

    if created_items:
        await session.flush()

    return GrammarResult(
        items_created=len(created_items),
        items=created_items,
        skipped_reason="no_agreed_items" if not created_items else None,
    )


# ---------------------------------------------------------------------------
# Backward Compatibility for bot commands and quizzes
# ---------------------------------------------------------------------------


class GrammarQuestion(BaseModel):
    id: str
    sentence_with_blank: str
    options: list[str]
    correct_index: int
    rule_explanation: str
    category: str

    def is_valid(self) -> bool:
        return validate_grammar_question(self)


def validate_grammar_question(q: GrammarQuestion) -> bool:
    """Verifies that a grammar question satisfies all schema and security constraints:

    - Exactly 4 options
    - All 4 options are unique
    - correct_index is within [0, 3]
    - rule_explanation is non-empty
    - rule_explanation contains NO http/https links (SEC-20)
    """
    if not isinstance(q.options, list) or len(q.options) != 4:
        return False
    if len(set(q.options)) != 4:
        return False
    if q.correct_index not in (0, 1, 2, 3):
        return False
    if not q.rule_explanation or not q.rule_explanation.strip():
        return False
    if _contains_link(q.rule_explanation):
        return False
    if not q.sentence_with_blank or not q.sentence_with_blank.strip():
        return False
    if _contains_link(q.sentence_with_blank):
        return False
    return True


_DEFAULT_GRAMMAR_POOL: list[GrammarQuestion] = [
    GrammarQuestion(
        id="gq_01",
        sentence_with_blank="Neither the manager nor the employees ___ aware of the delay.",
        options=["was", "were", "is", "are being"],
        correct_index=1,
        rule_explanation=(
            "When subjects are connected by 'neither... nor', the verb agrees "
            "with the closer subject ('employees', plural)."
        ),
        category="subject-verb-agreement",
    ),
    GrammarQuestion(
        id="gq_02",
        sentence_with_blank="Each of the participants ___ received a certificate of completion.",
        options=["have", "has", "are", "were"],
        correct_index=1,
        rule_explanation=(
            "'Each' is a singular indefinite pronoun and requires a singular verb ('has')."
        ),
        category="subject-verb-agreement",
    ),
    GrammarQuestion(
        id="gq_03",
        sentence_with_blank="By the time the train arrived, we ___ at the station for two hours.",
        options=["had been waiting", "have waited", "waited", "are waiting"],
        correct_index=0,
        rule_explanation=(
            "Past perfect continuous indicates an action that was ongoing "
            "up until another event in the past."
        ),
        category="tenses",
    ),
    GrammarQuestion(
        id="gq_04",
        sentence_with_blank="She ___ in this tech firm since 2021.",
        options=["works", "worked", "has been working", "is working"],
        correct_index=2,
        rule_explanation=(
            "Present perfect continuous is used with 'since' for actions that began "
            "in the past and continue into the present."
        ),
        category="tenses",
    ),
    GrammarQuestion(
        id="gq_05",
        sentence_with_blank="The committee will abide ___ the guidelines established by the board.",
        options=["with", "by", "to", "at"],
        correct_index=1,
        rule_explanation=(
            "The phrasal verb 'abide by' means to conform to or respect a rule or decision."
        ),
        category="prepositions",
    ),
    GrammarQuestion(
        id="gq_06",
        sentence_with_blank="He is proficient ___ Python programming and distributed systems.",
        options=["in", "at", "with", "for"],
        correct_index=0,
        rule_explanation=(
            "The adjective 'proficient' is conventionally paired with the preposition 'in'."
        ),
        category="prepositions",
    ),
    GrammarQuestion(
        id="gq_07",
        sentence_with_blank=(
            "She holds ___ degree in computer engineering from an accredited university."
        ),
        options=["a", "an", "the", "no article"],
        correct_index=0,
        rule_explanation=(
            "Use the indefinite article 'a' before singular countable nouns beginning with "
            "a consonant sound."
        ),
        category="articles",
    ),
    GrammarQuestion(
        id="gq_08",
        sentence_with_blank="Honesty is ___ best policy in public administration.",
        options=["a", "an", "the", "no article"],
        correct_index=2,
        rule_explanation=(
            "Superlative adjectives such as 'best' require the definite article 'the'."
        ),
        category="articles",
    ),
    GrammarQuestion(
        id="gq_09",
        sentence_with_blank=(
            "If she ___ harder during the semester, she would have cleared the examination."
        ),
        options=["had studied", "studied", "would study", "has studied"],
        correct_index=0,
        rule_explanation=(
            "Third conditional sentences take past perfect ('had studied') in the "
            "if-clause and 'would have' + past participle in the main clause."
        ),
        category="tenses",
    ),
    GrammarQuestion(
        id="gq_10",
        sentence_with_blank="The list of approved candidates ___ published on the notice board.",
        options=["were", "was", "are", "have been"],
        correct_index=1,
        rule_explanation=(
            "The subject is 'The list' (singular), which governs the singular verb 'was'."
        ),
        category="subject-verb-agreement",
    ),
    GrammarQuestion(
        id="gq_11",
        sentence_with_blank="He prevented the team ___ making a catastrophic deployment mistake.",
        options=["to", "from", "for", "with"],
        correct_index=1,
        rule_explanation="The verb 'prevent' governs the preposition 'from' followed by a gerund.",
        category="prepositions",
    ),
    GrammarQuestion(
        id="gq_12",
        sentence_with_blank="Copper is ___ useful metal in electrical wiring.",
        options=["a", "an", "the", "no article"],
        correct_index=0,
        rule_explanation=(
            "'Useful' starts with a 'y' consonant sound, so it takes the indefinite article 'a'."
        ),
        category="articles",
    ),
]


class GrammarQuizSession:
    """Generates and manages a daily 10-question grammar practice set."""

    def __init__(
        self,
        questions: Sequence[GrammarQuestion] | None = None,
        date_str: str | None = None,
    ) -> None:
        self._pool: list[GrammarQuestion] = (
            list(questions) if questions is not None else list(_DEFAULT_GRAMMAR_POOL)
        )
        self.date_str = date_str
        self.questions: list[GrammarQuestion] = self.generate_daily_set(date_str=date_str)

    def generate_daily_set(
        self,
        date_str: str | None = None,
        count: int = 10,
    ) -> list[GrammarQuestion]:
        """Generates a daily set of up to `count` validated grammar questions."""
        valid_pool = [q for q in self._pool if validate_grammar_question(q)]
        if not valid_pool:
            return []

        if date_str or self.date_str:
            seed_key = date_str or self.date_str or ""
            offset = sum(ord(c) for c in seed_key) % len(valid_pool)
            rotated = valid_pool[offset:] + valid_pool[:offset]
            chosen = rotated[:count]
        else:
            chosen = valid_pool[:count]

        self.questions = chosen
        return chosen

    def get_daily_questions(self) -> list[GrammarQuestion]:
        """Returns the current session's questions."""
        return self.questions

    def __len__(self) -> int:
        return len(self.questions)

    def __iter__(self) -> Iterator[GrammarQuestion]:
        return iter(self.questions)

    def __getitem__(self, index: int) -> GrammarQuestion:
        return self.questions[index]
