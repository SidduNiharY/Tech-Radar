from __future__ import annotations

from techradar.practice.grammar import (
    GrammarQuestion,
    GrammarQuizSession,
    validate_grammar_question,
)


def _make_sample_question(**kwargs) -> GrammarQuestion:
    defaults = {
        "id": "test_gq_1",
        "sentence_with_blank": "Neither the manager nor the employees ___ aware of the delay.",
        "options": ["was", "were", "is", "are being"],
        "correct_index": 1,
        "rule_explanation": "Verb agrees with closer plural subject 'employees'.",
        "category": "subject-verb-agreement",
    }
    defaults.update(kwargs)
    return GrammarQuestion(**defaults)


def test_grammar_question_four_options_requirement():
    # Exactly 4 options passes
    q_valid = _make_sample_question(options=["A", "B", "C", "D"])
    assert validate_grammar_question(q_valid) is True
    assert q_valid.is_valid() is True

    # 3 options fails
    q_three = _make_sample_question(options=["A", "B", "C"])
    assert validate_grammar_question(q_three) is False

    # 5 options fails
    q_five = _make_sample_question(options=["A", "B", "C", "D", "E"])
    assert validate_grammar_question(q_five) is False

    # Empty options fails
    q_empty = _make_sample_question(options=[])
    assert validate_grammar_question(q_empty) is False


def test_grammar_question_option_uniqueness():
    # Duplicate options fail
    q_dups = _make_sample_question(options=["was", "was", "were", "is"])
    assert validate_grammar_question(q_dups) is False

    # All unique options pass
    q_unique = _make_sample_question(options=["was", "were", "is", "are"])
    assert validate_grammar_question(q_unique) is True


def test_grammar_question_correct_index_boundaries():
    # Valid indices 0, 1, 2, 3
    for idx in range(4):
        q = _make_sample_question(correct_index=idx)
        assert validate_grammar_question(q) is True

    # Negative index fails
    q_neg = _make_sample_question(correct_index=-1)
    assert validate_grammar_question(q_neg) is False

    # Index >= 4 fails
    q_too_high = _make_sample_question(correct_index=4)
    assert validate_grammar_question(q_too_high) is False

    q_much_higher = _make_sample_question(correct_index=10)
    assert validate_grammar_question(q_much_higher) is False


def test_grammar_question_explanation_no_links():
    # Clean explanation passes
    q_clean = _make_sample_question(
        rule_explanation="Subject-verb agreement rule explains that the verb must match.",
    )
    assert validate_grammar_question(q_clean) is True

    # Empty explanation fails
    q_empty_exp = _make_sample_question(rule_explanation="")
    assert validate_grammar_question(q_empty_exp) is False

    q_whitespace_exp = _make_sample_question(rule_explanation="   ")
    assert validate_grammar_question(q_whitespace_exp) is False

    # HTTP link in explanation fails (SEC-20)
    q_http = _make_sample_question(
        rule_explanation="See explanation at http://grammar-rules.example.org/rule1",
    )
    assert validate_grammar_question(q_http) is False

    # HTTPS link in explanation fails (SEC-20)
    q_https = _make_sample_question(
        rule_explanation="Check https://rules.internal.net/grammar for details.",
    )
    assert validate_grammar_question(q_https) is False

    # WWW link in explanation fails (SEC-20)
    q_www = _make_sample_question(
        rule_explanation="Refer to www.rules.org for more information.",
    )
    assert validate_grammar_question(q_www) is False


def test_grammar_question_sentence_blank_required():
    q_no_blank = _make_sample_question(sentence_with_blank="")
    assert validate_grammar_question(q_no_blank) is False

    q_link_in_sentence = _make_sample_question(
        sentence_with_blank="Visit https://phishing.site ___ complete test.",
    )
    assert validate_grammar_question(q_link_in_sentence) is False


def test_grammar_quiz_session_generation():
    session = GrammarQuizSession()

    # Default session generates exactly 10 questions
    questions = session.generate_daily_set()
    assert len(questions) == 10
    assert len(session) == 10
    assert len(session.questions) == 10
    assert len(session.get_daily_questions()) == 10

    # All generated questions in the daily set must be valid
    for q in questions:
        assert validate_grammar_question(q) is True
        assert len(q.options) == 4
        assert 0 <= q.correct_index <= 3
        assert "___" in q.sentence_with_blank
        assert len(q.rule_explanation) > 0
        assert q.category in {
            "subject-verb-agreement",
            "tenses",
            "prepositions",
            "articles",
        }

    # Can access by index and iterate
    assert session[0] == questions[0]
    items = list(session)
    assert len(items) == 10


def test_grammar_quiz_session_custom_pool():
    # Session with custom provided pool
    custom_pool = [
        _make_sample_question(
            id=f"custom_{i}",
            sentence_with_blank=f"Sentence {i} ___ here.",
            options=[f"opt_{i}_a", f"opt_{i}_b", f"opt_{i}_c", f"opt_{i}_d"],
            correct_index=i % 4,
        )
        for i in range(12)
    ]
    session = GrammarQuizSession(questions=custom_pool)
    daily = session.generate_daily_set(count=10)
    assert len(daily) == 10
    assert daily[0].id == "custom_0"
    assert daily[9].id == "custom_9"


def test_grammar_quiz_session_filters_invalid_questions():
    # Pool with invalid questions mixed in
    mixed_pool = [
        _make_sample_question(id="valid_1"),
        _make_sample_question(id="invalid_1", options=["only_two", "options"]),
        _make_sample_question(
            id="invalid_2",
            rule_explanation="Visit https://malicious.com",
        ),
        _make_sample_question(id="valid_2"),
    ]
    session = GrammarQuizSession(questions=mixed_pool)
    daily = session.generate_daily_set(count=10)
    assert len(daily) == 2
    assert [q.id for q in daily] == ["valid_1", "valid_2"]
