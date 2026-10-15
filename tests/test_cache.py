"""
Unit tests untuk core.manage_cache (SearchCache).

Mencakup regresi bug v1.3.9.6: get_or_set() melempar
`TypeError: got multiple values for argument 'query'` karena argumen fetch
diserahkan lewat **kwargs yang bentrok dengan parameter `query`.
"""

import threading

import pytest

from core.manage_cache import SearchCache


@pytest.fixture
def cache(tmp_path):
    c = SearchCache(db_path=str(tmp_path / "cache.db"), default_ttl_hours=24)
    yield c
    c.close()


# ── set / get dasar ───────────────────────────────────────────────────────

def test_set_get_roundtrip(cache):
    results = [{"title": "A", "href": "http://a.com", "body": "b"}]
    assert cache.set("q1", "bing", results, {"region": "us-en"}) is True
    got = cache.get("q1", "bing", {"region": "us-en"})
    assert got == results


def test_get_miss_returns_none(cache):
    assert cache.get("tidak-ada", "bing", {}) is None


def test_cache_key_dipisah_per_engine_dan_params(cache):
    results = [{"title": "A", "href": "http://a.com", "body": "b"}]
    cache.set("q1", "bing", results, {"region": "us-en"})
    assert cache.get("q1", "google", {"region": "us-en"}) is None
    assert cache.get("q1", "bing", {"region": "uk-en"}) is None


def test_ttl_expired(cache):
    results = [{"title": "A", "href": "http://a.com", "body": "b"}]
    cache.set("q-exp", "bing", results, {}, ttl_hours=-1)
    assert cache.get("q-exp", "bing", {}) is None


def test_set_rejects_empty_results(cache):
    """Hasil kosong tidak disimpan — inilah alasan --cache-only + MISS = []."""
    assert cache.set("q-empty", "bing", [], {}) is False
    assert cache.get("q-empty", "bing", {}) is None


# ── get_or_set (regresi crash --cache) ────────────────────────────────────

def test_get_or_set_does_not_crash_on_query_kwarg(cache):
    """Regresi: call-site lama mengirim query=q → TypeError ganda."""
    calls = []

    def fetch(query=None, **kw):
        calls.append(query)
        return [{"title": query, "href": "http://a.com", "body": ""}]

    out = cache.get_or_set(
        "q1", "bing", fetch, params={}, ttl_hours=24,
        fetch_kwargs={"query": "q1", "max_results": 5},
    )
    assert calls == ["q1"]
    assert out[0]["title"] == "q1"


def test_get_or_set_fetch_dipanggil_satu_kali(cache):
    calls = {"n": 0}

    def fetch(**kw):
        calls["n"] += 1
        return [{"title": "x", "href": "http://a.com", "body": ""}]

    first = cache.get_or_set("q", "bing", fetch, params={})
    second = cache.get_or_set("q", "bing", fetch, params={})
    assert calls["n"] == 1  # kedua kalinya dari cache
    assert first == second


def test_get_or_set_fetch_error_propagates(cache):
    def fetch(**kw):
        raise RuntimeError("jaringan meledak")

    with pytest.raises(RuntimeError):
        cache.get_or_set("q-err", "bing", fetch, params={})
    # tidak ada entri tersimpan saat fetch gagal
    assert cache.get("q-err", "bing", {}) is None


def test_get_or_set_rejects_non_callable(cache):
    with pytest.raises(TypeError):
        cache.get_or_set("q", "bing", "bukan-fungsi")


# ── stats & cleanup ───────────────────────────────────────────────────────

def test_get_stats_and_cleanup(cache):
    cache.set("q1", "bing", [{"title": "a", "href": "http://a", "body": ""}], {})
    cache.set("q1", "google", [{"title": "a", "href": "http://a", "body": ""}], {})
    stats = cache.get_stats()
    assert stats["total_entries"] == 2
    assert set(stats["engines"]) == {"bing", "google"}

    cache.set("q-expired", "bing", [{"title": "a", "href": "http://a", "body": ""}],
              {}, ttl_hours=-1)
    assert cache.cleanup_expired() >= 1

    assert cache.clear_by_engine("bing") >= 1
    assert cache.get("q1", "google", {}) is not None
    assert cache.clear_all() >= 1
    assert cache.get_stats()["total_entries"] == 0


# ── thread safety (dipakai mode batch --concurrency > 1) ──────────────────

def test_get_or_set_thread_safe(tmp_path):
    db = str(tmp_path / "thread-cache.db")
    errors = []
    barrier = threading.Barrier(8)

    def worker(i):
        c = SearchCache(db_path=db, auto_cleanup=False)
        try:
            barrier.wait(timeout=10)

            def fetch(**kw):
                return [{"title": f"r{i}", "href": f"http://r{i}.com", "body": ""}]

            for _ in range(5):
                out = c.get_or_set("shared-q", "bing", fetch, params={})
                assert out and out[0]["href"].startswith("http://r")
            c.close()
        except Exception as e:  # pragma: no cover - hanya untuk debug test
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert errors == [], f"Thread gagal: {errors}"
