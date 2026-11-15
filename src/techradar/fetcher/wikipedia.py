from __future__ import annotations

import urllib.parse
from typing import Literal


def wikipedia_url(title: str, lang: Literal["en"] = "en") -> str:
    """Generate the official Wikipedia REST API HTML endpoint URL for a page title."""
    quoted = urllib.parse.quote(title)
    return f"https://{lang}.wikipedia.org/w/rest.php/v1/page/{quoted}/html"
