from __future__ import annotations

from techradar.fetcher.wikipedia import wikipedia_url


def test_wikipedia_url_quotes_title() -> None:
    assert (
        wikipedia_url("Reserve Bank of India")
        == "https://en.wikipedia.org/w/rest.php/v1/page/Reserve%20Bank%20of%20India/html"
    )
