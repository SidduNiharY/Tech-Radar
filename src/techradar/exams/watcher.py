from __future__ import annotations

import hashlib
import html
import re
from datetime import date
from pathlib import Path

from pydantic import BaseModel

from techradar.security.text import sanitize_text
from techradar.security.urls import UrlRejected, check_url, load_allowlist


class ExamTarget(BaseModel):
    id: str
    title: str
    url: str
    exam_code: str


class ExamNotification(BaseModel):
    target_id: str
    title: str
    published_date: date | None = None
    url: str
    exam_code: str | None = None
    target_title: str | None = None


def clean_exam_notice_title(raw: str) -> str:
    """Sanitize and strip raw HTML, script tags, and embedded external URLs from headline."""
    if not raw:
        return ""
    text = html.unescape(raw)
    # Strip script, style, and iframe tags along with their contents
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = re.sub(r"(?is)<iframe[^>]*>.*?</iframe>", " ", text)
    # Strip all remaining HTML tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Strip embedded URLs from notice headline
    text = re.sub(r"(?i)\b(?:https?://|www\.|javascript:)\S+", "", text)
    # Strip external domain references from notice headline
    text = re.sub(
        r"(?i)\b[a-zA-Z0-9.-]+\.(?:com|org|net|io|site|xyz|info|biz|co|cc|online)\b/?\S*",
        "",
        text,
    )
    # Strip angle brackets to prevent any HTML tag reconstruction
    text = text.replace("<", "").replace(">", "")
    # Sanitize unicode control/bidi characters
    text = sanitize_text(text)
    # Collapse newlines and whitespace to single line
    return re.sub(r"\s+", " ", text).strip()


def check_exam_domain_allowlisted(
    url: str,
    allowlist_path: Path | str | None = None,
    *,
    raise_on_error: bool = False,
) -> bool:
    """Verify that a URL's domain is allowed by the Squid egress allowlist.

    Returns True if the URL is valid, uses HTTPS, and its hostname matches an
    allowlisted domain. Returns False otherwise (or raises ValueError if raise_on_error=True).
    """
    path = Path(allowlist_path) if allowlist_path is not None else Path("infra/squid/allowlist.txt")
    if not path.is_file():
        if raise_on_error:
            raise ValueError(f"Allowlist file not found: {path}")
        return False

    try:
        allowed = load_allowlist(path)
        check_url(url, allowed)
        return True
    except (UrlRejected, ValueError, Exception) as exc:
        if raise_on_error:
            raise ValueError(f"URL '{url}' is not allowlisted: {exc}") from exc
        return False


def build_exam_alert_message(
    notif: ExamNotification,
    target: ExamTarget | None = None,
) -> str:
    """Build a sanitized plain-text exam alert message for Telegram/chat.

    SEC-26: Alert text uses ONLY configured target title and clean notification headline,
    never raw HTML or external links in the headline. Link previews must be off.

    Format:
    🚨 Exam Alert: <title>
    Exam: <exam_code>
    Notice: <notice title>
    Date: <date>
    Source: <url>
    """
    raw_title = target.title if target is not None else (notif.target_title or notif.target_id)
    raw_exam_code = target.exam_code if target is not None else (notif.exam_code or notif.target_id)

    clean_target_title = clean_exam_notice_title(raw_title)
    clean_exam_code = clean_exam_notice_title(raw_exam_code)
    clean_notice_title = clean_exam_notice_title(notif.title)
    date_str = str(notif.published_date) if notif.published_date is not None else "None"
    url = notif.url.strip()

    return (
        f"🚨 Exam Alert: {clean_target_title}\n"
        f"Exam: {clean_exam_code}\n"
        f"Notice: {clean_notice_title}\n"
        f"Date: {date_str}\n"
        f"Source: {url}"
    )


def compute_notification_hash(target: ExamTarget, notif: ExamNotification) -> str:
    """Compute deterministic SHA-256 hash for notification deduplication."""
    payload = f"{target.id}:{notif.target_id}:{notif.url}:{notif.title}:{notif.published_date}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ExamWatcher:
    """Monitors official exam targets for new notifications with deduplication.

    Validates that URLs belong to allowlisted domains before alerting.
    """

    def __init__(self, allowlist_path: Path | str | None = None) -> None:
        default_path = Path("infra/squid/allowlist.txt")
        self.allowlist_path = Path(allowlist_path) if allowlist_path is not None else default_path

    @staticmethod
    def compute_notification_hash(target: ExamTarget, notif: ExamNotification) -> str:
        """Compute deterministic SHA-256 hash for notification deduplication."""
        return compute_notification_hash(target, notif)

    def detect_new_notifications(
        self,
        target: ExamTarget,
        current_items: list[ExamNotification],
        seen_hashes: set[str],
    ) -> list[ExamNotification]:
        """Identify unseen notifications and record their hashes to prevent re-alerting.

        Validates that both the target URL and notification URLs belong to allowlisted domains.
        Raises ValueError if any URL is not allowlisted.
        """
        if not check_exam_domain_allowlisted(target.url, self.allowlist_path):
            raise ValueError(f"Target URL '{target.url}' is not allowlisted")

        new_items: list[ExamNotification] = []
        for item in current_items:
            if not check_exam_domain_allowlisted(item.url, self.allowlist_path):
                raise ValueError(f"Notification URL '{item.url}' is not allowlisted")

            if not item.exam_code:
                item.exam_code = target.exam_code
            if not item.target_title:
                item.target_title = target.title

            item_hash = self.compute_notification_hash(target, item)
            if item_hash not in seen_hashes:
                seen_hashes.add(item_hash)
                new_items.append(item)

        return new_items
