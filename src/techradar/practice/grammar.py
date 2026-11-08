from __future__ import annotations

import re
from collections.abc import Iterator, Sequence

from pydantic import BaseModel

_LINK_RE = re.compile(r"(?i)(https?://|www\.|\]\(|!\[|<\s*(a|img|script|iframe)\b|data:)")


def _contains_link(text: str) -> bool:
    """Returns True if the text contains URLs or link markdown/HTML patterns."""
    return bool(_LINK_RE.search(text))


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

        # If date_str is provided or set, pick deterministically based on hash
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
