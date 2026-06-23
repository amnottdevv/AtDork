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
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from pathlib import Path

logger = logging.getLogger(__name__)

# Default cache expiration (24 jam)
DEFAULT_TTL_HOURS = 24

# Cache database schema
SQL_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS api_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query TEXT NOT NULL,
    engine TEXT NOT NULL,
    params TEXT NOT NULL,  -- JSON string dari parameter (region, safesearch, dll.)
    results TEXT NOT NULL, -- JSON string dari hasil pencarian
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP,
    hit_count INTEGER DEFAULT 1,
    last_accessed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_cache_lookup ON api_cache(query, engine, params);
CREATE INDEX IF NOT EXISTS idx_cache_expires ON api_cache(expires_at);
"""


class SearchCache:
    """
    Manajer cache untuk hasil pencarian API.

    Args:
        db_path: Path ke file database SQLite (default: atdork_cache.db)
        default_ttl_hours: Default TTL dalam jam (default: 24)
        auto_cleanup: Hapus cache expired saat inisialisasi (default: True)
    """

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
        """Buka koneksi database."""
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def close(self):
        """Tutup koneksi database."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def _init_db(self):
        """Buat tabel cache jika belum ada."""
        conn = self._connect()
        conn.executescript(SQL_CREATE_TABLE)
        conn.commit()
        logger.debug("Cache database siap di %s", self.db_path)

    def _normalize_params(self, params: Dict[str, Any]) -> str:
        """
        Normalisasi parameter untuk digunakan sebagai key cache.
        Mengabaikan parameter yang None atau kosong.
        """
        if not params:
            return "{}"

        # Filter parameter yang None atau kosong
        filtered = {
            k: v for k, v in params.items()
            if v is not None and v != "" and v != {}
        }

        # Sort untuk konsistensi
        return json.dumps(filtered, sort_keys=True, ensure_ascii=False)

    def _params_to_dict(self, params_json: str) -> Dict[str, Any]:
        """Parse parameter dari JSON string."""
        try:
            return json.loads(params_json) if params_json else {}
        except json.JSONDecodeError:
            return {}

    def get(
        self,
        query: str,
        engine: str,
        params: Optional[Dict[str, Any]] = None,
        max_age_hours: Optional[int] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Ambil hasil dari cache.

        Args:
            query: Query pencarian.
            engine: Nama engine (serpapi, serper, brave, dll.).
            params: Parameter tambahan (region, safesearch, dll.).
            max_age_hours: TTL kustom (override default).

        Returns:
            List hasil jika ditemukan dan masih valid, None jika tidak ada.
        """
        if not query or not engine:
            return None

        params_json = self._normalize_params(params or {})
        ttl_hours = max_age_hours or self.default_ttl_hours

        conn = self._connect()
        try:
            cursor = conn.execute(
                """
                SELECT results, created_at, hit_count
                FROM api_cache
                WHERE query = ? AND engine = ? AND params = ?
                  AND expires_at > datetime('now')
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (query, engine, params_json)
            )

            row = cursor.fetchone()
            if not row:
                return None

            # Update hit_count dan last_accessed
            try:
                conn.execute(
                    """
                    UPDATE api_cache
                    SET hit_count = hit_count + 1,
                        last_accessed = datetime('now')
                    WHERE query = ? AND engine = ? AND params = ?
                    """,
                    (query, engine, params_json)
                )
                conn.commit()
            except Exception as e:
                logger.warning("Gagal update hit_count: %s", e)

            try:
                results = json.loads(row["results"])
                logger.debug(
                    "Cache HIT: %s (%s) - hit #%d",
                    query[:50], engine, row["hit_count"]
                )
                return results
            except json.JSONDecodeError:
                logger.warning("Cache corrupt untuk %s (%s)", query[:50], engine)
                return None
        except Exception as e:
            logger.error("Gagal mengambil cache: %s", e)
            return None

    def set(
        self,
        query: str,
        engine: str,
        results: List[Dict[str, Any]],
        params: Optional[Dict[str, Any]] = None,
        ttl_hours: Optional[int] = None,
    ) -> bool:
        """
        Simpan hasil ke cache.

        Args:
            query: Query pencarian.
            engine: Nama engine.
            results: List hasil pencarian.
            params: Parameter tambahan.
            ttl_hours: TTL kustom (override default).

        Returns:
            True jika berhasil disimpan, False jika gagal.
        """
        if not query or not engine or not results:
            return False

        params_json = self._normalize_params(params or {})
        ttl = ttl_hours or self.default_ttl_hours
        results_json = json.dumps(results, ensure_ascii=False)

        conn = self._connect()
        try:
            # Upsert: update jika sudah ada, insert jika belum
            # Gunakan INSERT OR REPLACE untuk simplicity
            conn.execute(
                """
                INSERT OR REPLACE INTO api_cache
                (query, engine, params, results, created_at, expires_at, hit_count, last_accessed)
                VALUES (
                    ?, ?, ?, ?,
                    datetime('now'),
                    datetime('now', '+' || ? || ' hours'),
                    1,
                    datetime('now')
                )
                """,
                (query, engine, params_json, results_json, ttl)
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
        """
        Get dari cache, jika tidak ada jalankan fetch_func dan simpan hasilnya.

        Args:
            query: Query pencarian.
            engine: Nama engine.
            fetch_func: Fungsi yang dipanggil jika cache miss.
            params: Parameter tambahan.
            ttl_hours: TTL kustom.
            *args, **kwargs: Diteruskan ke fetch_func.

        Returns:
            List hasil (dari cache atau fetch_func).
        """
        # Coba ambil dari cache
        cached = self.get(query, engine, params, ttl_hours)
        if cached is not None:
            return cached

        # Cache miss → jalankan fetch_func
        logger.debug("Cache MISS: %s (%s), calling fetch_func", query[:50], engine)
        try:
            results = fetch_func(*args, **kwargs)
            if results:
                self.set(query, engine, results, params, ttl_hours)
            return results if results else []
        except Exception as e:
            logger.error("fetch_func gagal untuk %s: %s", query[:50], e)
            raise

    def cleanup_expired(self) -> int:
        """
        Hapus semua cache yang sudah expired.
        Returns: Jumlah baris yang dihapus.
        """
        conn = self._connect()
        try:
            cursor = conn.execute(
                "DELETE FROM api_cache WHERE expires_at < datetime('now')"
            )
            deleted = cursor.rowcount
            conn.commit()

            if deleted > 0:
                logger.info("Cache cleanup: %d expired entries removed", deleted)

            return deleted
        except Exception as e:
            logger.error("Gagal cleanup cache: %s", e)
            return 0

    def clear_all(self) -> int:
        """Hapus semua cache."""
        conn = self._connect()
        try:
            cursor = conn.execute("DELETE FROM api_cache")
            deleted = cursor.rowcount
            conn.commit()
            logger.info("Cache cleared: %d entries removed", deleted)
            return deleted
        except Exception as e:
            logger.error("Gagal clear cache: %s", e)
            return 0

    def clear_by_engine(self, engine: str) -> int:
        """Hapus cache untuk engine tertentu."""
        conn = self._connect()
        try:
            cursor = conn.execute("DELETE FROM api_cache WHERE engine = ?", (engine,))
            deleted = cursor.rowcount
            conn.commit()
            logger.info("Cache cleared for engine '%s': %d entries removed", engine, deleted)
            return deleted
        except Exception as e:
            logger.error("Gagal clear cache by engine: %s", e)
            return 0

    def get_stats(self) -> Dict[str, Any]:
        """Dapatkan statistik cache."""
        conn = self._connect()
        try:
            total = conn.execute("SELECT COUNT(*) FROM api_cache").fetchone()[0]
            expired = conn.execute(
                "SELECT COUNT(*) FROM api_cache WHERE expires_at < datetime('now')"
            ).fetchone()[0]
            total_hits = conn.execute(
                "SELECT COALESCE(SUM(hit_count), 0) FROM api_cache"
            ).fetchone()[0]

            return {
                "total_entries": total,
                "expired_entries": expired,
                "total_hits": total_hits,
                "engines": [
                    row["engine"]
                    for row in conn.execute(
                        "SELECT DISTINCT engine FROM api_cache"
                    ).fetchall()
                ],
            }
        except Exception as e:
            logger.error("Gagal mengambil statistik cache: %s", e)
            return {
                "total_entries": 0,
                "expired_entries": 0,
                "total_hits": 0,
                "engines": [],
            }

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# ── Convenience Functions ──────────────────────────────────────────────

def create_cache_key(
    query: str,
    engine: str,
    params: Optional[Dict[str, Any]] = None,
) -> str:
    """Buat key cache untuk debugging."""
    params_json = json.dumps(params or {}, sort_keys=True, ensure_ascii=False)
    return f"{engine}:{query[:50]}:{params_json[:50]}"


# ── Example Usage ──────────────────────────────────────────────────────

if __name__ == "__main__":
    # Contoh penggunaan
    with SearchCache("test_cache.db", default_ttl_hours=1) as cache:
        # Simpan cache
        cache.set(
            query="site:example.com",
            engine="serpapi",
            results=[{"title": "Test", "href": "https://example.com"}],
            params={"region": "us-en", "safesearch": "moderate"},
            ttl_hours=2,
        )

        # Ambil dari cache
        results = cache.get(
            query="site:example.com",
            engine="serpapi",
            params={"region": "us-en", "safesearch": "moderate"},
        )
        print(f"Cache results: {results}")

        # Statistik
        stats = cache.get_stats()
        print(f"Stats: {stats}")

        # Hapus cache expired
        cache.cleanup_expired()

        # Hapus semua cache
        # cache.clear_all()
