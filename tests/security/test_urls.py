import pytest

from techradar.security.urls import (
    UrlRejected,
    check_resolved,
    check_url,
    load_allowlist,
    registrable_domain,
)
from tests.fakes import FakeResolver

A = frozenset({"pib.gov.in", ".github.com"})


@pytest.mark.parametrize(
    "url,reason",
    [
        ("http://pib.gov.in/x", "scheme"),
        ("https://u:p@pib.gov.in/", "userinfo"),
        ("https://pib.gov.in:8443/", "port"),
        ("https://127.0.0.1/", "ip_literal"),
        ("https://[::1]/", "ip_literal"),
        ("https://pib.gov.in.evil.com/", "not_allowlisted"),
        ("https://evilpib.gov.in/", "not_allowlisted"),
        ("https://pib.gov.in/" + "a" * 2000, "too_long"),
    ],
)
def test_check_url_rejects(url, reason):
    with pytest.raises(UrlRejected) as e:
        check_url(url, A)
    assert e.value.reason == reason


def test_check_url_ok_and_normalised():
    assert check_url("https://PIB.gov.in/x#frag", A) == "https://pib.gov.in/x"


def test_subdomain_rules_follow_squid():
    assert check_url("https://api.github.com/x", A)
    with pytest.raises(UrlRejected):
        check_url("https://api.github.com/x", frozenset({"github.com"}))


@pytest.mark.parametrize(
    "ips",
    [
        ["10.0.0.5"],
        ["100.101.1.1"],
        ["169.254.169.254"],
        ["::1"],
        ["8.8.8.8", "192.168.1.9"],
    ],
)
async def test_check_resolved_rejects_private(ips):
    with pytest.raises(UrlRejected, match="private"):
        await check_resolved("x", FakeResolver(ips))


async def test_check_resolved_public_ok_and_dns_failure_passes():
    await check_resolved("x", FakeResolver(["8.8.8.8"]))
    await check_resolved("x", FakeResolver(error=OSError()))


def test_registrable_domain():
    assert (
        registrable_domain("www.rbi.org.in") == "rbi.org.in"
        and registrable_domain("news.un.org") == "un.org"
    )


def test_load_allowlist(tmp_path):
    f = tmp_path / "allow.txt"
    f.write_text("# comment\nPIB.GOV.IN\n\n.GITHUB.COM\n")
    allowed = load_allowlist(f)
    assert allowed == frozenset({"pib.gov.in", ".github.com"})
