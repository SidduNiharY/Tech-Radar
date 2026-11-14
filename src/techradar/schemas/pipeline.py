from __future__ import annotations

import re
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator


class Section(StrEnum):
    INDIA = "india"
    WORLD = "world"
    POLITICS = "politics"
    ECONOMY = "economy"
    TECH = "tech"
    SCIENCE = "science"
    EXAMS = "exams"
    DAILY_LIFE = "daily_life"


class ExamTag(StrEnum):
    GATE = "gate"
    SSC_CGL = "ssc_cgl"
    BANK = "bank"


class TrustTier(StrEnum):
    OFFICIAL = "official"
    NEWS = "news"
    COMMUNITY = "community"


JobKind = Literal["feed", "page", "pdf", "md", "docx", "epub", "video", "audio", "image"]
ParseStatus = Literal[
    "ok", "empty", "too_large", "timeout", "error", "unsupported", "quarantined", "rejected"
]
Origin = Literal["fetch", "telegram", "library", "upload", "clipping", "pack"]
Verdict = Literal["pass", "flag", "quarantine", "reject"]

_LINK_RE = re.compile(r"(?i)(https?://|www\.|\]\(|!\[|<\s*(a|img|script|iframe)\b|data:)")


def reject_links(value: str) -> str:
    if _LINK_RE.search(value):
        raise ValueError("links are not allowed")
    return value


NoLinks = Annotated[str, AfterValidator(reject_links)]


class BasePipelineModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceSpec(BasePipelineModel):
    name: Annotated[str, Field(min_length=1, max_length=80)]
    url: str
    section: Section
    trust_tier: TrustTier
    interval_min: Annotated[int, Field(ge=30, le=1440)] = 120
    enabled: bool = False


class ParseJob(BasePipelineModel):
    job_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
    kind: JobKind
    raw_name: Annotated[
        str,
        Field(
            pattern=r"^[0-9a-f]{64}\.(xml|html|pdf|md|docx|epub|mp4|mkv|webm|mov|mp3|m4a|wav|ogg|png|jpg|jpeg)$"
        ),
    ]
    url: str
    source_id: int
    raw_item_id: int | None = None
    origin: Origin = "fetch"
    purpose: Literal["news", "library", "clipping"] = "news"
    # For purpose="library", raw_name is relative to /data/library/originals.
    mode: Literal["full", "probe", "part", "media"] = "full"
    page_start: int | None = None
    page_end: int | None = None
    doc_id: int | None = None
    part_id: int | None = None
    # Media segments (seconds); each media job covers one segment so it stays
    # within the parser's 120 s timeout (SEC-06).
    ts_start: Annotated[float, Field(ge=0, le=14_460)] | None = None
    ts_end: Annotated[float, Field(gt=0, le=14_460)] | None = None
    # Set only by the worker when the owner released this doc from quarantine (a released
    # QuarantineItem exists for it): the gateway then turns quarantine steps into flags;
    # rejects stay rejects (SEC-14). Never derived from file content.
    owner_released: Annotated[bool, Field(strict=True)] = False


class FeedEntry(BasePipelineModel):
    title: Annotated[str, Field(max_length=300)]
    link: Annotated[str, Field(max_length=2000)]
    published: datetime | None = None
    summary: Annotated[str, Field(max_length=2000)] = ""


class CleanDoc(BasePipelineModel):
    url: str
    title: Annotated[str, Field(max_length=300)]
    text: Annotated[str, Field(min_length=1, max_length=100_000)]
    lang: Literal["en", "hi", "te", "other"]
    truncated: bool = False


class IntakeStep(BasePipelineModel):
    name: Literal[
        "source",
        "size",
        "type",
        "structure",
        "antivirus",
        "rules",
        "rebuild",
        "text",
        "injection",
        "links",
    ]
    outcome: Literal["ok", "flag", "quarantine", "reject", "skipped"]
    detail: Annotated[str, Field(max_length=200)] = ""


class IntakeVerdict(BasePipelineModel):
    verdict: Verdict
    steps: Annotated[list[IntakeStep], Field(max_length=12)]
    reasons: Annotated[list[Annotated[str, Field(max_length=120)]], Field(max_length=10)] = Field(
        default_factory=list
    )


class ParseResult(BasePipelineModel):
    job_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
    kind: JobKind
    status: ParseStatus
    purpose: Literal["news", "library", "clipping"] = "news"
    doc: CleanDoc | None = None
    entries: Annotated[list[FeedEntry], Field(max_length=200)] = Field(default_factory=list)
    intake: IntakeVerdict | None = None


class FourQuestions(BasePipelineModel):
    what_happened: Annotated[NoLinks, Field(min_length=1, max_length=400)]
    why: Annotated[NoLinks, Field(min_length=1, max_length=400)]
    what_changes: Annotated[NoLinks, Field(min_length=1, max_length=400)]
    how_it_affects_me: Annotated[NoLinks, Field(min_length=1, max_length=400)]


class FactClaim(BasePipelineModel):
    statement: Annotated[NoLinks, Field(min_length=1, max_length=240)]
    subject: Annotated[NoLinks, Field(min_length=1, max_length=120)]
    value: Annotated[NoLinks, Field(max_length=120)] | None = None


class ReaderOutput(BasePipelineModel):
    summary: Annotated[NoLinks, Field(min_length=1, max_length=600)]
    section: Section
    exam_tags: Annotated[list[ExamTag], Field(max_length=3)] = Field(default_factory=list)
    facts: Annotated[list[FactClaim], Field(max_length=8)] = Field(default_factory=list)
    four_questions: FourQuestions
    entities: Annotated[list[Annotated[NoLinks, Field(max_length=80)]], Field(max_length=10)] = (
        Field(default_factory=list)
    )

    @field_validator("exam_tags")
    @classmethod
    def unique_exam_tags(cls, v: list[ExamTag]) -> list[ExamTag]:
        if len(v) != len(set(v)):
            raise ValueError("exam_tags must be unique")
        return v


class CheckerVerdict(BasePipelineModel):
    supported: bool
    quote: Annotated[str, Field(max_length=300)] = ""
