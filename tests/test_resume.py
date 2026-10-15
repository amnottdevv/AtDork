"""
Integration tests untuk alur status SQLite & --resume (atdork.cli_mode).

Regresi v1.3.9.6: status query tidak pernah 'pending', query gagal tetap
ditandai 'completed', sehingga --resume selalu bilang "Tidak ada query yang
tertunda" — fitur resume tak pernah bisa bekerja.
"""

from unittest.mock import patch

import pytest

import atdork
from core.database import Database, STATUS_PENDING, STATUS_COMPLETED, STATUS_FAILED


def _good_result(href="https://example.com/login?user=1"):
    """Hasil yang lolos filter validasi (title≥5, desc≥10, url valid)."""
    return {
        "title": "Admin login page untuk portal contoh",
        "href": href,
        "body": "Halaman login admin dengan deskripsi yang cukup panjang.",
    }


def _statuses(db_path):
    with _open(db_path) as db:
        return {text: status for _, text, status in db.get_all_queries()}


class _open:
    def __init__(self, db_path):
        self.db = Database(str(db_path))

    def __enter__(self):
        return self.db

    def __exit__(self, *exc):
        self.db.close()
        return False


def _run(args_list, tmp_path, monkeypatch, search_mock):
    monkeypatch.chdir(tmp_path)
    args = atdork.build_parser().parse_args(args_list)
    with patch("core.batch_runner.search_dork", search_mock):
        atdork.cli_mode(args)


# ── Batch: sukses & gagal ditandai benar ──────────────────────────────────

def test_batch_marks_completed_and_failed(tmp_path, monkeypatch):
    db_path = tmp_path / "resume.db"
    calls = []

    def search(q, **kw):
        calls.append(q)
        if q == "query-gagal":
            raise Exception("fatal boom")
        return [_good_result("https://hasil.com/login?user=1")]

    _run(["-q", "query-sukses;query-gagal", "--db-path", str(db_path)],
         tmp_path, monkeypatch, search)

    assert sorted(calls) == ["query-gagal", "query-sukses"]
    assert _statuses(db_path) == {
        "query-sukses": STATUS_COMPLETED,
        "query-gagal": STATUS_FAILED,
    }

    # hasil query yang sukses benar-benar tersimpan
    with _open(db_path) as db:
        rows = db.get_all_queries()
        qid_sukses = [r[0] for r in rows if r[1] == "query-sukses"][0]
        assert db.get_results_by_query(qid_sukses)
        # query gagal tidak menyimpan hasil
        qid_gagal = [r[0] for r in rows if r[1] == "query-gagal"][0]
        assert db.get_results_by_query(qid_gagal) == []


def test_batch_query_is_pending_during_run(tmp_path, monkeypatch):
    """Saat eksekusi berjalan, query sudah berstatus 'pending' (kunci resume)."""
    db_path = tmp_path / "resume.db"
    seen_status = {}

    def search(q, **kw):
        # baca status langsung dari DB saat query masih dieksekusi
        with _open(db_path) as db:
            seen_status.update(
                {t: s for _, t, s in db.get_all_queries()}
            )
        return []

    _run(["-q", "q1;q2", "--db-path", str(db_path)],
         tmp_path, monkeypatch, search)

    assert seen_status == {"q1": STATUS_PENDING, "q2": STATUS_PENDING}


# ── --resume ──────────────────────────────────────────────────────────────

def test_resume_reruns_only_failed_queries(tmp_path, monkeypatch):
    db_path = tmp_path / "resume.db"

    def first_run(q, **kw):
        if q == "query-gagal":
            raise Exception("fatal boom")
        return [{"title": "OK", "href": "http://a.com", "body": "x" * 30}]

    _run(["-q", "query-sukses;query-gagal", "--db-path", str(db_path)],
         tmp_path, monkeypatch, first_run)

    # Run kedua dengan --resume: hanya query gagal yang dijalankan ulang.
    resumed_calls = []

    def second_run(q, **kw):
        resumed_calls.append(q)
        return [{"title": "OK", "href": "http://b.com", "body": "x" * 30}]

    _run(["--resume", "--db-path", str(db_path)],
         tmp_path, monkeypatch, second_run)

    assert resumed_calls == ["query-gagal"]
    assert _statuses(db_path) == {
        "query-sukses": STATUS_COMPLETED,
        "query-gagal": STATUS_COMPLETED,  # sekarang sukses → tidak diulang lagi
    }


def test_resume_with_nothing_pending_does_nothing(tmp_path, monkeypatch):
    db_path = tmp_path / "resume.db"

    def search(q, **kw):
        return [_good_result()]

    _run(["-q", "sudah-selesai", "--db-path", str(db_path)],
         tmp_path, monkeypatch, search)

    calls = []

    def should_not_be_called(q, **kw):  # pragma: no cover - sengaja dipantau
        calls.append(q)
        return []

    _run(["--resume", "--db-path", str(db_path)],
         tmp_path, monkeypatch, should_not_be_called)

    assert calls == []  # tidak ada yang tertunda → tidak ada request
    assert _statuses(db_path) == {"sudah-selesai": STATUS_COMPLETED}


