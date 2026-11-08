from __future__ import annotations

from techradar.practice.mistakes import MistakesNotebook


def test_record_quiz_mistake_and_list_active():
    notebook = MistakesNotebook()
    user_id = 1001

    mistake_id = notebook.record_quiz_mistake(
        user_id=user_id,
        question_id="gate_algo_42",
        question_text="What is the worst-case time complexity of QuickSort?",
        chosen_option="O(N log N)",
        correct_option="O(N^2)",
        explanation="When partition is maximally unbalanced, QuickSort degrades to O(N^2).",
    )

    assert isinstance(mistake_id, str)
    assert mistake_id.startswith("mstk_")

    active = notebook.get_active_mistakes(user_id)
    assert len(active) == 1
    m = active[0]
    assert m["id"] == mistake_id
    assert m["user_id"] == user_id
    assert m["question_id"] == "gate_algo_42"
    assert m["chosen_option"] == "O(N log N)"
    assert m["correct_option"] == "O(N^2)"
    assert "QuickSort" in m["explanation"]
    assert m["resolved"] is False


def test_resolve_mistake():
    notebook = MistakesNotebook()
    user_id = 1002

    m1_id = notebook.record_quiz_mistake(
        user_id=user_id,
        question_id="gate_dbms_01",
        question_text="Which normal form eliminates partial dependency?",
        chosen_option="1NF",
        correct_option="2NF",
        explanation="2NF requires 1NF and no partial dependencies.",
    )
    m2_id = notebook.record_quiz_mistake(
        user_id=user_id,
        question_id="gate_dbms_02",
        question_text="Which normal form eliminates transitive dependency?",
        chosen_option="2NF",
        correct_option="3NF",
        explanation="3NF eliminates transitive dependencies for non-prime attributes.",
    )

    # Both active initially
    active = notebook.get_active_mistakes(user_id)
    assert len(active) == 2

    # Resolve first mistake
    notebook.resolve_mistake(m1_id)

    # Only second mistake remains active
    active_after = notebook.get_active_mistakes(user_id)
    assert len(active_after) == 1
    assert active_after[0]["id"] == m2_id
    assert active_after[0]["question_id"] == "gate_dbms_02"

    # Resolving second mistake leaves 0 active mistakes
    notebook.resolve_mistake(m2_id)
    assert len(notebook.get_active_mistakes(user_id)) == 0


def test_user_isolation():
    notebook = MistakesNotebook()
    user_a = 2001
    user_b = 2002

    notebook.record_quiz_mistake(
        user_id=user_a,
        question_id="q1",
        question_text="Text A",
        chosen_option="A",
        correct_option="B",
        explanation="Exp A",
    )
    notebook.record_quiz_mistake(
        user_id=user_b,
        question_id="q2",
        question_text="Text B",
        chosen_option="C",
        correct_option="D",
        explanation="Exp B",
    )

    assert len(notebook.get_active_mistakes(user_a)) == 1
    assert len(notebook.get_active_mistakes(user_b)) == 1
    assert notebook.get_active_mistakes(user_a)[0]["question_id"] == "q1"
    assert notebook.get_active_mistakes(user_b)[0]["question_id"] == "q2"


def test_resolve_unknown_mistake_graceful():
    notebook = MistakesNotebook()
    # Does not raise error on non-existent mistake id
    notebook.resolve_mistake("non_existent_id")
