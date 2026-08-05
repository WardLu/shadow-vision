"""Remote image fetching with SSRF protection (F1).

Protections: scheme allowlist, userinfo rejection, private/loopback/link-local
IP blocklist (IPv4 + IPv6), DNS resolution verification, disabled redirects,
response size limit, image content-type check, and an independent timeout.

Residual risk: a DNS-rebinding window exists between `getaddrinfo` validation
and the actual httpx connection. Full protection requires a custom httpx
transport that pins the resolved IP; for a local MCP process this risk is low.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import httpx

from .config import Config

_CGNAT = ipaddress.ip_network("100.64.0.0/10")


def _is_private_ip(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    if addr.version == 6 and addr.ipv4_mapped is not None:
        return _is_private_ip(str(addr.ipv4_mapped))
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
        or (addr.version == 4 and addr in _CGNAT)
    )


def is_safe_url(url: str, *, allow_private: bool = False) -> tuple[bool, str]:
    """Validate scheme, host and resolved IPs. Returns (ok, reason)."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False, "invalid url"
    if parsed.scheme not in ("http", "https"):
        return False, f"unsupported scheme: {parsed.scheme}"
    if parsed.username or parsed.password:
        return False, "url must not contain userinfo"
    host = parsed.hostname
    if not host:
        return False, "missing host"
    try:
        infos = socket.getaddrinfo(host, parsed.port or 80, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return False, "dns resolution failed"
    for info in infos:
        ip = info[4][0]
        if not allow_private and _is_private_ip(ip):
            return False, f"blocked address: {ip}"
    return True, ""


def fetch_image_from_url(url: str, config: Config) -> tuple[bytes, str]:
    """Fetch a remote image, returning (bytes, mime). Raises ValueError on any
    SSRF, redirect, non-image, or size-limit violation."""
    ok, reason = is_safe_url(url, allow_private=config.ssrf_allow_private)
    if not ok:
        raise ValueError(reason)
    timeout = httpx.Timeout(config.fetch_timeout)
    with httpx.Client(follow_redirects=False, timeout=timeout) as client:
        with client.stream("GET", url) as resp:
            if resp.status_code >= 300:
                raise ValueError(f"redirects not allowed (status {resp.status_code})")
            ctype = resp.headers.get("content-type", "")
            if not ctype.startswith("image/"):
                raise ValueError(f"not an image: {ctype}")
            data = bytearray()
            for chunk in resp.iter_bytes():
                data.extend(chunk)
                if len(data) > config.max_remote_size:
                    raise ValueError(f"remote image exceeds size limit ({config.max_remote_size})")
            return bytes(data), ctype
