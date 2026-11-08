from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from techradar.exams.watcher import (
    ExamNotification,
    ExamTarget,
    ExamWatcher,
    build_exam_alert_message,
    check_exam_domain_allowlisted,
    clean_exam_notice_title,
    compute_notification_hash,
)


def test_link_not_allowlisted_rejected(tmp_path: Path):
    allowlist_file = tmp_path / "allowlist.txt"
    allowlist_file.write_text("ssc.gov.in\nrbi.org.in\n.ibps.in\n", encoding="utf-8")

    # Non-allowlisted domain returns False
    assert not check_exam_domain_allowlisted(
        "https://evil-phish.com/exam", allowlist_path=allowlist_file
    )
    assert not check_exam_domain_allowlisted(
        "https://ssc.gov.in.evil.com/notice", allowlist_path=allowlist_file
    )

    # Insecure HTTP scheme returns False
    assert not check_exam_domain_allowlisted(
        "http://ssc.gov.in/notice", allowlist_path=allowlist_file
    )

    # Allowlisted domain returns True
    assert check_exam_domain_allowlisted(
        "https://ssc.gov.in/cgl2026", allowlist_path=allowlist_file
    )
    assert check_exam_domain_allowlisted(
        "https://subdomain.ibps.in/crp", allowlist_path=allowlist_file
    )

    # raise_on_error=True raises ValueError on rejected URLs
    with pytest.raises(ValueError, match="not allowlisted"):
        check_exam_domain_allowlisted(
            "https://evil.com/alert",
            allowlist_path=allowlist_file,
            raise_on_error=True,
        )

    # Missing allowlist file handling
    assert not check_exam_domain_allowlisted(
        "https://ssc.gov.in/cgl", allowlist_path=tmp_path / "missing.txt"
    )
    with pytest.raises(ValueError, match="file not found"):
        check_exam_domain_allowlisted(
            "https://ssc.gov.in/cgl",
            allowlist_path=tmp_path / "missing.txt",
            raise_on_error=True,
        )

    # ExamWatcher raises ValueError when target URL is not allowlisted
    watcher = ExamWatcher(allowlist_path=allowlist_file)
    evil_target = ExamTarget(
        id="evil_gate",
        title="Fake GATE",
        url="https://evil.com/gate",
        exam_code="GATE_CS",
    )
    with pytest.raises(ValueError, match="Target URL .* is not allowlisted"):
        watcher.detect_new_notifications(evil_target, [], set())

    # ExamWatcher raises ValueError when notification URL is not allowlisted
    good_target = ExamTarget(
        id="ssc",
        title="Staff Selection Commission",
        url="https://ssc.gov.in",
        exam_code="SSC_CGL",
    )
    evil_notif = ExamNotification(
        target_id="ssc",
        title="Admit Card",
        url="https://evil.com/phish",
    )
    with pytest.raises(ValueError, match="Notification URL .* is not allowlisted"):
        watcher.detect_new_notifications(good_target, [evil_notif], set())


def test_exam_alert_text_never_includes_raw_html_or_script():
    malicious_inputs = [
        "<script>alert('xss')</script> GATE CS 2026 Schedule",
        "<SCRIPT SRC='https://evil.com/xss.js'></SCRIPT>SSC CGL Tier 1",
        "Admit Card <img src=x onerror=alert('hack')> Released",
        "<b>Important:</b> Check updates at <a href='https://evil.com'>evil.com</a>",
        "&lt;script&gt;alert(1)&lt;/script&gt; Notification Released",
        "<iframe src='javascript:alert(1)'></iframe>Exam Dates",
        "<style>body { display: none; }</style>Postponed notice",
        "Exam Notice <svg/onload=alert('svg')> Out Now",
        "Schedule announced! Check https://phish-site.org/fake for info",
    ]

    target = ExamTarget(
        id="gate_target",
        title="GATE 2026 Organizing Committee",
        url="https://gate.iitk.ac.in",
        exam_code="GATE_CS",
    )

    for raw_title in malicious_inputs:
        notif = ExamNotification(
            target_id="gate_target",
            title=raw_title,
            published_date=date(2026, 11, 8),
            url="https://ssc.gov.in/gate",
            exam_code="GATE_CS",
            target_title="GATE 2026 Organizing Committee",
        )
        msg = build_exam_alert_message(notif, target=target)

        # Ensure no raw HTML tags or script payloads exist in the alert message
        assert "<script" not in msg.lower()
        assert "</script" not in msg.lower()
        assert "<img" not in msg.lower()
        assert "<a " not in msg.lower()
        assert "<iframe" not in msg.lower()
        assert "<style" not in msg.lower()
        assert "<svg" not in msg.lower()
        assert "alert(" not in msg

        # Ensure no unescaped angle brackets in the notice line
        lines = msg.splitlines()
        notice_line = next(line for line in lines if line.startswith("Notice:"))
        assert "<" not in notice_line
        assert ">" not in notice_line

        # Ensure headline does not contain external links
        assert "evil.com" not in notice_line
        assert "phish-site.org" not in notice_line

        # Verify exact header and structure
        assert lines[0] == "🚨 Exam Alert: GATE 2026 Organizing Committee"
        assert lines[1] == "Exam: GATE_CS"
        assert lines[3] == "Date: 2026-11-08"
        assert lines[4] == "Source: https://ssc.gov.in/gate"


