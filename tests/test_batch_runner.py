"""
Unit tests for core.batch_runner module.
"""

import pytest
from unittest.mock import patch, MagicMock
from core.batch_runner import (
    load_queries_from_file,
    parse_query_string,
    run_batch,
)


# ── load_queries_from_file ────────────────────────────────────────────────

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


# ── parse_query_string ────────────────────────────────────────────────────

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


# ── run_batch ────────────────────────────────────────────────────────────

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