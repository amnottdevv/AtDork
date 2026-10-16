"""
Unit tests for core.batch_runner module (upgraded with case modules).
"""

import pytest
from unittest.mock import patch, MagicMock
from core.batch_runner import load_queries_from_file, parse_query_string, run_batch
from core.case.circuit_breaker import CircuitBreaker
from core.case.fallback_manager import FallbackManager
from core.case.retry_handler import RetryHandler
from core.case.adaptive_delay import AdaptiveDelay

from core.manage_cache import SearchCache


@pytest.fixture(autouse=True)
def fast_cooldown(monkeypatch):
    """Jangan jeda 30 detik saat FallbackManager memutuskan action 'cooldown'.

    (Suite lama butuh ~30 detik hanya gara-gara satu test yang memicu cooldown.)
    """
    monkeypatch.setattr("core.batch_runner.COOLDOWN_SLEEP_SECONDS", 0.0)


# ── load_queries_from_file ──────────────────────────────────────────────

def test_load_queries_from_file_basic(tmp_path):
    file = tmp_path / "dorks.txt"
    file.write_text("query one\nquery two\nquery three\n")
    queries = load_queries_from_file(str(file))
    assert queries == ["query one", "query two", "query three"]


def test_load_queries_from_file_skip_empty_lines(tmp_path):
    file = tmp_path / "dorks.txt"
    file.write_text("query one\n\n\nquery two\n   \nquery three\n")
    queries = load_queries_from_file(str(file))
    assert queries == ["query one", "query two", "query three"]


def test_load_queries_from_file_skip_comments(tmp_path):
    file = tmp_path / "dorks.txt"
    file.write_text("# This is a comment\nquery one\n# another comment\nquery two\n")
    queries = load_queries_from_file(str(file))
    assert queries == ["query one", "query two"]


def test_load_queries_from_file_empty_file(tmp_path):
    file = tmp_path / "dorks.txt"
    file.write_text("")
    queries = load_queries_from_file(str(file))
    assert queries == []


# ── parse_query_string ──────────────────────────────────────────────────

def test_parse_query_string_default_separator():
    queries = parse_query_string("dork1;dork2;dork3")
    assert queries == ["dork1", "dork2", "dork3"]


def test_parse_query_string_custom_separator():
    queries = parse_query_string("dork1|dork2|dork3", separator="|")
    assert queries == ["dork1", "dork2", "dork3"]


def test_parse_query_string_single_query():
    queries = parse_query_string("onlydork")
    assert queries == ["onlydork"]


def test_parse_query_string_empty():
    queries = parse_query_string("")
    assert queries == []


def test_parse_query_string_whitespace_trim():
    queries = parse_query_string("  dork1  ; dork2 ; dork3  ")
    assert queries == ["dork1", "dork2", "dork3"]


# ── run_batch (basic, without case modules) ────────────────────────────

@patch("core.batch_runner.search_dork")
def test_run_batch_success(mock_search):
    """run_batch should call search_dork for each query and collect results."""
    mock_search.side_effect = [
        [{"title": "Result 1", "href": "http://a.com"}],
        [{"title": "Result 2", "href": "http://b.com"}],
        [{"title": "Result 3", "href": "http://c.com"}],
    ]
    queries = ["q1", "q2", "q3"]
    results = run_batch(queries, max_results=5)
    assert len(results) == 3
    assert results["q1"][0]["title"] == "Result 1"
    assert results["q2"][0]["title"] == "Result 2"
    assert results["q3"][0]["title"] == "Result 3"
    assert mock_search.call_count == 3


@patch("core.batch_runner.search_dork")
def test_run_batch_with_failures(mock_search):
    """Queries that raise exceptions should be recorded as empty lists."""
    mock_search.side_effect = [
        [{"title": "OK", "href": "http://a.com"}],
        Exception("Search failed"),
        [{"title": "Also OK", "href": "http://b.com"}],
    ]
    queries = ["q1", "q2", "q3"]
    results = run_batch(queries)
    assert results["q1"] != []
    assert results["q2"] == []
    assert results["q3"] != []


@patch("core.batch_runner.search_dork")
def test_run_batch_empty_queries(mock_search):
    results = run_batch([])
    assert results == {}
    mock_search.assert_not_called()


# ── run_batch with case modules ────────────────────────────────────────

@patch("core.batch_runner.search_dork")
def test_run_batch_with_retry_handler(mock_search):
    """Retry handler should retry on transient errors."""
    mock_search.side_effect = [
        Exception("timeout"),  # transient → retry
        [{"title": "Success", "href": "http://a.com"}],
    ]
    retry_handler = RetryHandler(max_retries=2, base_delay=0.1)
    case_modules = {"retry_handler": retry_handler}
    results = run_batch(["q1"], case_modules=case_modules, max_results=5)
    assert len(results["q1"]) == 1
    assert results["q1"][0]["title"] == "Success"
    assert mock_search.call_count == 2


