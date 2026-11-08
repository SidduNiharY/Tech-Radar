from __future__ import annotations

from techradar.voice.grammar import (
    SpeechGrammarFeedback,
    evaluate_speech_grammar,
)


def test_clean_transcript_produces_zero_issues_and_excellent_rating():
    transcript = (
        "We configured the database cluster with three read replicas. "
        "High availability is maintained across all deployment regions."
    )
    feedback = evaluate_speech_grammar(transcript)

    assert isinstance(feedback, SpeechGrammarFeedback)
    assert feedback.total_sentences == 2
    assert feedback.issues == []
    assert feedback.clarity_rating == "excellent"


def test_repeated_word_detection():
    transcript = "I went to the the server room to inspect the nodes."
    feedback = evaluate_speech_grammar(transcript)

    assert len(feedback.issues) == 1
    issue = feedback.issues[0]
    assert issue["type"] == "repeated_word"
    assert issue["match"] == "the the"
    assert "the" in issue["message"]
    assert issue["suggestion"] == "the"


def test_repeated_word_exclusions():
    # Idioms and legitimate English repetitions shouldn't be falsely flagged
    transcript = "He knew that that was expected. He said bye bye before leaving."
    feedback = evaluate_speech_grammar(transcript)

    assert feedback.issues == []
    assert feedback.clarity_rating == "excellent"


def test_double_comparative_detection():
    transcript = "This caching layer makes our service more better under load."
    feedback = evaluate_speech_grammar(transcript)

    assert len(feedback.issues) == 1
    issue = feedback.issues[0]
    assert issue["type"] == "double_comparative"
    assert issue["match"] == "more better"
    assert "more better" in issue["message"]
    assert issue["suggestion"] == "better"

    superlative_text = "This is the most best architectural pattern for our team."
    superlative_feedback = evaluate_speech_grammar(superlative_text)
    assert len(superlative_feedback.issues) == 1
    assert superlative_feedback.issues[0]["type"] == "double_comparative"
    assert superlative_feedback.issues[0]["match"] == "most best"
    assert superlative_feedback.issues[0]["suggestion"] == "best"


def test_subject_verb_disagreement_detection():
    transcript = "He don't understand the cache eviction policy."
    feedback = evaluate_speech_grammar(transcript)

    assert len(feedback.issues) == 1
    issue = feedback.issues[0]
    assert issue["type"] == "subject_verb_disagreement"
    assert issue["match"] == "He don't"
    assert issue["suggestion"] == "He doesn't"


def test_double_negative_detection():
    transcript = "We don't have no memory leaks in this process."
    feedback = evaluate_speech_grammar(transcript)

    assert len(feedback.issues) == 1
    issue = feedback.issues[0]
    assert issue["type"] == "double_negative"


def test_clarity_rating_gradation():
    # 0 issues -> excellent
    clean = evaluate_speech_grammar("Everything is running smoothly.")
    assert clean.clarity_rating == "excellent"

    # 1 issue -> good
    one_issue = evaluate_speech_grammar("We went to the the store.")
    assert len(one_issue.issues) == 1
    assert one_issue.clarity_rating == "good"

    # 2 issues -> good
    two_issues = evaluate_speech_grammar("We went to the the store. It is more better.")
    assert len(two_issues.issues) == 2
    assert two_issues.clarity_rating == "good"

    # 3 issues -> needs_practice
    three_issues = evaluate_speech_grammar("He don't know the the reason. It is more better now.")
    assert len(three_issues.issues) == 3
    assert three_issues.clarity_rating == "needs_practice"


def test_empty_transcript():
    feedback = evaluate_speech_grammar("")
    assert feedback.total_sentences == 0
    assert feedback.issues == []
    assert feedback.clarity_rating == "excellent"

    whitespace_feedback = evaluate_speech_grammar("   \n\t  ")
    assert whitespace_feedback.total_sentences == 0
    assert whitespace_feedback.issues == []
    assert whitespace_feedback.clarity_rating == "excellent"
