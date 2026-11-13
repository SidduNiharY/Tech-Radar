import pytest
from pydantic import ValidationError

from techradar.schemas.pipeline import (
    CleanDoc,
    IntakeStep,
    ParseJob,
    ParseResult,
    ReaderOutput,
    Section,
    SourceSpec,
    TrustTier,
)

GOOD = {
    "summary": "RBI kept the repo rate unchanged.",
    "section": "economy",
    "exam_tags": ["bank"],
    "facts": [
        {"statement": "The repo rate stayed at 5.5%.", "subject": "repo rate", "value": "5.5%"}
    ],
    "four_questions": {
        "what_happened": "a",
        "why": "b",
        "what_changes": "c",
        "how_it_affects_me": "d",
    },
    "entities": ["RBI"],
}


def test_reader_output_valid_roundtrip():
    res = ReaderOutput.model_validate(GOOD)
    assert res.section is Section.ECONOMY
    assert res.summary == "RBI kept the repo rate unchanged."


def test_extra_field_rejected():
    with pytest.raises(ValidationError):
        ReaderOutput.model_validate({**GOOD, "tool_call": {"name": "x"}})


def test_summary_too_long_rejected():
    with pytest.raises(ValidationError):
        ReaderOutput.model_validate({**GOOD, "summary": "a" * 601})


@pytest.mark.parametrize(
    "patch",
    [
        {"summary": "see https://evil.example"},
        {"entities": ["![x](y)"]},
        {"four_questions": {**GOOD["four_questions"], "why": "<img src=x>"}},
        {"facts": [{"statement": "[click here](http://evil.com)", "subject": "sub", "value": "v"}]},
    ],
)
def test_links_rejected_everywhere(patch):
    with pytest.raises(ValidationError):
        ReaderOutput.model_validate({**GOOD, **patch})


def test_unknown_section_rejected():
    with pytest.raises(ValidationError):
        ReaderOutput.model_validate({**GOOD, "section": "gossip"})


def test_reader_output_accepts_devanagari_and_telugu():
    assert ReaderOutput.model_validate({**GOOD, "summary": "भारत में दरें स्थिर रहीं। తెలుగు వార్త."})


def test_parse_job_rejects_path_traversal_raw_name():
    with pytest.raises(ValidationError):
        ParseJob(
            job_id="a" * 32,
            kind="page",
            raw_name="../../etc/passwd",
            url="https://x",
            source_id=1,
            raw_item_id=None,
        )


def test_exam_tags_max_three_and_unique():
    with pytest.raises(ValidationError):
        ReaderOutput.model_validate({**GOOD, "exam_tags": ["gate", "bank", "ssc_cgl", "gate"]})


def test_parse_job_origin_defaults_to_fetch():
    job = ParseJob(
        job_id="a" * 32,
        kind="page",
        raw_name="b" * 64 + ".html",
        url="https://x",
        source_id=1,
        raw_item_id=None,
    )
    assert job.origin == "fetch"


def test_intake_verdict_rejects_unknown_step():
    with pytest.raises(ValidationError):
        IntakeStep(name="magic", outcome="ok", detail="")


def test_source_spec_valid():
    spec = SourceSpec(
        name="PIB Releases",
        url="https://pib.gov.in/rss.xml",
        section=Section.INDIA,
        trust_tier=TrustTier.OFFICIAL,
    )
    assert spec.interval_min == 120
    assert not spec.enabled


def test_parse_result_structure():
    doc = CleanDoc(
        url="https://example.com/test",
        title="Test Doc",
        text="Sample clean text content",
        lang="en",
        truncated=False,
    )
    res = ParseResult(
        job_id="a" * 32,
        kind="page",
        status="ok",
        doc=doc,
        entries=[],
    )
    assert res.status == "ok"
    assert res.doc.lang == "en"


def test_parse_job_purpose_defaults_to_news():
    job = ParseJob(
        job_id="a" * 32,
        kind="pdf",
        raw_name="b" * 64 + ".pdf",
        url="https://example.com/test.pdf",
        source_id=0,
        raw_item_id=None,
    )
    assert job.purpose == "news"


def test_parse_result_purpose_defaults_to_news():
    res = ParseResult(
        job_id="a" * 32,
        kind="page",
        status="ok",
    )
    assert res.purpose == "news"


def test_parse_job_part_fields():
    j = ParseJob(
        job_id="a" * 32,
        kind="pdf",
        raw_name="b" * 64 + ".pdf",
        url="library:x",
        source_id=0,
        raw_item_id=None,
        origin="library",
        purpose="library",
        mode="part",
        page_start=26,
        page_end=50,
        doc_id=1,
        part_id=2,
    )
    assert (j.page_start, j.page_end) == (26, 50)
    assert (j.doc_id, j.part_id, j.mode) == (1, 2, "part")


def test_parse_job_mode_defaults_to_full():
    j = ParseJob(job_id="a" * 32, kind="pdf", raw_name="b" * 64 + ".pdf", url="u", source_id=0)
    assert j.mode == "full"
    assert j.page_start is None and j.doc_id is None and j.part_id is None


def test_raw_name_accepts_video_extension():
    ParseJob(
        job_id="a" * 32,
        kind="video",
        raw_name="c" * 64 + ".mp4",
        url="library:v",
        source_id=0,
        raw_item_id=None,
    )


@pytest.mark.parametrize(
    "kind,ext",
    [
        ("docx", "docx"),
        ("epub", "epub"),
        ("audio", "mp3"),
        ("audio", "m4a"),
        ("video", "mkv"),
        ("image", "png"),
        ("image", "jpeg"),
    ],
)
def test_new_kinds_and_extensions(kind, ext):
    ParseJob(job_id="a" * 32, kind=kind, raw_name="d" * 64 + "." + ext, url="u", source_id=0)


def test_raw_name_rejects_unknown_extension():
    with pytest.raises(ValidationError):
        ParseJob(job_id="a" * 32, kind="pdf", raw_name="d" * 64 + ".exe", url="u", source_id=0)


def test_parse_job_rejects_bad_mode():
    with pytest.raises(ValidationError):
        ParseJob(
            job_id="a" * 32,
            kind="pdf",
            raw_name="b" * 64 + ".pdf",
            url="u",
            source_id=0,
            mode="bogus",
        )
