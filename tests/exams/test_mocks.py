from __future__ import annotations

from techradar.exams.mocks import (
    MockScore,
    SectionScore,
    extract_mock,
    extract_mock_regex,
    numbers_present,
    render_mock_reply,
)
from tests.fakes import FakeCompleter

MOCK_FIXTURE_TEXT = "Total Score: 123.5 / 200\nQuantitative Aptitude 32.5 / 50\nEnglish 41 / 50"


def test_extract_mock_regex_fixture():
    m = extract_mock_regex(MOCK_FIXTURE_TEXT)
    assert m is not None
    assert m.total == 123.5
    assert m.max_total == 200.0
    assert len(m.sections) == 2
    assert m.sections[0].name == "Quantitative Aptitude"
    assert m.sections[0].score == 32.5
    assert m.sections[0].max_score == 50.0
    assert m.sections[1].name == "English"
    assert m.sections[1].score == 41.0
    assert m.sections[1].max_score == 50.0


def test_numbers_must_appear_in_ocr():
    # 150 is not in the text
    score_invented = MockScore(exam="SSC", total=150.0, max_total=200.0, sections=[])
    assert not numbers_present(score_invented, "Total Score: 123.5 / 200")

    # 123.5 and 200 are in the text
    score_valid = MockScore(exam="SSC", total=123.5, max_total=200.0, sections=[])
    assert numbers_present(score_valid, "Total Score: 123.5 / 200")


async def test_model_fallback_rejected_when_numbers_invented():
    completer = FakeCompleter(['{"exam":"SSC","total":150,"max_total":200,"sections":[]}'])
    assert await extract_mock(completer, "garbled 123.5 / 200") is None


async def test_model_fallback_accepted_when_numbers_present():
    completer = FakeCompleter(['{"exam":"SSC","total":123.5,"max_total":200,"sections":[]}'])
    m = await extract_mock(completer, "unstructured scorecard text with 123.5 and 200 total")
    assert m is not None
    assert m.total == 123.5


def test_render_mock_reply_with_cutoff():
    m = MockScore(
        exam="SSC CGL",
        total=123.5,
        max_total=200.0,
        sections=[
            SectionScore(name="Quantitative Aptitude", score=20.0, max_score=50.0),
            SectionScore(name="English", score=40.0, max_score=50.0),
        ],
    )
    reply = render_mock_reply(m, 136.0, "General")
    lines = reply.splitlines()
    assert lines[0] == "📊 Mock saved: 123.5/200."
    assert lines[1] == "You're 12.5 marks below last year's cutoff (136.0, General)."
    assert lines[2] == "Quantitative Aptitude is where you can gain the most (20/50)."


def test_render_mock_reply_above_cutoff():
    m = MockScore(exam="SSC CGL", total=145.0, max_total=200.0, sections=[])
    reply = render_mock_reply(m, 136.0, "General")
    assert "You're 9.0 marks above last year's cutoff (136.0, General)." in reply


def test_extract_mock_regex_attempted_and_correct_belong_to_the_section_above():
    m = extract_mock_regex(
        "Total Score: 60 / 100\nQuantitative Aptitude 32.5 / 50\nAttempted: 20\nCorrect: 13\n"
        "English 27.5 / 50\nAttempted 22\nCorrect 15"
    )
    assert m is not None
    assert (m.sections[0].attempted, m.sections[0].correct) == (20, 13)
    assert (m.sections[1].attempted, m.sections[1].correct) == (22, 15)


async def test_ocr_text_reaches_the_model_inside_untrusted_markers():
    completer = FakeCompleter(['{"exam":"SSC","total":123.5,"max_total":200,"sections":[]}'])
    assert await extract_mock(completer, "garbled 123.5 / 200") is not None
    user = completer.calls[0]["messages"][1]["content"]
    assert "<<UNTRUSTED " in user
