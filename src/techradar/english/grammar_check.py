from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, ConfigDict

from techradar.practice.grammar import GrammarRule

RULE_MAP: dict[str, GrammarRule] = {
    "EN_A_VS_AN": GrammarRule.ARTICLES,
    "A_UNCOUNTABLE": GrammarRule.ARTICLES,
    "THE_SUPERLATIVE": GrammarRule.ARTICLES,
    "HE_VERB_AGR": GrammarRule.SUBJECT_VERB,
    "PERS_PRONOUN_AGREEMENT": GrammarRule.PRONOUNS,
    "PRP_": GrammarRule.PRONOUNS,
    "TENSE_": GrammarRule.TENSE,
    "PREPOSITION_": GrammarRule.PREPOSITIONS,
    "MODIFIERS_": GrammarRule.MODIFIERS,
    "PARALLELISM_": GrammarRule.PARALLELISM,
    "VOICE_": GrammarRule.VOICE,
    "NARRATION_": GrammarRule.NARRATION,
    "CONJUNCTIONS_": GrammarRule.CONJUNCTIONS,
}


def _map_rule_id(rule_id: str) -> GrammarRule | None:
    if rule_id in RULE_MAP:
        return RULE_MAP[rule_id]
    for prefix, rule in RULE_MAP.items():
        if rule_id.startswith(prefix):
            return rule
    return None


class GrammarIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str
    message: str
    offset: int
    length: int
    replacements: list[str]
    category: str
    rule: GrammarRule | None = None


async def check_grammar(
    client: httpx.AsyncClient,
    base_url: str,
    text: str,
    language: str = "en-GB",
) -> list[GrammarIssue]:
    """Check text grammar via LanguageTool API endpoint."""
    capped_text = text[:5000]
    url = f"{base_url.rstrip('/')}/v2/check"
    resp = await client.post(
        url,
        data={"text": capped_text, "language": language},
    )
    resp.raise_for_status()
    data: dict[str, Any] = resp.json()

    issues: list[GrammarIssue] = []
    for match in data.get("matches", []):
        r_info = match.get("rule", {})
        rid = r_info.get("id", "")
        msg = str(match.get("message", ""))[:300]
        off = int(match.get("offset", 0))
        length = int(match.get("length", 0))
        repls = [str(r.get("value", "")) for r in match.get("replacements", [])][:3]
        cat = str(r_info.get("category", {}).get("name", "Grammar"))
        rule = _map_rule_id(rid)

        issues.append(
            GrammarIssue(
                rule_id=rid,
                message=msg,
                offset=off,
                length=length,
                replacements=repls,
                category=cat,
                rule=rule,
            )
        )
    return issues


def top_rule(issues: Sequence[GrammarIssue]) -> GrammarRule | None:
    """Find the most frequently violated mapped GrammarRule."""
    mapped_rules = [i.rule for i in issues if i.rule is not None]
    if not mapped_rules:
        return None
    counts = Counter(mapped_rules)
    return counts.most_common(1)[0][0]


class GrammarChecker(Protocol):
    """What the voice and writing code need from LanguageTool; tests pass a fake."""

    async def check(self, text: str) -> list[GrammarIssue]: ...


class LanguageToolClient:
    """The LanguageTool container (owner-only, `tools` network) behind `GrammarChecker`."""

    def __init__(self, client: httpx.AsyncClient, base_url: str, language: str = "en-GB") -> None:
        self._client = client
        self._base_url = base_url
        self._language = language

    async def check(self, text: str) -> list[GrammarIssue]:
        return await check_grammar(self._client, self._base_url, text, self._language)
