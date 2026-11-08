import subprocess

import pytest

pytestmark = pytest.mark.egress


def probe(*args):
    return subprocess.run(
        ["docker", "compose", "--profile", "test", "run", "--rm", "egress-probe", *args],
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_allowlisted_https_ok():
    r = probe("-sS", "-o", "/dev/null", "-w", "%{http_code}", "https://api.telegram.org/")
    assert r.returncode == 0 and r.stdout != "000"


def test_not_allowlisted_denied():
    r = probe("-sS", "https://example.com/")
    assert r.returncode != 0 and "403" in r.stderr


@pytest.mark.parametrize(
    "url",
    [
        "https://192.168.1.1/",
        "http://169.254.169.254/",
        "https://10.0.0.1/",
        "https://100.100.100.100/",
    ],
)
def test_private_and_metadata_addresses_denied(url):
    assert probe("-sS", "--max-time", "10", url).returncode != 0


def test_plain_http_denied():
    r = probe("-sS", "-o", "/dev/null", "-w", "%{http_code}", "http://api.telegram.org/")
    assert r.stdout == "403"


def test_no_direct_internet_without_proxy():
    assert (
        probe("-sS", "--max-time", "10", "--noproxy", "*", "https://api.telegram.org/").returncode
        != 0
    )
