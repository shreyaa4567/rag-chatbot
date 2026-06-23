# app/security.py
"""Security helpers that are free of import-time side effects so they can be
unit-tested and reused independently of the Flask app."""

import socket
import ipaddress
from urllib.parse import urlparse


def is_safe_url(url):
    """Reject URLs that resolve to private/internal addresses (SSRF guard).

    Blocks localhost, link-local (169.254.x.x), and the RFC 1918 private
    ranges (10.x, 172.16-31.x, 192.168.x) as well as other reserved/
    loopback/multicast addresses.

    Returns:
        (ok: bool, reason: str) — ok is False with a human-readable reason
        when the URL must be rejected.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False, "Only http and https URLs are allowed."

    host = parsed.hostname
    if not host:
        return False, "URL has no host."

    try:
        # Resolve every address the host maps to and check them all.
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False, "Could not resolve host."

    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False, "URL points to a private or internal address."

    return True, ""
