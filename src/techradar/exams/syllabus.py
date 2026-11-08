from __future__ import annotations

from pydantic import BaseModel, Field


class SyllabusNode(BaseModel):
    id: str
    title: str
    exam_code: str
    parent_id: str | None = None
    subtopics: list[str] = Field(default_factory=list)
    weight: float = 1.0
    covered: bool = False


_DEFAULT_GATE_CS_SYLLABUS = [
    SyllabusNode(
        id="gate_cs_algo",
        title="Algorithms",
        exam_code="GATE_CS",
        subtopics=[
            "Asymptotic analysis",
            "Recurrence relations",
            "Divide and conquer",
            "Greedy algorithms",
            "Dynamic programming",
            "Graph traversals and MST",
        ],
        weight=1.0,
    ),
    SyllabusNode(
        id="gate_cs_os",
        title="OS",
        exam_code="GATE_CS",
        subtopics=[
            "Processes and threads",
            "CPU scheduling",
            "Deadlocks and synchronization",
            "Memory management and virtual memory",
            "File systems and I/O",
        ],
        weight=1.0,
    ),
    SyllabusNode(
        id="gate_cs_dbms",
        title="DBMS",
        exam_code="GATE_CS",
        subtopics=[
            "ER-model and relational schema",
            "Relational algebra and tuple calculus",
            "SQL queries",
            "Integrity constraints and normalization",
            "Transactions and concurrency control",
        ],
        weight=1.0,
    ),
    SyllabusNode(
        id="gate_cs_networks",
        title="Networks",
        exam_code="GATE_CS",
        subtopics=[
            "OSI and TCP/IP protocol suite",
            "Framing and flow/error control",
            "Routing algorithms and IP addressing",
            "TCP/UDP and congestion control",
            "Network security and firewalls",
        ],
        weight=1.0,
    ),
]

_DEFAULT_SSC_CGL_SYLLABUS = [
    SyllabusNode(
        id="ssc_cgl_quant",
        title="Quantitative Aptitude",
        exam_code="SSC_CGL",
        subtopics=[
            "Percentages, profit and loss",
            "Ratio, proportion and averages",
            "Time and work",
            "Speed, time and distance",
            "Algebra, geometry and trigonometry",
        ],
        weight=1.0,
    ),
    SyllabusNode(
        id="ssc_cgl_reasoning",
        title="Reasoning",
        exam_code="SSC_CGL",
        subtopics=[
            "Analogies and classification",
            "Number and alphabet series",
            "Coding-decoding",
            "Syllogisms and Venn diagrams",
            "Blood relations and directions",
        ],
        weight=1.0,
    ),
    SyllabusNode(
        id="ssc_cgl_english",
        title="English",
        exam_code="SSC_CGL",
        subtopics=[
            "Reading comprehension",
            "Spotting errors",
            "Sentence improvement and cloze test",
            "Idioms, phrases and one word substitution",
            "Synonyms and antonyms",
        ],
        weight=1.0,
    ),
    SyllabusNode(
        id="ssc_cgl_ga",
        title="General Awareness",
        exam_code="SSC_CGL",
        subtopics=[
            "Current affairs and national events",
            "Indian history and culture",
            "Polity and constitution",
            "Geography and environment",
            "General science and economic policies",
        ],
        weight=1.0,
    ),
]


def get_default_syllabus(exam_code: str) -> list[SyllabusNode]:
    """Returns curated baseline syllabus tree nodes for recognized exams."""
    normalized = exam_code.strip().upper().replace("-", "_").replace(" ", "_")
    if normalized == "GATE_CS":
        return [node.model_copy() for node in _DEFAULT_GATE_CS_SYLLABUS]
    if normalized == "SSC_CGL":
        return [node.model_copy() for node in _DEFAULT_SSC_CGL_SYLLABUS]
    return []


class SyllabusTree:
    """In-memory syllabus tree representation with hierarchy and coverage tracking."""

    def __init__(self) -> None:
        self._nodes: dict[str, SyllabusNode] = {}

    def add_node(self, node: SyllabusNode) -> None:
        """Adds or updates a syllabus node."""
        self._nodes[node.id] = node

    def get_node(self, node_id: str) -> SyllabusNode | None:
        """Retrieves a syllabus node by ID."""
        return self._nodes.get(node_id)

    def get_children(self, parent_id: str) -> list[SyllabusNode]:
        """Returns direct children of a given parent node."""
        return [node for node in self._nodes.values() if node.parent_id == parent_id]

    def get_nodes(self, exam_code: str | None = None) -> list[SyllabusNode]:
        """Returns all nodes, optionally filtered by exam code."""
        if exam_code is None:
            return list(self._nodes.values())
        normalized = exam_code.strip().upper().replace("-", "_").replace(" ", "_")
        return [
            node
            for node in self._nodes.values()
            if node.exam_code.strip().upper().replace("-", "_").replace(" ", "_") == normalized
        ]

    def mark_covered(self, node_id: str, covered: bool = True) -> None:
        """Marks a node as covered or uncovered."""
        node = self._nodes.get(node_id)
        if node is not None:
            node.covered = covered

    def get_uncovered_topics(self, exam_code: str) -> list[SyllabusNode]:
        """Returns all syllabus nodes for an exam where covered is False."""
        normalized = exam_code.strip().upper().replace("-", "_").replace(" ", "_")
        return [
            node
            for node in self._nodes.values()
            if node.exam_code.strip().upper().replace("-", "_").replace(" ", "_") == normalized
            and not node.covered
        ]

    def calculate_coverage(self, exam_code: str, weighted: bool = False) -> float:
        """Returns coverage percentage (0.0 to 100.0) of topics for an exam."""
        nodes = self.get_nodes(exam_code)
        if not nodes:
            return 0.0
        if weighted:
            total_weight = sum(node.weight for node in nodes)
            if total_weight <= 0:
                return 0.0
            covered_weight = sum(node.weight for node in nodes if node.covered)
            return round((covered_weight / total_weight) * 100.0, 2)
        covered_count = sum(1 for node in nodes if node.covered)
        return round((covered_count / len(nodes)) * 100.0, 2)

    def load_default_syllabus(self, exam_code: str) -> list[SyllabusNode]:
        """Loads curated default syllabus nodes into the tree and returns them."""
        nodes = get_default_syllabus(exam_code)
        for node in nodes:
            self.add_node(node)
        return nodes
