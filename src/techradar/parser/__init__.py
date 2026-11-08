from __future__ import annotations

from techradar.parser.feed import feed_to_entries
from techradar.parser.html import MIN_TEXT_CHARS, html_to_doc
from techradar.parser.limits import parse_job, run_with_limits
from techradar.parser.main import serve_forever, serve_once
from techradar.parser.pdf import pdf_to_doc

__all__ = [
    "MIN_TEXT_CHARS",
    "feed_to_entries",
    "html_to_doc",
    "parse_job",
    "pdf_to_doc",
    "run_with_limits",
    "serve_forever",
    "serve_once",
]
