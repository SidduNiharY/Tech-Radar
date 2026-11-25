"""Official answer keys: the offline parts of Phase 8 Task 6b.

- `load_capture_pattern` accepts the owner's pattern only when it starts with
  `^https://<official host>/`, the host written with escaped dots only, and the pattern
  has no alternation (`|`): otherwise a pattern could match another site.
- `matching_links` finds links on an already fetched page with the standard library's
  HTML parser (never a model), and keeps a link only when it matches the pattern AND is
  itself `https` on an official host without userinfo or port (defence in depth). The
  page and the links it looks at are bounded.
- `render_answer_key_notice` shows a cleaned, shortened file name.

WIRING(claude): fetching is not built. `capture_answer_keys` (fetch the watched page
through the fetcher, download each new matching PDF into `library-packs/answer_keys/`)
needs the exam bodies' hosts in `infra/squid/allowlist.txt`, which only the owner adds.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from techradar.library.inbox import clean_text

OFFICIAL_SUFFIXES = (".gov.in", ".nic.in", ".ac.in", ".edu.in")
OFFICIAL_DOMAINS = frozenset(
    {
        "rbi.org.in",
        "ibps.in",
        "sbi.co.in",
        "nios.ac.in",
    }
)
MAX_PAGE_CHARS = 2_000_000
MAX_HREFS = 5_000
MAX_HREF_CHARS = 2_000
MAX_LINKS = 20
MAX_NOTICE_NAME = 120
MAX_NOTICE_EXAM = 40
_PREFIX = "^https://"
# Labels of letters, digits and hyphens joined by escaped dots, then the path's slash.
_HOST = re.compile(r"([A-Za-z0-9-]+(?:\\\.[A-Za-z0-9-]+)+)/")


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


def load_capture_pattern(pattern_str: str) -> re.Pattern[str]:
    """Validate and compile an answer key capture pattern anchored to an official host."""
    if not pattern_str.startswith(_PREFIX):
        raise ValueError("Pattern must start with '^https://'")
    if "|" in pattern_str:
        raise ValueError("Pattern must not use alternation ('|')")
    m = _HOST.match(pattern_str, len(_PREFIX))
    if m is None:
        raise ValueError(
            "Pattern must name the host with escaped dots, then '/', e.g. ^https://ssc\\.gov\\.in/"
        )
    host = m.group(1).replace("\\.", ".").lower()
    if not is_official_host(host):
        raise ValueError(f"Host '{host}' is not an allowlisted official host")
    return re.compile(pattern_str)


class _HrefParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a" and len(self.hrefs) < MAX_HREFS:
            for k, v in attrs:
                if k.lower() == "href" and v:
                    self.hrefs.append(v)


def _official_https(url: str) -> bool:
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return False
    return (
        parts.scheme == "https"
        and parts.username is None
        and parts.password is None
        and port is None
        and is_official_host(parts.hostname or "")
    )


def matching_links(html: str, base_url: str, pattern: re.Pattern[str]) -> list[str]:
    """Absolute https links to official hosts matching pattern, in page order, deduplicated,
    at most 20. Only the first 2,000,000 characters and 5,000 links of a page are read."""
    parser = _HrefParser()
    parser.feed(html[:MAX_PAGE_CHARS])
    parser.close()

    seen: set[str] = set()
    matches: list[str] = []
    for href in parser.hrefs:
        if len(href) > MAX_HREF_CHARS:
            continue
        abs_url = urljoin(base_url, href.strip())
        if abs_url in seen or not pattern.search(abs_url) or not _official_https(abs_url):
            continue
        seen.add(abs_url)
        matches.append(abs_url)
        if len(matches) >= MAX_LINKS:
            break
    return matches


def render_answer_key_notice(file_name: str, exam: str) -> str:
    """Render notification message when an official answer key is captured."""
    name = clean_text(file_name, MAX_NOTICE_NAME) or "answer key"
    label = clean_text(exam, MAX_NOTICE_EXAM).upper()
    return f"New answer key saved: {name} ({label}). It's in your library."
