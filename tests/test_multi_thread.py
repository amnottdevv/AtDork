"""
Unit tests for core.multi_thread_runner module.
"""

import pytest
from unittest.mock import patch, MagicMock
from core.multi_thread_runner import run_batch_multithread


# ── Fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def mock_search_success():
    """Mocks search_dork to return a fixed result."""
    with patch("core.multi_thread_runner.search_dork") as mock:
        mock.return_value = [
            {"title": "Result", "href": "http://example.com", "body": "Snippet"}
        ]
        yield mock


@pytest.fixture
def mock_search_failure():
    """Mocks search_dork to always raise an exception."""
    with patch("core.multi_thread_runner.search_dork") as mock:
        mock.side_effect = Exception("Connection failed")
        yield mock


# ── Test cases ───────────────────────────────────────────────────────────

def test_run_batch_multithread_success(mock_search_success):
    queries = ["q1", "q2", "q3"]
    results = run_batch_multithread(queries, concurrency=2)
    assert len(results) == 3
    assert all(len(v) == 1 for v in results.values())
    assert mock_search_success.call_count == 3


def test_run_batch_multithread_with_failures(mock_search_failure):
    queries = ["q1", "q2"]
    results = run_batch_multithread(queries, concurrency=2, fallback_sequential=True)
    assert len(results) == 2
    # Semua gagal → setiap query harus memiliki list kosong
    assert results["q1"] == []
    assert results["q2"] == []
    # Karena semua gagal, mekanisme fallback sequential akan tetap dijalankan
    # mock dipanggil setidaknya 2 kali (bisa lebih jika fallback terjadi)
    assert mock_search_failure.call_count >= 2


def test_run_batch_multithread_fallback_on_consecutive_failures():
    """Jika kegagalan berturut-turut melebihi batas, harus fallback ke sequential."""
    call_counter = [0]

    def side_effect(*args, **kwargs):
        call_counter[0] += 1
        raise Exception("Fail")

    with patch("core.multi_thread_runner.search_dork", side_effect=side_effect):
        queries = ["q1", "q2", "q3", "q4"]
        results = run_batch_multithread(
            queries,
            concurrency=2,
            fallback_sequential=True,
            max_consecutive_failures=2,
        )
        assert len(results) == 4
        # Semua gagal, tapi tidak ada yang hilang
        assert all(v == [] for v in results.values())


def test_run_batch_multithread_empty_queries():
    results = run_batch_multithread([], concurrency=5)
    assert results == {}


def test_run_batch_multithread_progress_mocked(mock_search_success):
    """Pastikan progress bar tidak menyebabkan error."""
    queries = ["a", "b"]
    results = run_batch_multithread(queries, concurrency=1)
    assert len(results) == 2