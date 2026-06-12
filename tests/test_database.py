"""
Atdork – SQLite Database Layer
Menyimpan hasil pencarian ke database SQLite lokal untuk resume, history, dan deduplikasi.
"""

import sqlite3
import json
import csv
import logging
from datetime import datetime, timezone
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
        """Buka koneksi (otomatis buat file jika belum ada)."""
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.execute("PRAGMA journal_mode=WAL")   # performa & concurrent
            self._conn.execute("PRAGMA foreign_keys = ON")
        return self._conn

    def close(self):
        """Tutup koneksi database."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def _init_db(self):
        """Buat tabel jika belum ada."""
        conn = self._connect()
        conn.executescript(SQL_CREATE_TABLES)
        conn.commit()
        logger.debug("Database siap di %s", self.db_path)

    # ── Query Management ──────────────────────────────────────────────

    def add_query(self, query_text: str, status: str = STATUS_PENDING) -> int:
        """
        Tambahkan query baru. Mengembalikan ID query.
        Jika query sudah ada, update statusnya.
        """
        now = datetime.now(timezone.utc).isoformat()
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
        except Exception as e:
            conn.rollback()
            raise e

    def update_query_status(self, query_id: int, status: str):
        now = datetime.now(timezone.utc).isoformat()
        conn = self._connect()
        conn.execute(
            "UPDATE queries SET status = ?, updated_at = ? WHERE id = ?",
            (status, now, query_id)
        )
        conn.commit()

    def get_pending_queries(self) -> List[Tuple[int, str]]:
        """Ambil daftar query yang belum selesai (pending/failed)."""
        conn = self._connect()
        rows = conn.execute(
            "SELECT id, query_text FROM queries WHERE status IN (?, ?)",
            (STATUS_PENDING, STATUS_FAILED)
        ).fetchall()
        return [(r[0], r[1]) for r in rows]

    def get_all_queries(self) -> List[Tuple[int, str, str]]:
        """Ambil semua query beserta statusnya."""
        conn = self._connect()
        rows = conn.execute(
            "SELECT id, query_text, status FROM queries ORDER BY id DESC"
        ).fetchall()
        return [(r[0], r[1], r[2]) for r in rows]

    # ── Result Management ─────────────────────────────────────────────

    def add_result(self, query_id: int, result: Dict[str, Any]) -> bool:
        """
        Simpan satu hasil pencarian.
        Mengabaikan duplikat (href yang sama untuk query_id yang sama).
        Mengembalikan True jika data baru disimpan.
        """
        now = datetime.now(timezone.utc).isoformat()
        conn = self._connect()
        try:
            cursor = conn.execute(
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
            return cursor.rowcount > 0          # True hanya jika baris baru ditambahkan
        except sqlite3.IntegrityError:
            # Duplikat
            return False

    def add_results_batch(self, query_id: int, results: List[Dict[str, Any]]) -> int:
        """Tambahkan banyak hasil sekaligus. Mengembalikan jumlah yang benar‑benar baru."""
        count = 0
        for res in results:
            if self.add_result(query_id, res):
                count += 1
        return count

    def get_results_by_query(self, query_id: int) -> List[Dict[str, Any]]:
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

    def get_all_results(self) -> Dict[int, List[Dict[str, Any]]]:
        """Kembalikan dict {query_id: [results]}."""
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

    # ── Deduplication ─────────────────────────────────────────────────

    def is_duplicate(self, href: str) -> bool:
        """Cek apakah URL sudah pernah disimpan di seluruh database."""
        conn = self._connect()
        row = conn.execute(
            "SELECT COUNT(*) FROM results WHERE href = ?", (href,)
        ).fetchone()
        return row[0] > 0

    # ── Export ────────────────────────────────────────────────────────

    def export_to_json(self, output_path: str) -> None:
        """Export semua hasil ke file JSON."""
        data = self.get_all_results()
        # Ubah key integer menjadi string untuk JSON
        serializable = {str(k): v for k, v in data.items()}
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(serializable, f, indent=2, ensure_ascii=False)
        logger.info("Database diekspor ke %s", output_path)

    def export_to_csv(self, output_path: str) -> None:
        """Export semua hasil ke file CSV."""
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

    # ── Maintenance ──────────────────────────────────────────────────

    def vacuum(self):
        """Optimalkan ukuran database."""
        self._connect().execute("VACUUM")
