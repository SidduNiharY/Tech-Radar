from __future__ import annotations

import ipaddress
import urllib.parse
from pathlib import Path
from typing import Literal, Protocol

import tldextract

UrlRejectReason = Literal[
    "scheme",
    "userinfo",
    "port",
    "ip_literal",
    "not_allowlisted",
    "private_address",
    "too_long",
    "too_many_redirects",
]


class UrlRejected(Exception):
    def __init__(self, reason: UrlRejectReason, message: str | None = None) -> None:
        super().__init__(message or f"URL rejected: {reason}")
        self.reason: UrlRejectReason = reason


_SHARED_EXTRACTOR = tldextract.TLDExtract(suffix_list_urls=())
_CARRIER_GRADE_NAT = ipaddress.ip_network("100.64.0.0/10")


def load_allowlist(path: Path) -> frozenset[str]:
    """Load lowercase domain allowlist from file, ignoring comments and blanks."""
    allowed: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip().lower()
        if not line or line.startswith("#"):
            continue
        allowed.add(line)
    return frozenset(allowed)


def host_allowed(host: str, allowed: frozenset[str]) -> bool:
    """Check if host matches Squid dstdomain semantics.

    An entry without a leading dot matches exact host.
    An entry with a leading dot matches the domain and any subdomain.
    """
    host = host.lower()
    for pattern in allowed:
        pattern = pattern.lower()
        if pattern.startswith("."):
            domain = pattern[1:]
            if host == domain or host.endswith("." + domain):
                return True
        else:
            if host == pattern:
                return True
    return False


def check_url(url: str, allowed: frozenset[str]) -> str:
    """Validate and normalize a URL against scheme, port, userinfo, IP literal, and allowlist."""
    if len(url) > 2000:
        raise UrlRejected("too_long", "URL exceeds maximum length of 2000 characters")

    parsed = urllib.parse.urlsplit(url)

    if parsed.scheme != "https":
        raise UrlRejected("scheme", f"Scheme '{parsed.scheme}' is not allowed; must be https")

    if parsed.username or parsed.password:
        raise UrlRejected("userinfo", "Userinfo in URL is forbidden")

    if parsed.port is not None and parsed.port != 443:
        raise UrlRejected("port", f"Non-standard port '{parsed.port}' is forbidden")

    hostname = parsed.hostname
    if not hostname:
        raise UrlRejected("not_allowlisted", "Hostname is missing")

    # Check for IP literal (IPv4 or IPv6)
    try:
        ipaddress.ip_address(hostname)
        raise UrlRejected("ip_literal", "IP literals are forbidden in URLs")
    except ValueError:
        pass

    try:
        norm_host = hostname.encode("idna").decode("ascii").lower()
    except Exception as exc:
        raise UrlRejected("not_allowlisted", f"Failed to encode hostname: {exc}") from exc

    if not host_allowed(norm_host, allowed):
        raise UrlRejected("not_allowlisted", f"Host '{norm_host}' is not in allowlist")

    # Reconstruct normalized URL with lowercase host and no fragment
    path = parsed.path or "/"
    if parsed.query:
        return f"https://{norm_host}{path}?{parsed.query}"
    return f"https://{norm_host}{path}"


class Resolver(Protocol):
    async def resolve(self, host: str) -> list[str]: ...


async def check_resolved(host: str, resolver: Resolver) -> None:
    """Check resolved IP addresses for host against private and internal subnets."""
    try:
        ips = await resolver.resolve(host)
    except OSError:
        return

    for ip_str in ips:
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue

        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
            or ip in _CARRIER_GRADE_NAT
        ):
            raise UrlRejected(
                "private_address",
                f"Host '{host}' resolved to private or internal address: {ip_str}",
            )


def registrable_domain(host: str) -> str:
    """Extract registrable domain using offline public suffix list snapshot."""
    extracted = _SHARED_EXTRACTOR(host)
    if hasattr(extracted, "top_domain_under_public_suffix"):
        domain = extracted.top_domain_under_public_suffix
    else:
        domain = extracted.registered_domain
    return domain or host.lower()
