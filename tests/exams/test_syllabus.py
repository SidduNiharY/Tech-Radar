from __future__ import annotations

from techradar.exams.syllabus import SyllabusNode, SyllabusTree, get_default_syllabus


def test_hierarchical_node_insertion_and_parent_child_tracking():
    tree = SyllabusTree()

    parent = SyllabusNode(
        id="gate_cs_algo",
        title="Algorithms",
        exam_code="GATE_CS",
        subtopics=["Analysis", "Greedy", "DP"],
        weight=2.0,
    )
    child1 = SyllabusNode(
        id="gate_cs_algo_dp",
        title="Dynamic Programming",
        exam_code="GATE_CS",
        parent_id="gate_cs_algo",
        subtopics=["Optimal Substructure", "Knapsack"],
        weight=1.0,
    )
    child2 = SyllabusNode(
        id="gate_cs_algo_graphs",
        title="Graph Algorithms",
        exam_code="GATE_CS",
        parent_id="gate_cs_algo",
        subtopics=["BFS/DFS", "Dijkstra"],
        weight=1.0,
    )
    other = SyllabusNode(
        id="gate_cs_os",
        title="OS",
        exam_code="GATE_CS",
        weight=1.5,
    )

    tree.add_node(parent)
    tree.add_node(child1)
    tree.add_node(child2)
    tree.add_node(other)

    # Node retrieval
    assert tree.get_node("gate_cs_algo") == parent
    assert tree.get_node("gate_cs_algo_dp") == child1
    assert tree.get_node("non_existent") is None

    # Parent-child tracking
    algo_children = tree.get_children("gate_cs_algo")
    assert len(algo_children) == 2
    assert {c.id for c in algo_children} == {"gate_cs_algo_dp", "gate_cs_algo_graphs"}
    assert tree.get_children("gate_cs_os") == []
    assert tree.get_children("unknown_id") == []

    # Node parent_id inspection
    assert child1.parent_id == "gate_cs_algo"
    assert parent.parent_id is None


def test_coverage_calculation_empty_and_levels():
    tree = SyllabusTree()

    # Empty tree returns 0.0
    assert tree.calculate_coverage("GATE_CS") == 0.0

    node1 = SyllabusNode(
        id="t1",
        title="Topic 1",
        exam_code="GATE_CS",
        covered=False,
    )
    node2 = SyllabusNode(
        id="t2",
        title="Topic 2",
        exam_code="GATE_CS",
        covered=False,
    )
    tree.add_node(node1)
    tree.add_node(node2)

    # 0% coverage
    assert tree.calculate_coverage("GATE_CS") == 0.0
    uncovered = tree.get_uncovered_topics("GATE_CS")
    assert len(uncovered) == 2
    assert {n.id for n in uncovered} == {"t1", "t2"}

    # 50% coverage
    tree.mark_covered("t1", True)
    assert tree.calculate_coverage("GATE_CS") == 50.0
    uncovered = tree.get_uncovered_topics("GATE_CS")
    assert len(uncovered) == 1
    assert uncovered[0].id == "t2"

    # 100% coverage
    tree.mark_covered("t2", True)
    assert tree.calculate_coverage("GATE_CS") == 100.0
    assert tree.get_uncovered_topics("GATE_CS") == []


def test_weighted_coverage_calculation():
    tree = SyllabusTree()

    node1 = SyllabusNode(
        id="w1",
        title="Core Topic",
        exam_code="GATE_CS",
        weight=3.0,
        covered=False,
    )
    node2 = SyllabusNode(
        id="w2",
        title="Minor Topic",
        exam_code="GATE_CS",
        weight=1.0,
        covered=False,
    )
    tree.add_node(node1)
    tree.add_node(node2)

    # Both uncovered
    assert tree.calculate_coverage("GATE_CS", weighted=True) == 0.0

    # Covering node with weight 3 out of total weight 4 -> 75%
    tree.mark_covered("w1", True)
    assert tree.calculate_coverage("GATE_CS", weighted=True) == 75.0

    # Covering both -> 100%
    tree.mark_covered("w2", True)
    assert tree.calculate_coverage("GATE_CS", weighted=True) == 100.0


def test_default_syllabus_loader_gate_cs():
    tree = SyllabusTree()
    gate_nodes = tree.load_default_syllabus("GATE_CS")

    assert len(gate_nodes) == 4
    titles = [n.title for n in gate_nodes]
    assert "Algorithms" in titles
    assert "OS" in titles
    assert "DBMS" in titles
    assert "Networks" in titles

    for node in gate_nodes:
        assert node.exam_code == "GATE_CS"
        assert not node.covered
        assert len(node.subtopics) > 0

    # Initial coverage is 0.0%
    assert tree.calculate_coverage("GATE_CS") == 0.0

    # All nodes are uncovered initially
    assert len(tree.get_uncovered_topics("GATE_CS")) == 4


def test_default_syllabus_loader_ssc_cgl():
    tree = SyllabusTree()
    ssc_nodes = tree.load_default_syllabus("SSC_CGL")

    assert len(ssc_nodes) == 4
    titles = [n.title for n in ssc_nodes]
    assert "Quantitative Aptitude" in titles
    assert "Reasoning" in titles
    assert "English" in titles
    assert "General Awareness" in titles

    for node in ssc_nodes:
        assert node.exam_code == "SSC_CGL"
        assert not node.covered
        assert len(node.subtopics) > 0

    assert tree.calculate_coverage("SSC_CGL") == 0.0


def test_default_syllabus_normalization_and_unknown():
    # Test case and punctuation normalization
    nodes_lower = get_default_syllabus("gate-cs")
    assert len(nodes_lower) == 4

    nodes_spaced = get_default_syllabus("SSC CGL")
    assert len(nodes_spaced) == 4

    # Unknown exam code returns empty list
    assert get_default_syllabus("UNKNOWN_EXAM") == []
