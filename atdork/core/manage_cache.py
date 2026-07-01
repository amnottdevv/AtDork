"""
Atdork – Cache Manager for API Results (core/manage_cache.py)
Menyimpan dan mengambil hasil pencarian dari API ke SQLite cache.

Fitur:
- Cache berdasarkan query + engine + parameter (region, safesearch, dll.)
- TTL (Time-To-Live) untuk cache expired
- Auto-cleanup cache lama
- Thread-safe
"""

import sqlite3
import json
import logging
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# Default cache expiration (24 jam)
DEFAULT_TTL_HOURS = 24

# Cache database schema
SQL_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS api_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query TEXT NOT NULL,
    engine TEXT NOT NULL,
    params TEXT NOT NULL,
    results TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    hit_count INTEGER DEFAULT 1,
    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cache_lookup ON api_cache(query, engine, params);
CREATE INDEX IF NOT EXISTS idx_cache_expires ON api_cache(expires_at);
"""


class SearchCache:
    """Manajer cache untuk hasil pencarian API."""

    def __init__(
        self,
        db_path: str = "atdork_cache.db",
        default_ttl_hours: int = DEFAULT_TTL_HOURS,
        auto_cleanup: bool = True,
    ):
        self.db_path = db_path
        self.default_ttl_hours = default_ttl_hours
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()
        if auto_cleanup:
            self.cleanup_expired()

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def _init_db(self):
        conn = self._connect()
        conn.executescript(SQL_CREATE_TABLE)
        conn.commit()
        logger.debug("Cache database siap di %s", self.db_path)

    def _normalize_params(self, params: Dict[str, Any]) -> str:
        if not params:
            return "{}"
        filtered = {k: v for k, v in params.items() if v is not None and v != "" and v != {}}
        return json.dumps(filtered, sort_keys=True, ensure_ascii=False)

    def get(
        self,
        query: str,
        engine: str,
        params: Optional[Dict[str, Any]] = None,
        max_age_hours: Optional[int] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        if not query or not engine:
            return None

        params_json = self._normalize_params(params or {})
        conn = self._connect()
        cursor = conn.execute(
            """SELECT results, created_at, hit_count FROM api_cache
               WHERE query = ? AND engine = ? AND params = ?
                 AND expires_at > datetime('now')
               ORDER BY created_at DESC LIMIT 1""",
            (query, engine, params_json),
        )
        row = cursor.fetchone()
        if not row:
            return None

        try:
            conn.execute(
                "UPDATE api_cache SET hit_count = hit_count + 1, last_accessed = datetime('now') "
                "WHERE query = ? AND engine = ? AND params = ?",
                (query, engine, params_json),
            )
            conn.commit()
        except Exception as e:
            logger.warning("Gagal update hit_count: %s", e)

        try:
            results = json.loads(row["results"])
            logger.debug("Cache HIT: %s (%s) - hit #%d", query[:50], engine, row["hit_count"])
            return results
        except json.JSONDecodeError:
            logger.warning("Cache corrupt untuk %s (%s)", query[:50], engine)
            return None

    def set(
        self,
        query: str,
        engine: str,
        results: List[Dict[str, Any]],
        params: Optional[Dict[str, Any]] = None,
        ttl_hours: Optional[int] = None,
    ) -> bool:
        if not query or not engine or not results:
            return False

        params_json = self._normalize_params(params or {})
        ttl = ttl_hours or self.default_ttl_hours
        results_json = json.dumps(results, ensure_ascii=False)
        conn = self._connect()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO api_cache
                   (query, engine, params, results, created_at, expires_at, hit_count, last_accessed)
                   VALUES (?, ?, ?, ?, datetime('now'), datetime('now', '+' || ? || ' hours'), 1, datetime('now'))""",
                (query, engine, params_json, results_json, ttl),
            )
            conn.commit()
            logger.debug("Cache SET: %s (%s) - %d results", query[:50], engine, len(results))
            return True
        except Exception as e:
            logger.error("Gagal menyimpan cache: %s", e)
            return False

    def get_or_set(
        self,
        query: str,
        engine: str,
        fetch_func,
        params: Optional[Dict[str, Any]] = None,
        ttl_hours: Optional[int] = None,
        *args,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        cached = self.get(query, engine, params, ttl_hours)
        if cached is not None:
            return cached
        logger.debug("Cache MISS: %s (%s), calling fetch_func", query[:50], engine)
        results = fetch_func(*args, **kwargs)
        if results:
            self.set(query, engine, results, params, ttl_hours)
        return results if results else []

    def cleanup_expired(self) -> int:
        conn = self._connect()
        cursor = conn.execute("DELETE FROM api_cache WHERE expires_at < datetime('now')")
        deleted = cursor.rowcount
        conn.commit()
        if deleted:
            logger.info("Cache cleanup: %d expired entries removed", deleted)
        return deleted

    def clear_all(self) -> int:
        conn = self._connect()
        cursor = conn.execute("DELETE FROM api_cache")
        deleted = cursor.rowcount
        conn.commit()
        logger.info("Cache cleared: %d entries removed", deleted)
        return deleted

    def clear_by_engine(self, engine: str) -> int:
        conn = self._connect()
        cursor = conn.execute("DELETE FROM api_cache WHERE engine = ?", (engine,))
        deleted = cursor.rowcount
        conn.commit()
        logger.info("Cache cleared for engine '%s': %d entries removed", engine, deleted)
        return deleted

    def get_stats(self) -> Dict[str, Any]:
        conn = self._connect()
        total = conn.execute("SELECT COUNT(*) FROM api_cache").fetchone()[0]
        expired = conn.execute(
            "SELECT COUNT(*) FROM api_cache WHERE expires_at < datetime('now')"
        ).fetchone()[0]
        total_hits = conn.execute("SELECT COALESCE(SUM(hit_count), 0) FROM api_cache").fetchone()[0]
        return {
            "total_entries": total,
            "expired_entries": expired,
            "total_hits": total_hits,
            "engines": [row["engine"] for row in conn.execute("SELECT DISTINCT engine FROM api_cache").fetchall()],
        }

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def create_cache_key(query: str, engine: str, params: Optional[Dict[str, Any]] = None) -> str:
    params_json = json.dumps(params or {}, sort_keys=True, ensure_ascii=False)
    return f"{engine}:{query[:50]}:{params_json[:50]}"


if __name__ == "__main__":
    with SearchCache("test_cache.db", default_ttl_hours=1) as cache:
        cache.set(
            query="site:example.com",
            engine="serpapi",
            results=[{"title": "Test", "href": "https://example.com"}],
            params={"region": "us-en", "safesearch": "moderate"},
            ttl_hours=2,
        )
        results = cache.get(query="site:example.com", engine="serpapi", params={"region": "us-en", "safesearch": "moderate"})
        print(f"Cache results: {results}")
        stats = cache.get_stats()
        print(f"Stats: {stats}")
        cache.cleanup_expired()
