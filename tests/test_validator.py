"""
Unit tests for lib.validator module.
Covers URL validation, spam detection, result filtering, and statistics.
"""

import pytest
from lib.validator import (
    is_valid_url,
    is_spam_text,
    is_valid_result,
    filter_results,
    get_filter_stats,
)


# ── is_valid_url ──────────────────────────────────────────────────────────

def test_valid_http_url():
    assert is_valid_url("http://example.com/path") is True


def test_valid_https_url():
    assert is_valid_url("https://sub.example.org/page?q=1") is True


def test_valid_ftp_url():
    assert is_valid_url("ftp://files.example.com") is True


def test_invalid_no_scheme():
    assert is_valid_url("example.com") is False


def test_invalid_no_host():
    assert is_valid_url("http:///path") is False


def test_invalid_no_dot_in_host():
    assert is_valid_url("http://localhost") is False  # tidak ada titik


def test_invalid_weird_scheme():
    assert is_valid_url("gopher://example.com") is False


def test_invalid_empty_string():
    assert is_valid_url("") is False


def test_invalid_none():
    assert is_valid_url(None) is False


def test_invalid_missing_port_not_needed():  # port tidak wajib untuk validasi
    assert is_valid_url("http://example.com") is True


# ── is_spam_text ─────────────────────────────────────────────────────────

def test_spam_buy_now():
    assert is_spam_text("Buy now and get discount") is True


def test_spam_free_money():
    assert is_spam_text("Earn free money fast") is True


def test_spam_casino():
    assert is_spam_text("Online casino and poker") is True


def test_spam_adult():
    assert is_spam_text("Adult xxx content") is True


def test_spam_seo():
    assert is_spam_text("Best SEO backlink service") is True


def test_spam_suspicious_tld():
    assert is_spam_text("Visit my site.xyz for offers") is True


def test_not_spam_normal_text():
    assert is_spam_text("How to bake a cake") is False


def test_not_spam_empty_string():
    assert is_spam_text("") is False


def test_not_spam_none():
    assert is_spam_text(None) is False


# ── is_valid_result ─────────────────────────────────────────────────────

def test_valid_result_full():
    result = {
        "title": "My Page Title",
        "href": "https://example.com",
        "body": "This is a snippet of the page content."
    }
    assert is_valid_result(result) is True


def test_valid_result_minimal():
    # Judul minimal 5 karakter (MIN_TITLE_LENGTH = 5)
    result = {
        "title": "Valid",
        "href": "https://a.co",
        "body": "Short"
    }
    assert is_valid_result(result) is True


def test_invalid_result_bad_url():
    result = {
        "title": "Good Title",
        "href": "not-a-url",
        "body": "Some description"
    }
    assert is_valid_result(result) is False


def test_invalid_result_spam_title():
    result = {
        "title": "Buy now cheap pills",
        "href": "https://example.com",
        "body": "Not spam body"
    }
    assert is_valid_result(result) is False


def test_invalid_result_spam_body():
    result = {
        "title": "Nice article",
        "href": "https://example.com",
        "body": "Visit our casino online"
    }
    assert is_valid_result(result) is False


def test_invalid_result_short_title():
    result = {
        "title": "AB",   # kurang dari MIN_TITLE_LENGTH (5)
        "href": "https://example.com",
        "body": "Valid body"
    }
    assert is_valid_result(result) is False


def test_strict_mode_no_body():
    result = {
        "title": "A valid title",
        "href": "https://example.com",
        "body": ""          # empty
    }
    # non-strict: ok, strict: not ok
    assert is_valid_result(result, strict=False) is True
    assert is_valid_result(result, strict=True) is False


def test_strict_mode_short_body():
    result = {
        "title": "A valid title",
        "href": "https://example.com",
        "body": "Short"      # kurang dari MIN_BODY_LENGTH (10)
    }
    assert is_valid_result(result, strict=False) is True
    assert is_valid_result(result, strict=True) is False


# ── filter_results ───────────────────────────────────────────────────────

def test_filter_results_all_valid():
    data = [
        {"title": "First",  "href": "http://a.com", "body": "body1"},
        {"title": "Second", "href": "http://b.com", "body": "body2"},
    ]
    filtered = filter_results(data)
    assert len(filtered) == 2


def test_filter_results_all_invalid():
    data = [
        {"title": "X", "href": "bad", "body": "x"},
        {"title": "Buy now", "href": "http://b.com", "body": "x"},
    ]
    filtered = filter_results(data)
    assert len(filtered) == 0


def test_filter_results_mixed():
    data = [
        {"title": "Good One", "href": "http://a.com", "body": "valid"},
        {"title": "Free money here", "href": "http://b.com", "body": "valid"},  # spam title
        {"title": "Another Good", "href": "http://c.com", "body": "casino"},    # spam body
        {"title": "Invalid url", "href": "not", "body": "x"},
    ]
    filtered = filter_results(data)
    assert len(filtered) == 1
    assert filtered[0]["title"] == "Good One"


def test_filter_results_strict():
    data = [
        {"title": "Valid Title", "href": "http://a.com", "body": "This is long enough body"},
        {"title": "Another Valid", "href": "http://b.com", "body": "Short"},   # <10, strict will reject
    ]
    filtered = filter_results(data, strict=True)
    assert len(filtered) == 1


def test_filter_results_empty_input():
    assert filter_results([]) == []


def test_filter_results_none_input():
    # Jika None, akan dianggap sebagai list kosong
    assert filter_results(None) == []


# ── get_filter_stats ─────────────────────────────────────────────────────

def test_get_filter_stats():
    stats = get_filter_stats(original=10, filtered=7)
    assert stats["original"] == 10
    assert stats["filtered"] == 7
    assert stats["removed"] == 3


def test_get_filter_stats_no_removal():
    stats = get_filter_stats(original=5, filtered=5)
    assert stats["removed"] == 0