@patch("core.batch_runner.search_dork")
def test_run_batch_with_circuit_breaker(mock_search):
    """Circuit breaker should record failures and block after threshold.

    Sejak fix maintainer v1.4.0 kegagalan dicatat TEPAT SEKALI per query
    (setelah semua retry habis) — dulu tercatat hingga 3x per retry sehingga
    breaker terbuka prematur. Threshold=2 karena itu butuh 2 query gagal.
    """
    mock_search.side_effect = Exception("rate limit")
    circuit_breaker = CircuitBreaker(threshold=2, cooldown=120.0)
    fallback_manager = FallbackManager(
        backends=["duckduckgo", "startpage"],
        circuit_breaker=circuit_breaker,
    )
    retry_handler = RetryHandler(max_retries=2, base_delay=0.1)
    case_modules = {
        "circuit_breaker": circuit_breaker,
        "fallback_manager": fallback_manager,
        "retry_handler": retry_handler,
    }
    results = run_batch(["q1", "q2"], case_modules=case_modules, max_results=5, backend="duckduckgo")
    # Should return empty list (all retries exhausted)
    assert results["q1"] == []
    assert results["q2"] == []
    # Circuit breaker should be OPEN for duckduckgo (2 failed queries, recorded once each)
    assert circuit_breaker.status("duckduckgo") == "OPEN"


@patch("core.batch_runner.search_dork")
def test_run_batch_with_adaptive_delay(mock_search):
    """Adaptive delay should adjust delay based on response."""
    mock_search.return_value = [{"title": "OK", "href": "http://a.com"}]
    adaptive_delay = AdaptiveDelay(
        base_delay=0.1,
        max_delay=60.0,
        backoff_factor=2.0,
        recovery_factor=0.9,
        min_delay=0.01,  # lower than 0.1 * 0.9 = 0.09
    )
    case_modules = {"adaptive_delay": adaptive_delay}
    results = run_batch(["q1"], case_modules=case_modules, max_results=5)
    assert len(results["q1"]) == 1
    # Delay should have decreased after success
    assert adaptive_delay.get_delay("auto") < 0.1


@patch("core.batch_runner.search_dork")
def test_run_batch_with_concurrency(mock_search):
    """Batch runner should support parallel execution."""
    mock_search.return_value = [{"title": "Result", "href": "http://a.com"}]
    queries = ["q1", "q2", "q3", "q4"]
    results = run_batch(queries, concurrency=2, max_results=5)
    assert len(results) == 4
    assert mock_search.call_count == 4


# ── Dedup, cache, dan callback status (v1.3.9.6) ──────────────────────────

@patch("core.batch_runner.search_dork")
def test_run_batch_dedup_duplicate_queries(mock_search):
    """Query yang identik hanya dieksekusi sekali (hemat request/rate-limit)."""
    mock_search.return_value = [{"title": "x", "href": "http://a.com"}]
    results = run_batch(["q1", "q1", "q2", "q1"], max_results=5)
    assert mock_search.call_count == 2
    assert results == {"q1": mock_search.return_value, "q2": mock_search.return_value}


@patch("core.batch_runner.search_dork")
def test_run_batch_on_query_done_success_and_failure(mock_search):
    """on_query_done dipanggil sekali per query dengan flag success (untuk --resume)."""
    mock_search.side_effect = [
        [{"title": "x", "href": "http://a.com"}],
        Exception("fatal boom"),  # classify → FATAL, tanpa retry
    ]
    seen = {}
    results = run_batch(["ok", "fail"], on_query_done=lambda q, res, ok: seen.__setitem__(q, (len(res), ok)))
    assert seen["ok"] == (1, True)
    assert seen["fail"] == (0, False)
    assert results["fail"] == []


@patch("core.batch_runner.search_dork")
def test_run_batch_cache_hit_skips_search(mock_search, tmp_path):
    """Cache di mode batch: hasil sudah ada → search_dork tidak dipanggil."""
    cache = SearchCache(db_path=str(tmp_path / "c.db"))
    cache.set("cached_q", "auto", [{"title": "cached", "href": "http://c.com"}], {})
    mock_search.return_value = [{"title": "live", "href": "http://l.com"}]

    results = run_batch(["cached_q"], cache=cache, cache_params={}, max_results=5)
    mock_search.assert_not_called()
    assert results["cached_q"][0]["title"] == "cached"
    cache.close()


@patch("core.batch_runner.search_dork")
def test_run_batch_cache_miss_stores_result(mock_search, tmp_path):
    """Cache MISS → search dijalankan lalu hasil disimpan ke cache."""
    cache = SearchCache(db_path=str(tmp_path / "c.db"))
    mock_search.return_value = [{"title": "live", "href": "http://l.com"}]

    results = run_batch(["new_q"], cache=cache, cache_params={}, max_results=5)
    assert mock_search.call_count == 1
    assert cache.get("new_q", "auto", {}) is not None
    assert results["new_q"][0]["title"] == "live"
    cache.close()


@patch("core.batch_runner.search_dork")
def test_run_batch_cache_only_miss_returns_empty(mock_search, tmp_path):
    """--cache-only di batch: MISS → [] tanpa menyentuh jaringan."""
    cache = SearchCache(db_path=str(tmp_path / "c.db"))
    results = run_batch(["unknown_q"], cache=cache, cache_params={}, cache_only=True)
    mock_search.assert_not_called()
    assert results["unknown_q"] == []
    cache.close()


@patch("core.batch_runner.search_dork")
def test_run_batch_concurrent_with_cache(mock_search, tmp_path):
    """Cache thread-safe dipakai bersama oleh beberapa worker thread."""
    cache = SearchCache(db_path=str(tmp_path / "c.db"))
    mock_search.side_effect = lambda q, **kw: [{"title": q, "href": "http://a.com"}]

    queries = [f"q{i}" for i in range(8)]
    results = run_batch(queries, concurrency=4, cache=cache, cache_params={})
    assert len(results) == 8
    assert all(res for res in results.values())
    cache.close()
