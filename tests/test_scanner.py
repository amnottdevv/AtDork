"""
Unit tests for core.scanner module.
Mocks DDGS to avoid real network calls.
"""

import pytest
from unittest.mock import patch, MagicMock

from core.scanner import (
    search_dork,
    SearchError,
    RateLimitError,
    BlockedError,
    ProxyError,
    ParseError,
    EmptyResultsError,
)
from core.proxy_manager import ProxyManager


# ── Fixtures ──────────────────────────────────────────────────────────────

@pytest.fixture
def mock_ddgs_success():
    """Mocks DDGS that returns valid results."""
    with patch("core.scanner.DDGS") as mock_ddgs:
        instance = MagicMock()
        instance.text.return_value = [
            {"title": "Test Result", "href": "https://example.com", "body": "Snippet text"},
            {"title": "Another", "href": "https://test.org", "body": "More text"},
        ]
        mock_ddgs.return_value = instance
        yield mock_ddgs


@pytest.fixture
def mock_ddgs_empty():
    """Mocks DDGS that returns empty list."""
    with patch("core.scanner.DDGS") as mock_ddgs:
        instance = MagicMock()
        instance.text.return_value = []
        mock_ddgs.return_value = instance
        yield mock_ddgs


@pytest.fixture
def mock_ddgs_rate_limit():
    """Mocks DDGS that raises a rate-limit error."""
    with patch("core.scanner.DDGS") as mock_ddgs:
        instance = MagicMock()
        instance.text.side_effect = Exception("HTTP 429 Too Many Requests")
        mock_ddgs.return_value = instance
        yield mock_ddgs


@pytest.fixture
def sample_proxy_manager():
    """A simple proxy manager with one valid proxy."""
    return ProxyManager(
        proxies=["http://proxy1:8080"],
        cooldown_seconds=60,
        strict=False,
        max_failures=0,
    )


# ── Test Cases ────────────────────────────────────────────────────────────

def test_search_dork_success(mock_ddgs_success):
    """Should return a list of results when everything works."""
    results = search_dork("test query", max_results=5)
    assert len(results) == 2
    assert results[0]["title"] == "Test Result"
    assert results[0]["href"] == "https://example.com"


def test_search_dork_empty_results(mock_ddgs_empty):
    """Should raise EmptyResultsError when no results are returned."""
    with pytest.raises(SearchError):
        search_dork("test query", max_results=5)


def test_search_dork_rate_limit(mock_ddgs_rate_limit):
    """Should raise SearchError after exhausting retries on rate limit."""
    with pytest.raises(SearchError):
        search_dork("test query", max_results=5, retries=1)


def test_search_dork_with_proxy(mock_ddgs_success, sample_proxy_manager):
    """Should use proxy from proxy_manager and return results."""
    results = search_dork("test query", max_results=5, proxy_manager=sample_proxy_manager)
    assert len(results) == 2


def test_search_dork_proxy_failure_then_success(mock_ddgs_success, sample_proxy_manager):
    """Should rotate proxy after failure and eventually succeed."""
    # Make the first call fail, second succeed
    call_count = [0]

    def side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            raise Exception("Proxy connection failed")
        return [
            {"title": "Rescued", "href": "https://rescue.com", "body": "Success"}
        ]

    mock_ddgs_success.return_value.text.side_effect = side_effect
    results = search_dork("test query", max_results=5, proxy_manager=sample_proxy_manager, retries=2)
    assert len(results) == 1
    assert results[0]["title"] == "Rescued"


def test_search_dork_custom_user_agent(mock_ddgs_success):
    """Should accept and use custom User-Agent."""
    ua = "MyTestBot/2.0"
    results = search_dork("test query", user_agent=ua)
    assert len(results) == 2


def test_search_dork_validate_results():
    """Should fill missing titles with href."""
    with patch("core.scanner.DDGS") as mock_ddgs:
        instance = MagicMock()
        instance.text.return_value = [
            {"href": "https://example.com", "body": "No title"},
            {"title": "", "href": "https://test.org", "body": "Empty title"},
        ]
        mock_ddgs.return_value = instance
        results = search_dork("test query")
        assert results[0]["title"] == "https://example.com"
        assert results[1]["title"] == "https://test.org"


def test_search_dork_with_region_and_time(mock_ddgs_success):
    """Should pass region and timelimit parameters to DDGS."""
    results = search_dork("test", region="uk-en", timelimit="w")
    assert len(results) == 2
    # Verify DDGS.text was called with correct params
    mock_ddgs_success.return_value.text.assert_called_once_with(
        "test",
        region="uk-en",
        safesearch="moderate",
        timelimit="w",
        max_results=20,
        backend="auto",
    )


def test_search_dork_fallback_backends():
    """Should try fallback backends if main backend fails."""
    call_count = [0]

    def side_effect(*args, **kwargs):
        call_count[0] += 1
        # Fail for first two backends (bing + first fallback), succeed on third
        if call_count[0] <= 2:
            raise Exception("Backend error")
        return [{"title": "Fallback", "href": "https://fallback.com", "body": "OK"}]

    with patch("core.scanner.DDGS") as mock_ddgs:
        instance = MagicMock()
        instance.text.side_effect = side_effect
        mock_ddgs.return_value = instance
        # Use a specific backend, not 'auto', to enable fallback chain
        results = search_dork("test", backend="bing", fallback_backends=True, retries=0)
        assert len(results) == 1
        assert results[0]["title"] == "Fallback"