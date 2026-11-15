from __future__ import annotations

from techradar.exams.pyq import (
    KeyEntry,
    QuestionChunk,
    check_answer,
    parse_answer_key,
    split_questions,
    suggest_topic,
)
from tests.fakes import FakeCompleter

GATE_TEXT_FIXTURE = """
Q. 1 Which of the following is a power of 2?
(A) 2
(B) 4
(C) 8
(D) 16

Q. 2
Which algorithm is used for MST?
(A) Prim's
(B) Kruskal's
(C) Dijkstra's
(D) Bellman-Ford

Q. 3
Compute the value of 1.5 + 0.05.
"""


def test_split_questions_fixture():
    qs = split_questions(GATE_TEXT_FIXTURE)
    assert [q.number for q in qs] == [1, 2, 3]
    assert qs[0].options == ["(A) 2", "(B) 4", "(C) 8", "(D) 16"]
    assert qs[1].options == ["(A) Prim's", "(B) Kruskal's", "(C) Dijkstra's", "(D) Bellman-Ford"]
    assert qs[2].options is None
    assert "1.5 + 0.05" in qs[2].text


def test_parse_answer_key_rows():
    keys = parse_answer_key("1 MCQ GA A 1\n2 MSQ CS A;C 2\n3 NAT CS 1.5 to 1.6 2\n")
    assert keys[1].key == "A"
    assert keys[1].qtype == "MCQ"
    assert keys[1].marks == 1.0
    assert keys[2].key == "A;C"
    assert keys[2].qtype == "MSQ"
    assert keys[3].qtype == "NAT"
    assert keys[3].key == "1.5 to 1.6"
    assert keys[3].marks == 2.0


def test_nat_range_inclusive():
    entry = KeyEntry(qtype="NAT", key="1.5 to 1.6", marks=2)
    assert check_answer(entry, "1.55")
    assert check_answer(entry, "1.6")
    assert check_answer(entry, "1.5")
    assert not check_answer(entry, "1.61")
    assert not check_answer(entry, "1.49")
    assert not check_answer(entry, "invalid")


def test_nat_single_value():
    entry = KeyEntry(qtype="NAT", key="42.5", marks=1)
    assert check_answer(entry, "42.5")
    assert not check_answer(entry, "42.51")


def test_mcq_exact():
    entry = KeyEntry(qtype="MCQ", key="B", marks=1)
    assert check_answer(entry, "B")
    assert check_answer(entry, "b")
    assert not check_answer(entry, "A")


def test_msq_set_equality():
    entry = KeyEntry(qtype="MSQ", key="A;C", marks=2)
    assert check_answer(entry, "C;A")
    assert check_answer(entry, "A, C")
    assert not check_answer(entry, "A")
    assert not check_answer(entry, "A;B;C")


async def test_suggest_topic_must_be_in_list():
    q = QuestionChunk(number=1, text="Explain banker's algorithm")
    completer = FakeCompleter(['{"topic": "Cooking"}'])
    res = await suggest_topic(completer, q, ["Deadlocks", "Paging"])
    assert res is None


async def test_suggest_topic_agreed():
    q = QuestionChunk(number=1, text="Explain banker's algorithm")
    completer = FakeCompleter(['{"topic": "Deadlocks"}', '{"topic": "Deadlocks"}'])
    res = await suggest_topic(completer, q, ["Deadlocks", "Paging"])
    assert res == "Deadlocks"


async def test_suggest_topic_checker_disagrees():
    q = QuestionChunk(number=1, text="Explain banker's algorithm")
    completer = FakeCompleter(['{"topic": "Deadlocks"}', '{"topic": ""}'])
    res = await suggest_topic(completer, q, ["Deadlocks", "Paging"])
    assert res is None
