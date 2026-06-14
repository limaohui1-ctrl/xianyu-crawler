"""DomainInput — normalize and validate domain/URL input."""
import re
from dataclasses import dataclass, asdict
from urllib.parse import urlparse
from typing import Optional


_PRIVATE_IP = re.compile(
    r"^(127\.\d+\.\d+\.\d+|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)$"
)

BLOCKED_PROTOCOLS = {"javascript:", "file:", "data:", "mailto:", "ftp:"}


@dataclass
class DomainInput:
    raw: str = ""
    normalized_base_url: str = ""
    domain: str = ""
    scheme: str = "https"
    root_url: str = ""
    is_valid: bool = False
    reason: str = ""

    def to_dict(self):
        return asdict(self)


def parse_domain(raw: str) -> DomainInput:
    """Parse user input into a normalized DomainInput.

    Handles: bare domain, www subdomain, full URL, URL with path.
    Rejects: localhost, private IPs, javascript/file/data protocols.
    """
    raw = raw.strip()
    if not raw:
        return DomainInput(raw=raw, reason="empty input")

    # Reject blocked protocols
    lower = raw.lower()
    for proto in BLOCKED_PROTOCOLS:
        if lower.startswith(proto):
            return DomainInput(raw=raw, reason=f"protocol not allowed: {proto}")

    # Add scheme if missing
    if "://" not in raw:
        raw = "https://" + raw

    parsed = urlparse(raw)
    host = parsed.hostname or ""

    if not host:
        return DomainInput(raw=raw, reason="could not parse domain")

    # Reject localhost
    if host in ("localhost", "0.0.0.0", "::1"):
        return DomainInput(raw=raw, domain=host, reason="localhost not allowed")

    # Reject private IPs
    if _PRIVATE_IP.match(host):
        return DomainInput(raw=raw, domain=host, reason="private IP not allowed")

    # Normalize: lowercase only. Keep www — some sites differ at root.
    domain = host.lower()

    scheme = parsed.scheme or "https"
    root_url = f"{scheme}://{domain}"

    return DomainInput(
        raw=raw,
        normalized_base_url=root_url.rstrip("/"),
        domain=domain,
        scheme=scheme,
        root_url=root_url,
        is_valid=True,
        reason="",
    )