def test_resume_picks_up_leftover_pending_queries(tmp_path, monkeypatch):
    """Query yang masih 'pending' (proses crash di tengah) ikut di-resume."""
    db_path = tmp_path / "resume.db"
    with _open(db_path) as db:
        db.add_query("tertinggal", STATUS_PENDING)

    calls = []

    def search(q, **kw):
        calls.append(q)
        return [{"title": "OK", "href": "http://a.com", "body": "x" * 30}]

    _run(["--resume", "--db-path", str(db_path)],
         tmp_path, monkeypatch, search)

    assert calls == ["tertinggal"]
    assert _statuses(db_path) == {"tertinggal": STATUS_COMPLETED}


# ── Mode single-query ─────────────────────────────────────────────────────

def test_single_query_failure_marks_failed_and_exits_1(tmp_path, monkeypatch):
    db_path = tmp_path / "resume.db"

    def search(q, **kw):
        raise Exception("fatal boom")

    monkeypatch.chdir(tmp_path)
    args = atdork.build_parser().parse_args(
        ["-q", "query-satu", "--db-path", str(db_path)]
    )
    with patch("core.batch_runner.search_dork", search):
        with pytest.raises(SystemExit) as exc:
            atdork.cli_mode(args)

    assert exc.value.code == 1
    assert _statuses(db_path) == {"query-satu": STATUS_FAILED}


def test_single_query_success_marks_completed(tmp_path, monkeypatch):
    db_path = tmp_path / "resume.db"

    def search(q, **kw):
        return [_good_result()]

    _run(["-q", "query-satu", "--db-path", str(db_path)],
         tmp_path, monkeypatch, search)

    assert _statuses(db_path) == {"query-satu": STATUS_COMPLETED}
    with _open(db_path) as db:
        rows = db.get_all_queries()
        assert db.get_results_by_query(rows[0][0])


def test_single_query_with_cache_does_not_hit_network(tmp_path, monkeypatch):
    """--cache pada mode single-query: hasil pertama disimpan, kedua dari cache."""
    db_path = tmp_path / "resume.db"
    cache_db = tmp_path / "cache.db"
    calls = []

    def search(q, **kw):
        calls.append(q)
        return [{"title": "OK", "href": "http://cache.com", "body": "x" * 30}]

    base = ["-q", "q-cache", "--db-path", str(db_path),
            "--cache", "--cache-db", str(cache_db)]
    _run(base, tmp_path, monkeypatch, search)
    assert calls == ["q-cache"]

    # run kedua (dedup global akan membuang hasilnya, tapi request tidak boleh
    # terjadi karena datang dari cache)
    _run(base, tmp_path, monkeypatch, search)
    assert calls == ["q-cache"]  # tidak bertambah → tidak ada request baru


def test_cache_only_miss_stays_pending_for_resume(tmp_path, monkeypatch):
    """--cache-only: HIT → completed; MISS → tetap 'pending' (belum diambil,
    bukan completed dan bukan failed) lalu diisi oleh --resume tanpa
    --cache-only."""
    db_path = tmp_path / "resume.db"
    cache_db = tmp_path / "cache.db"
    calls = []

    def search(q, **kw):
        calls.append(q)
        return [_good_result(f"https://{q}.com/login?user=1")]

    # 1. isi cache lewat pencarian sungguhan (single-query)
    _run(["-q", "q-cache", "--db-path", str(db_path),
          "--cache", "--cache-db", str(cache_db)],
         tmp_path, monkeypatch, search)
    assert calls == ["q-cache"]

    # 2. batch --cache-only: tidak boleh ada request jaringan sama sekali
    _run(["-q", "q-cache;q-baru", "--cache", "--cache-only",
          "--cache-db", str(cache_db), "--db-path", str(db_path)],
         tmp_path, monkeypatch, search)
    assert calls == ["q-cache"]                    # q-baru tidak bikin request
    statuses = _statuses(db_path)
    assert statuses["q-cache"] == STATUS_COMPLETED  # dari cache
    assert statuses["q-baru"] == STATUS_PENDING     # MISS → belum diambil

    # 3. --resume tanpa --cache-only → hanya q-baru yang dicari beneran
    _run(["--resume", "--db-path", str(db_path),
          "--cache", "--cache-db", str(cache_db)],
         tmp_path, monkeypatch, search)
    assert calls == ["q-cache", "q-baru"]
    assert _statuses(db_path)["q-baru"] == STATUS_COMPLETED
