from __future__ import annotations

from techradar.pipeline.politics import (
    Opinion,
    PoliticsView,
    keep_attributed,
    render_opinion_sections,
)


def test_opinions_need_cluster_domain() -> None:
    v = keep_attributed(
        PoliticsView(
            facts=[],
            supporters_say=[
                Opinion(text="Good bill", domain="a.com"),
                Opinion(text="x", domain="evil.example"),
            ],
            critics_say=[],
        ),
        {"a.com", "b.in", "c.org"},
    )
    assert [o.domain for o in v.supporters_say] == ["a.com"]


def test_render_opinion_sections() -> None:
    view = PoliticsView(
        facts=[],
        supporters_say=[Opinion(text="Spurs economic growth", domain="thehindu.com")],
        critics_say=[Opinion(text="Increases fiscal deficit", domain="indianexpress.com")],
    )
    rendered = render_opinion_sections(view)
    assert "## What supporters say (opinion)" in rendered
    assert "- Spurs economic growth (thehindu.com)" in rendered
    assert "## What critics say (opinion)" in rendered
    assert "- Increases fiscal deficit (indianexpress.com)" in rendered
