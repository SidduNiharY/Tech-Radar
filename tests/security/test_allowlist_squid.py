"""Squid refuses to start if the allowlist repeats a domain (dstdomain rules).

".x.org" already means x.org and every subdomain; listing "x.org" or
"sub.x.org" next to it is a fatal config error ("is a subdomain of"), which
stopped the egress proxy on the TUF.
"""

from pathlib import Path

ALLOWLIST = Path("infra/squid/allowlist.txt")


def entries() -> list[str]:
    lines = ALLOWLIST.read_text(encoding="utf-8").splitlines()
    return [ln.strip().lower() for ln in lines if ln.strip() and not ln.strip().startswith("#")]


def test_no_duplicate_entries():
    e = entries()
    assert len(e) == len(set(e))


def test_no_entry_covered_by_a_dotted_parent():
    e = entries()
    parents = [p for p in e if p.startswith(".")]
    covered = [
        x
        for x in e
        for p in parents
        if x != p and (x == p[1:] or x.endswith(p) or (x.startswith(".") and x[1:].endswith(p)))
    ]
    assert covered == []
