from datetime import date, timedelta

import pytest

from techradar.intake.av import AvResult, IntakeWait, check_av

TODAY = date(2026, 11, 8)


def test_av_infected_fetched_rejected_my_file_quarantined():
    bad = AvResult(status="infected", signature="Eicar-Signature", db_date=TODAY)
    assert check_av(bad, "fetch", TODAY).outcome == "reject"
    assert check_av(bad, "telegram", TODAY).outcome == "quarantine"


def test_av_down_or_stale_waits():
    with pytest.raises(IntakeWait):
        check_av(AvResult(status="error", signature=None, db_date=None), "fetch", TODAY)

    with pytest.raises(IntakeWait):
        check_av(
            AvResult(status="clean", signature=None, db_date=TODAY - timedelta(days=4)),
            "fetch",
            TODAY,
        )


def test_av_clean_passes():
    clean = AvResult(status="clean", signature=None, db_date=TODAY)
    assert check_av(clean, "fetch", TODAY).outcome == "ok"
