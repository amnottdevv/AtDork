"""
Unit tests for core.database module.
Uses a temporary SQLite database file.
"""

import json
import sqlite3
import pytest
from core.database import Database

@pytest.fixture
def db(tmp_path):
    """Create a Database instance backed by a temporary file."""
    db_path = tmp_path / "test.db"
    db = Database(str(db_path))
    yield db
    db.close()


def test_add_query(db):
    qid = db.add_query("test query")
    assert qid > 0
    # Adding again should return the same ID
    qid2 = db.add_query("test query")
    assert qid == qid2


def test_update_query_status(db):
    qid = db.add_query("query")
    db.update_query_status(qid, "completed")
    # Check status via get_all_queries
    all_queries = db.get_all_queries()
    status = [s for (i, t, s) in all_queries if i == qid][0]
    assert status == "completed"


def test_get_pending_queries(db):
    db.add_query("pending1")
    db.add_query("pending2")
    # both default to 'pending'
    pending = db.get_pending_queries()
    assert len(pending) == 2
    # Update one to completed
    qid = db.add_query("pending2")
    db.update_query_status(qid, "completed")
    pending = db.get_pending_queries()
    assert len(pending) == 1
    assert pending[0][1] == "pending1"


def test_add_result(db):
    qid = db.add_query("q")
    result = {"title": "Test", "href": "http://example.com", "body": "Snippet"}
    inserted = db.add_result(qid, result)
    assert inserted is True
    # Duplicate href for same query should be ignored
    inserted2 = db.add_result(qid, result)
    assert inserted2 is False
    # Retrieve
    results = db.get_results_by_query(qid)
    assert len(results) == 1
    assert results[0]["title"] == "Test"


def test_add_results_batch(db):
    qid = db.add_query("q")
    results = [
        {"title": "One", "href": "http://a.com"},
        {"title": "Two", "href": "http://b.com"},
        {"title": "One Dupe", "href": "http://a.com"},  # duplicate href
    ]
    new_count = db.add_results_batch(qid, results)
    assert new_count == 2


def test_deduplication(db):
    qid1 = db.add_query("q1")
    db.add_result(qid1, {"title": "A", "href": "http://dup.com"})
    qid2 = db.add_query("q2")
    db.add_result(qid2, {"title": "B", "href": "http://unique.com"})
    assert db.is_duplicate("http://dup.com") is True
    assert db.is_duplicate("http://unique.com") is True  # across all queries
    assert db.is_duplicate("http://new.com") is False


def test_export_json(db, tmp_path):
    qid = db.add_query("q")
    db.add_result(qid, {"title": "T", "href": "http://e.com"})
    out = tmp_path / "export.json"
    db.export_to_json(str(out))
    with open(out) as f:
        data = json.load(f)
    assert str(qid) in data
    assert len(data[str(qid)]) == 1


def test_export_csv(db, tmp_path):
    qid = db.add_query("q")
    db.add_result(qid, {"title": "T", "href": "http://e.com"})
    out = tmp_path / "export.csv"
    db.export_to_csv(str(out))
    with open(out) as f:
        lines = f.readlines()
    assert len(lines) == 2  # header + 1 row
    assert "T" in lines[1]
