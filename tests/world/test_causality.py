"""Tests for techradar.world.causality."""

import pytest

from techradar.world.causality import CausalGraph, CausalLink, CauseNode


def test_add_nodes_and_links() -> None:
    graph = CausalGraph()
    n1 = CauseNode(id="oil_shock", event="Global oil price hike", domain="Economy")
    n2 = CauseNode(id="fuel_price", event="Domestic fuel price rise", domain="Economy")

    graph.add_node(n1)
    graph.add_node(n2)

    assert "oil_shock" in graph.nodes
    assert "fuel_price" in graph.nodes
    assert len(graph.links) == 0

    link = CausalLink(
        source_id="oil_shock",
        target_id="fuel_price",
        relationship="directly_increases",
        evidence_quote="Oil import costs pass through to pump prices.",
    )
    graph.add_link(link)

    assert len(graph.links) == 1
    assert graph.links[0].source_id == "oil_shock"
    assert graph.links[0].target_id == "fuel_price"


def test_reject_self_loop() -> None:
    graph = CausalGraph()
    n1 = CauseNode(id="inflation", event="Inflation rises", domain="Economy")
    graph.add_node(n1)

    self_loop = CausalLink(
        source_id="inflation",
        target_id="inflation",
        relationship="feeds_back",
        evidence_quote="Feedback",
    )
    with pytest.raises(ValueError, match="Self-loop rejected"):
        graph.add_link(self_loop)


def test_reject_missing_nodes() -> None:
    graph = CausalGraph()
    n1 = CauseNode(id="n1", event="Event 1", domain="General")
    graph.add_node(n1)

    missing_target = CausalLink(
        source_id="n1", target_id="n2", relationship="causes", evidence_quote="none"
    )
    with pytest.raises(ValueError, match="Target node 'n2' does not exist"):
        graph.add_link(missing_target)

    missing_source = CausalLink(
        source_id="n0", target_id="n1", relationship="causes", evidence_quote="none"
    )
    with pytest.raises(ValueError, match="Source node 'n0' does not exist"):
        graph.add_link(missing_source)


def test_cycle_detection() -> None:
    graph = CausalGraph()

    # Empty graph is acyclic
    assert not graph.has_cycle()

    # Linear chain A -> B -> C: acyclic
    for nid in ["A", "B", "C"]:
        graph.add_node(CauseNode(id=nid, event=f"Event {nid}", domain="General"))

    graph.add_link(
        CausalLink(source_id="A", target_id="B", relationship="causes", evidence_quote="q")
    )
    graph.add_link(
        CausalLink(source_id="B", target_id="C", relationship="causes", evidence_quote="q")
    )
    assert not graph.has_cycle()

    # Diamond: A -> B, A -> C, B -> D, C -> D: acyclic
    graph.add_node(CauseNode(id="D", event="Event D", domain="General"))
    graph.add_link(
        CausalLink(source_id="A", target_id="C", relationship="causes", evidence_quote="q")
    )
    graph.add_link(
        CausalLink(source_id="B", target_id="D", relationship="causes", evidence_quote="q")
    )
    graph.add_link(
        CausalLink(source_id="C", target_id="D", relationship="causes", evidence_quote="q")
    )
    assert not graph.has_cycle()

    # Introduce cycle: D -> A
    graph.add_link(
        CausalLink(source_id="D", target_id="A", relationship="causes", evidence_quote="q")
    )
    assert graph.has_cycle()


def test_cycle_detection_small_cycle() -> None:
    graph = CausalGraph()
    graph.add_node(CauseNode(id="X", event="Event X", domain="General"))
    graph.add_node(CauseNode(id="Y", event="Event Y", domain="General"))

    graph.add_link(
        CausalLink(source_id="X", target_id="Y", relationship="causes", evidence_quote="q")
    )
    assert not graph.has_cycle()

    graph.add_link(
        CausalLink(source_id="Y", target_id="X", relationship="causes", evidence_quote="q")
    )
    assert graph.has_cycle()


def test_traversal_effects_and_root_causes() -> None:
    # Build causal graph:
    #   oil_shock -> transport_cost -> inflation -> rate_hike
    #   supply_snarl -> transport_cost
    graph = CausalGraph()

    nodes = [
        CauseNode(id="oil_shock", event="Crude oil price surge", domain="Economy"),
        CauseNode(id="supply_snarl", event="Global shipping bottlenecks", domain="Economy"),
        CauseNode(id="transport_cost", event="Transport costs surge", domain="Economy"),
        CauseNode(id="inflation", event="Broad price inflation", domain="Economy"),
        CauseNode(id="rate_hike", event="Central bank hikes rates", domain="Economy"),
    ]
    for n in nodes:
        graph.add_node(n)

    graph.add_link(
        CausalLink(
            source_id="oil_shock",
            target_id="transport_cost",
            relationship="causes",
            evidence_quote="q",
        )
    )
    graph.add_link(
        CausalLink(
            source_id="supply_snarl",
            target_id="transport_cost",
            relationship="causes",
            evidence_quote="q",
        )
    )
    graph.add_link(
        CausalLink(
            source_id="transport_cost",
            target_id="inflation",
            relationship="causes",
            evidence_quote="q",
        )
    )
    graph.add_link(
        CausalLink(
            source_id="inflation",
            target_id="rate_hike",
            relationship="causes",
            evidence_quote="q",
        )
    )

    # Downstream effects of oil_shock
    effects_oil = graph.get_effects("oil_shock")
    effect_ids = [e.id for e in effects_oil]
    assert effect_ids == ["transport_cost", "inflation", "rate_hike"]

    # Downstream effects of leaf node rate_hike
    assert graph.get_effects("rate_hike") == []

    # Downstream effects of unknown node
    assert graph.get_effects("nonexistent") == []

    # Upstream root causes of rate_hike (both oil_shock and supply_snarl)
    roots_rate = graph.get_root_causes("rate_hike")
    root_ids = {r.id for r in roots_rate}
    assert root_ids == {"oil_shock", "supply_snarl"}

    # Upstream root causes of transport_cost
    roots_transport = graph.get_root_causes("transport_cost")
    assert {r.id for r in roots_transport} == {"oil_shock", "supply_snarl"}

    # Upstream root causes of root node oil_shock
    assert graph.get_root_causes("oil_shock") == []

    # Upstream root causes of unknown node
    assert graph.get_root_causes("nonexistent") == []
