"""
Atdork – SQLite Database Layer
Menyimpan hasil pencarian ke database SQLite lokal untuk resume, history, dan deduplikasi.
"""

import sqlite3
import json
import csv
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

logger = logging.getLogger(__name__)

# Status untuk tabel queries
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

# Skema database
SQL_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS queries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_text TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_id INTEGER NOT NULL,
    title TEXT,
    href TEXT,
    body TEXT,
    raw_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (query_id) REFERENCES queries(id),
    UNIQUE(query_id, href)
);
"""


class Database:
    """Manajer penyimpanan SQLite untuk AtDork."""

    def __init__(self, db_path: str = "atdork.db"):
        self.db_path = db_path
        self._conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        """Buka koneksi (otomatis buat file jika belum ada).
        
        Raises:
            sqlite3.DatabaseError: Jika database corrupt atau tidak bisa diakses
            OSError: Jika permission denied atau disk penuh
        """
        if self._conn is None:
            try:
                self._conn = sqlite3.connect(self.db_path, timeout=10.0)
                self._conn.execute("PRAGMA journal_mode=WAL")   # performa & concurrent
                self._conn.execute("PRAGMA foreign_keys = ON")
            except sqlite3.DatabaseError as e:
                logger.error(f"Database error saat membuka {self.db_path}: {e}")
                raise
            except OSError as e:
                logger.error(f"OS error saat mengakses database {self.db_path}: {e}")
                raise
        return self._conn

    def close(self):
        """Tutup koneksi database dengan error handling."""
        if self._conn:
            try:
                self._conn.close()
            except Exception as e:
                logger.warning(f"Error saat menutup database connection: {e}")
            finally:
                self._conn = None

    def _init_db(self):
        """Buat tabel jika belum ada."""
        try:
            conn = self._connect()
            conn.executescript(SQL_CREATE_TABLES)
            conn.commit()
            logger.debug("Database siap di %s", self.db_path)
        except Exception as e:
            logger.error(f"Gagal menginisialisasi database: {e}")
            raise

    # ── Query Management ──────────────────────────────────────────────

    def add_query(self, query_text: str, status: str = STATUS_PENDING) -> int:
        """
        Tambahkan query baru. Mengembalikan ID query.
        Jika query sudah ada, update statusnya.
        
        Raises:
            sqlite3.Error: Jika ada error database
        """
        now = datetime.utcnow().isoformat()
        conn = self._connect()
        try:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO queries (query_text, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?)",
                (query_text, status, now, now)
            )
            if cursor.rowcount == 0:
                # Sudah ada, update status & timestamp
                cursor = conn.execute(
                    "UPDATE queries SET status = ?, updated_at = ? WHERE query_text = ?",
                    (status, now, query_text)
                )
                # Ambil ID
                row = conn.execute(
                    "SELECT id FROM queries WHERE query_text = ?", (query_text,)
                ).fetchone()
                query_id = row[0]
            else:
                query_id = cursor.lastrowid
            conn.commit()
            return query_id
        except sqlite3.DatabaseError as e:
            conn.rollback()
            logger.error(f"Database error saat add_query: {e}")
            raise
        except Exception as e:
            conn.rollback()
            logger.error(f"Unexpected error saat add_query: {e}")
            raise

    def update_query_status(self, query_id: int, status: str):
        """Update status query dengan error handling."""
        try:
            conn = self._connect()
            conn.execute(
                "UPDATE queries SET status = ?, updated_at = ? WHERE id = ?",
                (status, datetime.utcnow().isoformat(), query_id)
            )
            conn.commit()
        except sqlite3.DatabaseError as e:
            logger.error(f"Database error saat update_query_status: {e}")
            raise

    def get_pending_queries(self) -> List[Tuple[int, str]]:
        """Ambil daftar query yang belum selesai (pending/failed)."""
        try:
            conn = self._connect()
            rows = conn.execute(
                "SELECT id, query_text FROM queries WHERE status IN (?, ?)",
                (STATUS_PENDING, STATUS_FAILED)
            ).fetchall()
            return [(r[0], r[1]) for r in rows]
        except sqlite3.DatabaseError as e:
            logger.error(f"Database error saat get_pending_queries: {e}")
            return []

    def get_all_queries(self) -> List[Tuple[int, str, str]]:
        """Ambil semua query beserta statusnya."""
        try:
            conn = self._connect()
            rows = conn.execute(
                "SELECT id, query_text, status FROM queries ORDER BY id DESC"
            ).fetchall()
            return [(r[0], r[1], r[2]) for r in rows]
        except sqlite3.DatabaseError as e:
            logger.error(f"Database error saat get_all_queries: {e}")
            return []

    # ── Result Management ─────────────────────────────────────────────

    def add_result(self, query_id: int, result: Dict[str, Any]) -> bool:
        """
        Simpan satu hasil pencarian.
        Mengabaikan duplikat (href yang sama untuk query_id yang sama).
        Mengembalikan True jika data baru disimpan.
        """
        now = datetime.utcnow().isoformat()
        conn = self._connect()
        try:
            conn.execute(
                "INSERT OR IGNORE INTO results (query_id, title, href, body, raw_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    query_id,
                    result.get("title", ""),
                    result.get("href", ""),
                    result.get("body", ""),
                    json.dumps(result, ensure_ascii=False),
                    now
                )
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            # Duplikat
            return False
        except sqlite3.DatabaseError as e:
            logger.error(f"Database error saat add_result: {e}")
            return False

    def add_results_batch(self, query_id: int, results: List[Dict[str, Any]]) -> int:
        """Tambahkan banyak hasil sekaligus. Mengembalikan jumlah yang benar‑benar baru."""
        count = 0
        for res in results:
            try:
                if self.add_result(query_id, res):
                    count += 1
            except Exception as e:
                logger.warning(f"Error saat add_result dalam batch: {e}")
                continue
        return count

    def get_results_by_query(self, query_id: int) -> List[Dict[str, Any]]:
        """Ambil semua hasil untuk query tertentu."""
        try:
            conn = self._connect()
            rows = conn.execute(
                "SELECT title, href, body, raw_json FROM results WHERE query_id = ?",
                (query_id,)
            ).fetchall()
            results = []
            for r in rows:
                if r[3]:  # raw_json
                    try:
                        data = json.loads(r[3])
                    except json.JSONDecodeError:
                        data = {"title": r[0], "href": r[1], "body": r[2]}
                else:
                    data = {"title": r[0], "href": r[1], "body": r[2]}
                results.append(data)
            return results
        except sqlite3.DatabaseError as e:
            logger.error(f"Database error saat get_results_by_query: {e}")
            return []

    def get_all_results(self) -> Dict[int, List[Dict[str, Any]]]:
        """Kembalikan dict {query_id: [results]}."""
        try:
            conn = self._connect()
            rows = conn.execute(
                "SELECT r.query_id, r.title, r.href, r.body, r.raw_json, q.query_text "
                "FROM results r JOIN queries q ON r.query_id = q.id"
            ).fetchall()
            data: Dict[int, List[Dict]] = {}
            for row in rows:
                qid = row[0]
                if row[4]:
                    try:
                        item = json.loads(row[4])
                    except json.JSONDecodeError:
                        item = {"title": row[1], "href": row[2], "body": row[3]}
                else:
                    item = {"title": row[1], "href": row[2], "body": row[3]}
                data.setdefault(qid, []).append(item)
            return data
        except sqlite3.DatabaseError as e:
            logger.error(f"Database error saat get_all_results: {e}")
            return {}

    # ── Deduplication ─────────────────────────────────────────────────

    def is_duplicate(self, href: str) -> bool:
        """Cek apakah URL sudah pernah disimpan di seluruh database."""
        try:
            conn = self._connect()
            row = conn.execute(
                "SELECT COUNT(*) FROM results WHERE href = ?", (href,)
            ).fetchone()
            return row[0] > 0
        except sqlite3.DatabaseError as e:
            logger.error(f"Database error saat is_duplicate: {e}")
            return False

    # ── Export ────────────────────────────────────────────────────────

    def export_to_json(self, output_path: str) -> None:
        """Export semua hasil ke file JSON."""
        try:
            data = self.get_all_results()
            # Ubah key integer menjadi string untuk JSON
            serializable = {str(k): v for k, v in data.items()}
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(serializable, f, indent=2, ensure_ascii=False)
            logger.info("Database diekspor ke %s", output_path)
        except IOError as e:
            logger.error(f"IO error saat export_to_json: {e}")
            raise
        except Exception as e:
            logger.error(f"Error saat export_to_json: {e}")
            raise

    def export_to_csv(self, output_path: str) -> None:
        """Export semua hasil ke file CSV."""
        try:
            conn = self._connect()
            rows = conn.execute(
                "SELECT q.query_text, r.title, r.href, r.body "
                "FROM results r JOIN queries q ON r.query_id = q.id"
            ).fetchall()
            with open(output_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["query", "title", "href", "body"])
                writer.writerows(rows)
            logger.info("Database diekspor ke %s", output_path)
        except IOError as e:
            logger.error(f"IO error saat export_to_csv: {e}")
            raise
        except Exception as e:
            logger.error(f"Error saat export_to_csv: {e}")
            raise

    # ── Maintenance ──────────────────────────────────────────────────

    def vacuum(self):
        """Optimalkan ukuran database dengan error handling."""
        try:
            self._connect().execute("VACUUM")
            logger.info("Database vacuum selesai")
        except sqlite3.DatabaseError as e:
            logger.error(f"Database error saat vacuum: {e}")
            raise
