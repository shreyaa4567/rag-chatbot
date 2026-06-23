"""Tests for crawler URL handling (app/crawler.py)."""

from app.crawler import normalize_url, is_same_domain, get_base_domain


def test_normalize_strips_fragment():
    assert normalize_url("http://a.com/page#section") == "http://a.com/page"


def test_normalize_strips_trailing_slash_but_keeps_root():
    assert normalize_url("http://a.com/page/") == "http://a.com/page"
    assert normalize_url("http://a.com/") == "http://a.com/"


def test_normalize_lowercases_host_and_scheme():
    assert normalize_url("HTTP://A.COM/Page") == "http://a.com/Page"


def test_normalize_drops_default_ports():
    assert normalize_url("http://a.com:80/x") == "http://a.com/x"
    assert normalize_url("https://a.com:443/x") == "https://a.com/x"


def test_normalize_keeps_query():
    assert normalize_url("http://a.com/s?q=1") == "http://a.com/s?q=1"


def test_base_domain_uses_domain_plus_suffix():
    assert get_base_domain("https://www.example.co.uk/x") == "example.co.uk"


def test_same_domain_matches_subdomains():
    base = get_base_domain("https://example.com")
    assert is_same_domain("https://blog.example.com/post", base) is True


def test_same_domain_rejects_lookalike():
    base = get_base_domain("https://example.com")
    # A different registered domain that merely contains the word "example".
    assert is_same_domain("https://example.org", base) is False
    assert is_same_domain("https://notexample.com.evil.com", base) is False
