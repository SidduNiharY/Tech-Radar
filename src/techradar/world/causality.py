"""Causality graph engine for analyzing events, links, and root causes."""

from collections import deque

from pydantic import BaseModel


class CauseNode(BaseModel):
    """Node representing an event in a causal domain."""

    id: str
    event: str
    domain: str
    confidence: float = 1.0


class CausalLink(BaseModel):
    """Directed causal relationship connecting two cause nodes."""

    source_id: str
    target_id: str
    relationship: str
    evidence_quote: str


class CausalGraph:
    """Directed graph representing causal chains with cycle detection and traversal."""

    def __init__(self) -> None:
        self._nodes: dict[str, CauseNode] = {}
        self._links: list[CausalLink] = []
        self._adj: dict[str, list[str]] = {}
        self._rev_adj: dict[str, list[str]] = {}

    @property
    def nodes(self) -> dict[str, CauseNode]:
        """Return shallow copy of registered nodes."""
        return dict(self._nodes)

    @property
    def links(self) -> list[CausalLink]:
        """Return shallow copy of causal links."""
        return list(self._links)

    def add_node(self, node: CauseNode) -> None:
        """Register a node in the causal graph."""
        self._nodes[node.id] = node
        if node.id not in self._adj:
            self._adj[node.id] = []
        if node.id not in self._rev_adj:
            self._rev_adj[node.id] = []

    def add_link(self, link: CausalLink) -> None:
        """Add a directed causal link; rejects self-loops and unknown nodes."""
        if link.source_id == link.target_id:
            raise ValueError(f"Self-loop rejected: {link.source_id} -> {link.target_id}")
        if link.source_id not in self._nodes:
            raise ValueError(f"Source node '{link.source_id}' does not exist in graph")
        if link.target_id not in self._nodes:
            raise ValueError(f"Target node '{link.target_id}' does not exist in graph")

        if link.target_id not in self._adj[link.source_id]:
            self._adj[link.source_id].append(link.target_id)
        if link.source_id not in self._rev_adj[link.target_id]:
            self._rev_adj[link.target_id].append(link.source_id)
        self._links.append(link)

    def has_cycle(self) -> bool:
        """Detect whether the graph contains a directed cycle using DFS coloring."""
        # 0 = unvisited (white), 1 = visiting (gray), 2 = visited (black)
        state: dict[str, int] = {node_id: 0 for node_id in self._nodes}

        def _dfs(node_id: str) -> bool:
            state[node_id] = 1
            for neighbor in self._adj.get(node_id, []):
                if state.get(neighbor, 0) == 1:
                    return True
                if state.get(neighbor, 0) == 0 and _dfs(neighbor):
                    return True
            state[node_id] = 2
            return False

        for node_id in self._nodes:
            if state[node_id] == 0 and _dfs(node_id):
                return True
        return False

    def get_effects(self, node_id: str) -> list[CauseNode]:
        """Traverse downstream from node_id and return all reachable effect nodes."""
        if node_id not in self._nodes:
            return []

        visited: set[str] = {node_id}
        queue: deque[str] = deque([node_id])
        effects: list[CauseNode] = []

        while queue:
            current = queue.popleft()
            for successor in self._adj.get(current, []):
                if successor not in visited:
                    visited.add(successor)
                    queue.append(successor)
                    effects.append(self._nodes[successor])

        return effects

    def get_root_causes(self, node_id: str) -> list[CauseNode]:
        """Traverse upstream from node_id and return root causes (ancestors with in-degree 0)."""
        if node_id not in self._nodes:
            return []

        visited: set[str] = set()
        queue: deque[str] = deque(self._rev_adj.get(node_id, []))
        for parent in queue:
            visited.add(parent)

        ancestors: list[str] = []
        while queue:
            current = queue.popleft()
            ancestors.append(current)
            for predecessor in self._rev_adj.get(current, []):
                if predecessor not in visited:
                    visited.add(predecessor)
                    queue.append(predecessor)

        # Root causes are ancestors having in-degree 0 in the causal graph
        root_nodes = [
            self._nodes[ancestor_id]
            for ancestor_id in ancestors
            if not self._rev_adj.get(ancestor_id)
        ]
        if root_nodes:
            return root_nodes

        # Fallback if ancestors form a cycle with no external root
        return [self._nodes[ancestor_id] for ancestor_id in ancestors]
