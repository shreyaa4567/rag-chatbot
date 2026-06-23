"""Tests for the SSRF guard (app/security.py)."""

import pytest
from app.security import is_safe_url


@pytest.mark.parametrize("url", [
    "http://localhost:5000",
    "http://127.0.0.1",
    "http://192.168.1.10",
    "http://10.0.0.5",
    "http://172.16.0.1",
    "http://169.254.169.254",   # cloud metadata endpoint
    "http://0.0.0.0",
])
def test_blocks_private_and_internal(url):
    ok, reason = is_safe_url(url)
    assert ok is False
    assert reason


@pytest.mark.parametrize("url", [
    "ftp://example.com",
    "file:///etc/passwd",
    "gopher://example.com",
])
def test_blocks_non_http_schemes(url):
    ok, reason = is_safe_url(url)
    assert ok is False


def test_blocks_missing_host():
    ok, _ = is_safe_url("http://")
    assert ok is False


def test_blocks_unresolvable_host():
    ok, _ = is_safe_url("http://nonexistent.invalid.tld.example")
    assert ok is False


@pytest.mark.parametrize("url", [
    "http://example.com",
    "https://example.com/path?q=1",
])
def test_allows_public_urls(url):
    ok, reason = is_safe_url(url)
    assert ok is True
    assert reason == ""
