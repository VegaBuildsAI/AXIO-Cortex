"""Shared outbound-network policy for AXIO Code web and browser tools."""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


class UnsafeUrlError(ValueError):
    pass


def validate_public_url(url: str, *, resolve: bool = True) -> str:
    """Validate a public HTTP(S) URL and reject SSRF-relevant destinations."""
    parsed = urlparse(str(url).strip())
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeUrlError("Only http:// and https:// URLs are allowed")
    if not parsed.hostname:
        raise UnsafeUrlError("URL must include a hostname")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("Credentials in URLs are not allowed")

    hostname = parsed.hostname.rstrip(".").casefold()
    if hostname == "localhost" or hostname.endswith(".localhost"):
        raise UnsafeUrlError("Localhost is blocked")

    addresses: set[str] = set()
    try:
        addresses.add(str(ipaddress.ip_address(hostname)))
    except ValueError:
        if resolve:
            try:
                addresses.update(
                    item[4][0]
                    for item in socket.getaddrinfo(hostname, parsed.port or 443, type=socket.SOCK_STREAM)
                )
            except OSError as exc:
                raise UnsafeUrlError(f"Hostname could not be resolved: {hostname}") from exc

    for raw in addresses:
        address = ipaddress.ip_address(raw)
        if not address.is_global:
            raise UnsafeUrlError(f"Private, local, reserved, or non-global address is blocked: {address}")
    return parsed.geturl()


def route_url_is_allowed(url: str) -> bool:
    """Allow browser-internal data/blob/about resources and public HTTP(S)."""
    scheme = urlparse(url).scheme.casefold()
    if scheme in {"data", "blob", "about"}:
        return True
    try:
        validate_public_url(url)
        return True
    except (UnsafeUrlError, ValueError):
        return False