def test_duplicate_notifications_suppressed(tmp_path: Path):
    allowlist_file = tmp_path / "allowlist.txt"
    allowlist_file.write_text("ssc.gov.in\n", encoding="utf-8")

    watcher = ExamWatcher(allowlist_path=allowlist_file)
    target = ExamTarget(
        id="ssc_cgl",
        title="Staff Selection Commission",
        url="https://ssc.gov.in/cgl",
        exam_code="SSC_CGL",
    )
    notif1 = ExamNotification(
        target_id="ssc_cgl",
        title="Tier 1 Schedule Released",
        published_date=date(2026, 11, 8),
        url="https://ssc.gov.in/cgl/notice1",
    )
    notif2 = ExamNotification(
        target_id="ssc_cgl",
        title="Answer Keys Out",
        published_date=date(2026, 11, 9),
        url="https://ssc.gov.in/cgl/notice2",
    )

    seen_hashes: set[str] = set()

    # First run: notif1 is new
    first_detected = watcher.detect_new_notifications(target, [notif1], seen_hashes)
    assert len(first_detected) == 1
    assert first_detected[0].title == notif1.title
    assert len(seen_hashes) == 1

    # Second run with same notification: suppressed
    second_detected = watcher.detect_new_notifications(target, [notif1], seen_hashes)
    assert len(second_detected) == 0
    assert len(seen_hashes) == 1

    # Third run with notif1 and notif2: only notif2 is returned
    third_detected = watcher.detect_new_notifications(target, [notif1, notif2], seen_hashes)
    assert len(third_detected) == 1
    assert third_detected[0].title == notif2.title
    assert len(seen_hashes) == 2

    # Fourth run with all seen: empty list
    fourth_detected = watcher.detect_new_notifications(target, [notif1, notif2], seen_hashes)
    assert len(fourth_detected) == 0
    assert len(seen_hashes) == 2


def test_build_exam_alert_message_formatting():
    # Without explicit target passed, uses notif fields
    notif = ExamNotification(
        target_id="rbi_b",
        title="RBI Grade B 2026 Phase 1 Results",
        published_date=date(2026, 12, 1),
        url="https://rbi.org.in/results",
        exam_code="RBI_GRADE_B",
        target_title="Reserve Bank of India",
    )
    rendered = build_exam_alert_message(notif)
    expected = (
        "🚨 Exam Alert: Reserve Bank of India\n"
        "Exam: RBI_GRADE_B\n"
        "Notice: RBI Grade B 2026 Phase 1 Results\n"
        "Date: 2026-12-01\n"
        "Source: https://rbi.org.in/results"
    )
    assert rendered == expected

    # When published_date is None, displays None
    notif_no_date = ExamNotification(
        target_id="gate",
        title="Information Brochure",
        url="https://gate.iitk.ac.in/brochure",
    )
    rendered_no_date = build_exam_alert_message(notif_no_date)
    assert "Date: None" in rendered_no_date
    assert "🚨 Exam Alert: gate" in rendered_no_date
    assert "Exam: gate" in rendered_no_date
    assert "Notice: Information Brochure" in rendered_no_date
    assert "Source: https://gate.iitk.ac.in/brochure" in rendered_no_date


def test_compute_notification_hash_deterministic():
    target = ExamTarget(
        id="t1",
        title="Title",
        url="https://ssc.gov.in",
        exam_code="SSC",
    )
    notif = ExamNotification(
        target_id="t1",
        title="Notice 1",
        published_date=date(2026, 1, 1),
        url="https://ssc.gov.in/1",
    )
    h1 = compute_notification_hash(target, notif)
    h2 = ExamWatcher.compute_notification_hash(target, notif)
    assert h1 == h2
    assert len(h1) == 64  # sha256 hex length


def test_clean_exam_notice_title_edge_cases():
    assert clean_exam_notice_title("") == ""
    assert clean_exam_notice_title("   ") == ""
    assert clean_exam_notice_title("Clean Title") == "Clean Title"
    # Normalizes spaces and newlines
    assert clean_exam_notice_title("Line 1\n\nLine 2\tEnd") == "Line 1 Line 2 End"
