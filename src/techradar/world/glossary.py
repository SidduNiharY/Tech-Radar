"""World understanding glossary module."""

import re
from typing import Final

from pydantic import BaseModel, Field


class GlossaryTerm(BaseModel):
    """Glossary term definition."""

    term: str
    category: str
    definition: str
    synonyms: list[str] = Field(default_factory=list)
    related_terms: list[str] = Field(default_factory=list)
    importance: float = 1.0


BASELINE_TERMS: Final[list[GlossaryTerm]] = [
    GlossaryTerm(
        term="Repo Rate",
        category="Economy",
        definition=(
            "The interest rate at which the central bank lends money to commercial "
            "banks in the event of any shortfall of funds."
        ),
        synonyms=["repurchase rate", "repurchase agreement rate"],
        related_terms=["Inflation", "GDP", "Fiscal Deficit"],
        importance=1.0,
    ),
    GlossaryTerm(
        term="GDP",
        category="Economy",
        definition=(
            "Gross Domestic Product; the total monetary or market value of all finished "
            "goods and services produced within a country in a specific time period."
        ),
        synonyms=["Gross Domestic Product"],
        related_terms=["Inflation", "Fiscal Deficit", "Repo Rate"],
        importance=1.0,
    ),
    GlossaryTerm(
        term="Inflation",
        category="Economy",
        definition=(
            "The rate of increase in prices of goods and services over a given period of time, "
            "reducing currency purchasing power."
        ),
        synonyms=["price inflation"],
        related_terms=["Repo Rate", "GDP", "Fiscal Deficit"],
        importance=1.0,
    ),
    GlossaryTerm(
        term="Fiscal Deficit",
        category="Economy",
        definition=(
            "The gap between the government's total expenditure and its total "
            "receipts excluding borrowings."
        ),
        synonyms=["budget deficit"],
        related_terms=["GDP", "Inflation"],
        importance=1.0,
    ),
    GlossaryTerm(
        term="RAG",
        category="Technology",
        definition=(
            "Retrieval-Augmented Generation; a technique that enriches large language model "
            "prompts with relevant retrieved knowledge from external datasets."
        ),
        synonyms=["Retrieval-Augmented Generation"],
        related_terms=["Transformer"],
        importance=1.0,
    ),
    GlossaryTerm(
        term="Transformer",
        category="Technology",
        definition=(
            "A neural network architecture based on self-attention mechanisms, widely used "
            "in state-of-the-art natural language processing and multimodal AI."
        ),
        synonyms=["Transformer Architecture"],
        related_terms=["RAG"],
        importance=1.0,
    ),
    GlossaryTerm(
        term="eBPF",
        category="Technology",
        definition=(
            "Extended Berkeley Packet Filter; a kernel technology enabling sandboxed "
            "programs to execute safely within the Linux kernel without kernel modification."
        ),
        synonyms=["Extended Berkeley Packet Filter"],
        related_terms=[],
        importance=1.0,
    ),
]

# Patterns for protected regions in Markdown:
# 1. Wiki links: [[...]]
# 2. Multiline code blocks: ```...```
# 3. Inline code spans: `...`
# 4. Standard markdown links: [...](...)
_PROTECTED_MD_PATTERN = re.compile(r"(\[\[.*?\]\]|```[\s\S]*?```|`[^`\n]*`|\[[^\]]*\]\([^)]*\))")


class WorldGlossary:
    """Glossary storing domain knowledge terms with lookup, search, and Markdown linking."""

    def __init__(self, load_baselines: bool = True) -> None:
        self._terms: dict[str, GlossaryTerm] = {}
        if load_baselines:
            for baseline in BASELINE_TERMS:
                self.add_term(baseline)

    @property
    def terms(self) -> dict[str, GlossaryTerm]:
        """Return shallow copy of all registered terms."""
        return dict(self._terms)

    def add_term(self, term: GlossaryTerm) -> None:
        """Add or update a term in the glossary."""
        self._terms[term.term.strip().lower()] = term

    def lookup(self, term_name: str) -> GlossaryTerm | None:
        """Look up a term case-insensitively by its name or registered synonyms."""
        key = term_name.strip().lower()
        if not key:
            return None
        if key in self._terms:
            return self._terms[key]
        for term in self._terms.values():
            if any(syn.strip().lower() == key for syn in term.synonyms):
                return term
        return None

    def search(self, query: str) -> list[GlossaryTerm]:
        """Search glossary terms by query string across names, synonyms, and definitions."""
        q = query.strip().lower()
        if not q:
            return []

        scored: list[tuple[int, float, GlossaryTerm]] = []
        for term in self._terms.values():
            term_lower = term.term.lower()
            score = 0
            if q == term_lower:
                score = 100
            elif q in term_lower:
                score = 80
            elif any(q == syn.lower() for syn in term.synonyms):
                score = 70
            elif any(q in syn.lower() for syn in term.synonyms):
                score = 60
            elif q == term.category.lower():
                score = 50
            elif q in term.category.lower():
                score = 40
            elif q in term.definition.lower():
                score = 30
            elif any(q in rel.lower() for rel in term.related_terms):
                score = 20

            if score > 0:
                scored.append((score, term.importance, term))

        scored.sort(key=lambda item: (-item[0], -item[1], item[2].term))
        return [term for _, _, term in scored]

    def link_terms_in_markdown(self, text: str) -> str:
        """Insert wiki-style cross-references [[term]] without corrupting existing links or code."""
        if not text or not self._terms:
            return text

        # Sort terms by length descending to match longer multi-word phrases first
        sorted_terms = sorted(self._terms.values(), key=lambda t: len(t.term), reverse=True)
        joined_pattern = "|".join(re.escape(t.term) for t in sorted_terms)
        term_regex = re.compile(rf"(?<!\w)({joined_pattern})(?!\w)", re.IGNORECASE)

        def _replace_terms(match: re.Match[str]) -> str:
            matched_raw = match.group(0)
            canonical = self.lookup(matched_raw)
            term_name = canonical.term if canonical else matched_raw
            return f"[[{term_name}]]"

        # Split around protected regions (existing [[...]], code blocks, hyperlinks)
        segments = _PROTECTED_MD_PATTERN.split(text)
        result: list[str] = []
        for index, segment in enumerate(segments):
            # Odd index indicates a captured protected region
            if index % 2 == 1:
                result.append(segment)
            else:
                result.append(term_regex.sub(_replace_terms, segment))

        return "".join(result)
