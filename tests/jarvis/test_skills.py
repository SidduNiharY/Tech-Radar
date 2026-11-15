from __future__ import annotations

from techradar.jarvis.skill_impl import (
    speak_briefing,
    speak_daily_plan,
    speak_exam_status,
    speak_help,
    speak_library_summary,
    speak_practice_due,
    speak_search_result,
    speak_system_status,
    speak_voice_feedback,
    speak_world_update,
)


def test_speak_briefing():
    # Multiple highlights
    spoken = speak_briefing(
        "Markets rallied today.",
        ["Tech sector rose 2%", "Inflation dropped to 3.1%"],
    )
    assert "Markets rallied today." in spoken
    assert "Key highlights:" in spoken
    assert "Tech sector rose 2%" in spoken
    assert "Inflation dropped to 3.1%" in spoken

    # Single highlight
    spoken_single = speak_briefing("Quick summary.", ["Only one highlight"])
    assert "Quick summary." in spoken_single
    assert "Key highlight: Only one highlight." in spoken_single

    # No highlights
    spoken_no_hl = speak_briefing("Only summary here.", [])
    assert spoken_no_hl == "Only summary here."

    # Empty summary with highlights
    spoken_empty_sum = speak_briefing("", ["Key event happening"])
    assert spoken_empty_sum == "Key highlight: Key event happening."

    # All empty
    spoken_empty = speak_briefing("   ", [])
    assert "no briefing updates" in spoken_empty.lower()


def test_speak_practice_due():
    # Both zero/false
    assert "all caught up" in speak_practice_due(0, False).lower()
    assert "all caught up" in speak_practice_due(-2, False).lower()

    # Cards due and quiz ready (singular)
    spoken_1_quiz = speak_practice_due(1, True)
    assert "1 flashcard due" in spoken_1_quiz
    assert "daily quiz is ready" in spoken_1_quiz

    # Cards due and quiz ready (plural)
    spoken_5_quiz = speak_practice_due(5, True)
    assert "5 flashcards due" in spoken_5_quiz
    assert "daily quiz is ready" in spoken_5_quiz

    # Cards due, no quiz
    spoken_cards_only = speak_practice_due(3, False)
    assert "3 flashcards due" in spoken_cards_only
    assert "no quiz is scheduled" in spoken_cards_only.lower()

    # No cards, quiz ready
    spoken_quiz_only = speak_practice_due(0, True)
    assert "no flashcards due" in spoken_quiz_only.lower()
    assert "daily quiz is ready" in spoken_quiz_only


def test_speak_exam_status():
    # No exam scheduled
    no_exam = speak_exam_status(None, 65.0)
    assert "no upcoming exam" in no_exam.lower()
    assert "65%" in no_exam

    # Decimal coverage
    decimal_cov = speak_exam_status(None, 72.5)
    assert "72.5%" in decimal_cov

    # Exam today
    today = speak_exam_status(0, 100.0)
    assert "exam is today" in today.lower()
    assert "100%" in today

    # 1 day left (singular)
    one_day = speak_exam_status(1, 85.0)
    assert "1 day left" in one_day
    assert "85%" in one_day

    # Multiple days left (plural)
    many_days = speak_exam_status(15, 60.0)
    assert "15 days left" in many_days
    assert "60%" in many_days

    # Passed exam
    passed = speak_exam_status(-2, 50.0)
    assert "passed 2 days ago" in passed.lower()


def test_speak_voice_feedback():
    # Feedback with top fix
    spoken = speak_voice_feedback(85.0, "reduce filler words")
    assert "85" in spoken
    assert "reduce filler words" in spoken

    # Feedback with decimal score and no fix needed
    spoken_no_fix = speak_voice_feedback(92.5, None)
    assert "92.5" in spoken_no_fix
    assert "no critical pronunciation fixes" in spoken_no_fix.lower()

    # Empty string top fix
    spoken_empty_fix = speak_voice_feedback(90.0, "   ")
    assert "90" in spoken_empty_fix
    assert "no critical pronunciation fixes" in spoken_empty_fix.lower()


def test_speak_world_update():
    # Headline and series change
    spoken = speak_world_update("Central Bank holds rates", "10-year yield fell 5 bps")
    assert "Central Bank holds rates" in spoken
    assert "10-year yield fell 5 bps" in spoken

    # Headline only
    spoken_headline_only = speak_world_update("Treaty signed in Geneva", None)
    assert "Treaty signed in Geneva" in spoken_headline_only
    assert "indicator trend" not in spoken_headline_only.lower()

    # Empty headline
    spoken_empty = speak_world_update("", None)
    assert "no world updates" in spoken_empty.lower()


def test_speak_library_summary():
    # All fields provided
    spoken = speak_library_summary(
        "Operating Systems",
        "Virtual Memory",
        "Page tables translate virtual addresses to physical frames.",
    )
    assert "Operating Systems" in spoken
    assert "Virtual Memory" in spoken
    assert "Page tables translate" in spoken

    # Book and key idea only
    spoken_book_only = speak_library_summary("Clean Code", "", "Functions should do one thing.")
    assert "Clean Code" in spoken_book_only
    assert "Functions should do one thing." in spoken_book_only

    # Chapter only
    spoken_chap_only = speak_library_summary(
        "", "Concurrency", "Race conditions occur on shared state."
    )
    assert "Concurrency" in spoken_chap_only
    assert "Race conditions" in spoken_chap_only

    # Key idea only
    spoken_idea_only = speak_library_summary("", "", "Knowledge is power.")
    assert "Knowledge is power." in spoken_idea_only

    # All empty
    spoken_none = speak_library_summary("", "", "")
    assert "no summary available" in spoken_none.lower()


def test_speak_search_result():
    # Found chunk
    spoken = speak_search_result("Consistent hashing minimizes rehashing overhead.")
    assert "Here is what I found:" in spoken
    assert "Consistent hashing minimizes rehashing overhead." in spoken

    # Empty chunk
    spoken_empty = speak_search_result("   ")
    assert "could not find any relevant information" in spoken_empty.lower()


def test_speak_daily_plan():
    # Multiple goals
    spoken = speak_daily_plan(
        ["60 min Operating Systems", "30 min English Speaking", "10 Flashcards"]
    )
    assert "3 goals planned for today" in spoken
    assert "1, 60 min Operating Systems" in spoken
    assert "2, 30 min English Speaking" in spoken
    assert "3, 10 Flashcards" in spoken

    # 1 goal
    spoken_one = speak_daily_plan(["Review DBMS syllabus"])
    assert "1 goal planned for today" in spoken_one
    assert "Review DBMS syllabus" in spoken_one

    # No goals
    spoken_zero = speak_daily_plan([])
    assert "no study goals scheduled" in spoken_zero.lower()


def test_speak_system_status():
    # OK status
    spoken_ok = speak_system_status(24.0, True)
    assert "all systems are operational" in spoken_ok.lower()
    assert "24 hours" in spoken_ok

    # Degraded status with decimal uptime
    spoken_degraded = speak_system_status(1.5, False)
    assert "degradation detected" in spoken_degraded.lower()
    assert "1.5 hours" in spoken_degraded

    # Singular hour
    spoken_one_hour = speak_system_status(1.0, True)
    assert "1 hour" in spoken_one_hour


def test_speak_help():
    spoken = speak_help()
    assert "Jarvis" in spoken
    assert "daily briefing" in spoken
    assert "flashcards" in spoken
    assert "exam" in spoken
    assert "plan" in spoken
    assert "library" in spoken
