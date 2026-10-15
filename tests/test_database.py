"""
Unit tests for core.database module (real module — bukan salinan kode).

Catatan: file ini dahulu berisi SALINAN lengkap kelas Database yang tidak
di-import dari core.database sama sekali (0 test, kode produksi tak teruji).
Sekarang diuji modul aslinya, termasuk regresi deteksi duplikat add_result().
"""

import json
import os

import pytest
import sqlite3

from core.database import (
    Database,
    STATUS_PENDING,
    STATUS_RUNNING,
    STATUS_COMPLETED,
    STATUS_FAILED,
)


@pytest.fixture
def db(tmp_path):
    d = Database(db_path=str(tmp_path / "test.db"))
    yield d
    d.close()


# ── Query management ──────────────────────────────────────────────────────

def test_add_query_returns_id_and_defaults_pending(db):
    qid = db.add_query("site:example.com")
    assert isinstance(qid, int) and qid > 0
    assert db.get_all_queries() == [(qid, "site:example.com", STATUS_PENDING)]
    # pending harus terbaca oleh --resume
    assert db.get_pending_queries() == [(qid, "site:example.com")]


def test_add_query_upsert_keeps_id_updates_status(db):
    qid = db.add_query("dork-a", STATUS_COMPLETED)
    qid2 = db.add_query("dork-a", STATUS_PENDING)
    assert qid2 == qid  # id tidak berubah
    assert db.get_all_queries() == [(qid, "dork-a", STATUS_PENDING)]


def test_update_query_status(db):
    qid = db.add_query("dork-b")
    db.update_query_status(qid, STATUS_FAILED)
    assert db.get_all_queries() == [(qid, "dork-b", STATUS_FAILED)]
    assert db.get_pending_queries() == [(qid, "dork-b")]


def test_get_pending_queries_excludes_completed(db):
    db.add_query("done-query", STATUS_COMPLETED)
    assert db.get_pending_queries() == []


# ── Result management ─────────────────────────────────────────────────────

def test_add_result_returns_true_for_new_false_for_duplicate(db):
    """Regresi: add_result() dahulu SELALU return True (INSERT OR IGNORE tidak
    pernah melempar IntegrityError) sehingga duplikat tak pernah terdeteksi."""
    qid = db.add_query("q", STATUS_COMPLETED)
    assert db.add_result(qid, {"title": "A", "href": "http://a.com", "body": "x"}) is True
    assert db.add_result(qid, {"title": "A", "href": "http://a.com", "body": "x"}) is False


def test_add_result_same_href_different_query_ok(db):
    q1 = db.add_query("q1", STATUS_COMPLETED)
    q2 = db.add_query("q2", STATUS_COMPLETED)
    assert db.add_result(q1, {"title": "A", "href": "http://a.com", "body": "x"}) is True
    assert db.add_result(q2, {"title": "A", "href": "http://a.com", "body": "x"}) is True


def test_add_results_batch_counts_only_new(db):
    qid = db.add_query("q", STATUS_COMPLETED)
    results = [
        {"title": "1", "href": "http://1.com", "body": ""},
        {"title": "2", "href": "http://2.com", "body": ""},
    ]
    assert db.add_results_batch(qid, results) == 2
    # insert ulang → tidak ada yang baru
    assert db.add_results_batch(qid, results) == 0
    assert len(db.get_results_by_query(qid)) == 2


def test_is_duplicate_global(db):
    qid = db.add_query("q", STATUS_COMPLETED)
    db.add_result(qid, {"title": "A", "href": "http://dup.com", "body": ""})
    assert db.is_duplicate("http://dup.com") is True
    assert db.is_duplicate("http://unique.com") is False


def test_get_results_by_query_roundtrip_raw_json(db):
    qid = db.add_query("q", STATUS_COMPLETED)
    db.add_result(qid, {"title": "Judul", "href": "http://x.com", "body": "snippet", "backend": "bing"})
    rows = db.get_results_by_query(qid)
    assert rows[0]["href"] == "http://x.com"
    assert rows[0]["title"] == "Judul"


# ── Export ────────────────────────────────────────────────────────────────

def test_export_to_json(db, tmp_path):
    qid = db.add_query("q", STATUS_COMPLETED)
    db.add_result(qid, {"title": "A", "href": "http://a.com", "body": "b"})
    out = str(tmp_path / "out.json")
    db.export_to_json(out)
    with open(out, encoding="utf-8") as f:
        data = json.load(f)
    assert data  # ada isi


def test_export_to_csv(db, tmp_path):
    qid = db.add_query("q", STATUS_COMPLETED)
    db.add_result(qid, {"title": "A", "href": "http://a.com", "body": "b"})
    out = str(tmp_path / "out.csv")
    db.export_to_csv(out)
    content = open(out, encoding="utf-8").read()
    assert "http://a.com" in content
