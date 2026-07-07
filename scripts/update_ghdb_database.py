#!/usr/bin/env python
"""
scripts/update_ghdb_database.py

Mengambil seluruh dork dari GHDB, memecahnya per kategori, lalu menulis
masing-masing ke folder database/. Dipakai oleh GitHub Actions workflow
(.github/workflows/update-ghdb.yml) yang jalan mingguan, tapi juga bisa
dijalankan manual:

    python scripts/update_ghdb_database.py

Sengaja dibuat sebagai script terpisah dari atdork.py (bukan lewat CLI
--ghdb-scraper) supaya di CI cuma butuh dependency minimal (requests,
beautifulsoup4) tanpa perlu install seluruh dependency atdork (ddgs, pyyaml, dll).
"""

import logging
import os
import re
import sys
from datetime import datetime, timezone

# Supaya bisa import core.ghdb_scraper walau script dijalankan dari root repo.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.ghdb_scraper import fetch_all_dorks, summarize_categories  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DATABASE_DIR = "database"


def _slugify(name: str) -> str:
    """Ubah nama kategori jadi nama file yang aman, mis. 'Files Containing Passwords' -> 'files_containing_passwords'."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    slug = slug.strip("_")
    return slug or "unknown"


def _category_filename(cat_id: int, cat_title: str) -> str:
    return f"{cat_id:02d}_{_slugify(cat_title)}.txt"


def export_database():
    logger.info("Mengambil data GHDB...")
    data = fetch_all_dorks()
    if data is None:
        logger.error("Gagal mengambil data GHDB. Keluar dengan kode error.")
        sys.exit(1)

    all_dorks = data["dorks"]
    total_dorks = data["total_dorks"]

    os.makedirs(DATABASE_DIR, exist_ok=True)

    # Kelompokkan dork per kategori.
    by_category = {}
    for d in all_dorks:
        key = (d["cat_id"], d["cat_title"])
        by_category.setdefault(key, []).append(d)

    written_files = []
    for (cat_id, cat_title), dorks in sorted(by_category.items(), key=lambda kv: kv[0][0]):
        filename = _category_filename(cat_id, cat_title)
        filepath = os.path.join(DATABASE_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            for d in dorks:
                f.write(f"{d['text']}\n")
        written_files.append((filename, cat_title, len(dorks)))
        logger.info("Ditulis: %s (%d dork)", filepath, len(dorks))

    # Tulis README ringkasan supaya gampang lihat kapan terakhir update & isi tiap file.
    summary = summarize_categories(all_dorks)
    readme_path = os.path.join(DATABASE_DIR, "README.md")
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    with open(readme_path, "w", encoding="utf-8") as f:
        f.write("# GHDB Dork Database\n\n")
        f.write(f"Terakhir diperbarui: **{now_utc}**\n\n")
        f.write(f"Total dork: **{total_dorks}**\n\n")
        f.write("Sumber: [Exploit-DB Google Hacking Database](https://www.exploit-db.com/google-hacking-database)\n\n")
        f.write("| File | Kategori | Jumlah Dork |\n")
        f.write("|---|---|---|\n")
        for filename, cat_title, count in sorted(written_files, key=lambda x: x[0]):
            f.write(f"| `{filename}` | {cat_title} | {count} |\n")

    logger.info("README.md ditulis di %s", readme_path)
    logger.info("Selesai. Total %d dork tersebar di %d file kategori.", total_dorks, len(written_files))


if __name__ == "__main__":
    export_database()
