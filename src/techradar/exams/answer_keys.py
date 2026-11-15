from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urljoin

OFFICIAL_SUFFIXES = (".gov.in", ".nic.in", ".ac.in", ".edu.in")
OFFICIAL_DOMAINS = frozenset(
    {
        "rbi.org.in",
        "ibps.in",
        "sbi.co.in",
        "nios.ac.in",
    }
)


def is_official_host(host: str) -> bool:
    """Return True if host belongs to an allowlisted official government/academic portal."""
    h = host.strip().lower().rstrip(".")
    if not h:
        return False
    if any(h == d or h.endswith("." + d) for d in OFFICIAL_DOMAINS):
        return True
    if any(h.endswith(s) and len(h) > len(s) for s in OFFICIAL_SUFFIXES):
        return True
    return False


def load_capture_pattern(pattern_str: str) -> re.Pattern:
    """Validate and compile an answer key capture pattern anchored to an official host."""
    if not pattern_str.startswith("^https://"):
        raise ValueError("Pattern must start with '^https://'")

    rem = pattern_str[len("^https://") :]
    slash_idx = rem.find("/")
    host_part = rem if slash_idx == -1 else rem[:slash_idx]

    # Host part must not contain wildcards or regex groups
    if any(c in host_part for c in "*+?[](){}|^$"):
        raise ValueError(f"Pattern host '{host_part}' cannot contain regex wildcards")

    host = host_part.replace(r"\.", ".").strip().lower()
    if not is_official_host(host):
        raise ValueError(f"Host '{host}' is not an allowlisted official host")

    return re.compile(pattern_str)


class _HrefParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            for k, v in attrs:
                if k.lower() == "href" and v:
                    self.hrefs.append(v)


def matching_links(html: str, base_url: str, pattern: re.Pattern) -> list[str]:
    """Extract absolute hrefs from HTML matching pattern, deduplicated, capped at 20."""
    parser = _HrefParser()
    parser.feed(html)

    seen: set[str] = set()
    matches: list[str] = []

    for href in parser.hrefs:
        abs_url = urljoin(base_url, href)
        if pattern.search(abs_url) and abs_url not in seen:
            seen.add(abs_url)
            matches.append(abs_url)
            if len(matches) >= 20:
                break

    return matches


def render_answer_key_notice(file_name: str, exam: str) -> str:
    """Render notification message when an official answer key is captured."""
    return f"New answer key saved: {file_name} ({exam.upper()}). It's in your library."
