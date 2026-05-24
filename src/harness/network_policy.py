from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from urllib.parse import urlparse


@dataclass(frozen=True)
class NetworkPolicy:
    allow_hosts: list[str] = field(default_factory=list)
    deny_hosts: list[str] = field(default_factory=list)
    allow_schemes: list[str] = field(default_factory=lambda: ["https"])

    def check_url(self, url: str) -> None:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        host = (parsed.hostname or "").lower()
        if not host:
            raise PermissionError("network URL host is required")
        if scheme not in {item.lower() for item in self.allow_schemes}:
            raise PermissionError(f"network URL scheme is not allowed: {scheme}")
        if _matches_any(host, self.deny_hosts):
            raise PermissionError(f"network host is denied: {host}")
        if self.allow_hosts and not _matches_any(host, self.allow_hosts):
            raise PermissionError(f"network host is not allowed: {host}")


def _matches_any(host: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(host, pattern.lower()) for pattern in patterns)
