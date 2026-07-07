#!/usr/bin/env python
"""
core/ghdb_scraper.py
Modul GHDB Scraper untuk Atdork - mengambil Google Dorks dari Exploit-DB GHDB
lewat endpoint AJAX/JSON yang dipakai halaman GHDB itu sendiri.

Dipakai lewat flag CLI di atdork.py:
    atdork --ghdb-scraper --ghdb-file dorks/dorks.txt --ghdb-categories password,login --ghdb-years 2023-2024 --ghdb-r 60
"""

import json
import logging
import os
import random
import time
from typing import Optional, List, Dict, Any, Set

import requests
import urllib3
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

GHDB_URL = "https://www.exploit-db.com/google-hacking-database"

HEADERS = {
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "X-Requested-With": "XMLHttpRequest",
}


# --------------------------------------------------------------------------
# Fetch & parsing dasar
# --------------------------------------------------------------------------

def _fetch_ghdb_json(timeout: int = 10, max_retries: int = 3) -> Optional[dict]:
    """Ambil response JSON mentah dari endpoint GHDB, dengan retry sederhana."""
    for attempt in range(1, max_retries + 1):
        response = None
        try:
            logger.info("Requesting GHDB (attempt %d/%d): %s", attempt, max_retries, GHDB_URL)
            response = requests.get(GHDB_URL, headers=HEADERS, timeout=timeout)
        except requests.exceptions.SSLError:
            logger.warning("SSL error, mencoba ulang tanpa verifikasi sertifikat")
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            try:
                response = requests.get(GHDB_URL, headers=HEADERS, timeout=timeout, verify=False)
            except requests.exceptions.RequestException as e:
                logger.warning("Request gagal (attempt %d): %s", attempt, e)
        except requests.exceptions.RequestException as e:
            logger.warning("Request gagal (attempt %d): %s", attempt, e)

        if response is not None:
            if response.status_code != 200:
                logger.warning("Status code bukan 200: %s", response.status_code)
            else:
                try:
                    return response.json()
                except ValueError:
                    logger.warning(
                        "Response bukan JSON valid (kemungkinan diblokir / format berubah)"
                    )

        if attempt < max_retries:
            time.sleep(random.uniform(1, 3))

    return None


def _extract_dork_text(url_title_html: str) -> str:
    """Ekstrak teks dork murni dari fragmen HTML <a href=...>dork</a>."""
    soup = BeautifulSoup(url_title_html, "html.parser")
    a_tag = soup.find("a")
    if a_tag is None or not a_tag.contents:
        return ""
    return str(a_tag.contents[0]).strip()


def fetch_all_dorks() -> Optional[Dict[str, Any]]:
    """
    Ambil seluruh dork mentah dari GHDB dan susun jadi struktur yang mudah difilter.

    Returns:
        {
            "total_dorks": int,
            "dorks": [
                {
                    "text": "intitle:'index of' passwd",
                    "id": "5052",
                    "date": "2022-03-14",
                    "year": 2022,
                    "cat_id": 9,
                    "cat_title": "Files Containing Passwords",
                    "raw": {...}  # data mentah asli dari GHDB
                },
                ...
            ]
        }
        atau None kalau gagal.
    """
    json_response = _fetch_ghdb_json()
    if json_response is None:
        logger.error("Gagal mengambil data GHDB setelah beberapa percobaan")
        return None

    if "recordsTotal" not in json_response or "data" not in json_response:
        logger.error("Struktur JSON tidak sesuai ekspektasi (field recordsTotal/data hilang)")
        return None

    total_dorks = json_response["recordsTotal"]
    raw_dorks = json_response["data"]

    parsed_dorks = []
    for dork in raw_dorks:
        text = _extract_dork_text(dork.get("url_title", ""))
        if not text:
            logger.warning("Dork id=%s tidak bisa diparsing, dilewati", dork.get("id"))
            continue

        category = dork.get("category", {}) or {}
        try:
            cat_id = int(category.get("cat_id"))
        except (TypeError, ValueError):
            cat_id = -1
        cat_title = category.get("cat_title", "Unknown")

        date_str = dork.get("date", "") or ""
        year = None
        if len(date_str) >= 4 and date_str[:4].isdigit():
            year = int(date_str[:4])

        parsed_dorks.append(
            {
                "text": text,
                "id": dork.get("id"),
                "date": date_str,
                "year": year,
                "cat_id": cat_id,
                "cat_title": cat_title,
                "raw": dork,
            }
        )

    return {"total_dorks": total_dorks, "dorks": parsed_dorks}


# --------------------------------------------------------------------------
# Filtering
# --------------------------------------------------------------------------

def _parse_categories_arg(categories_arg: str) -> Dict[str, Set]:
    """
    Parse "--ghdb-categories" jadi dua kelompok: nama (partial, lowercase) dan id numerik.
    Contoh input: "password,9,login portals"
    """
    names = set()
    ids = set()
    for token in categories_arg.split(","):
        token = token.strip()
        if not token:
            continue
        if token.isdigit():
            ids.add(int(token))
        else:
            names.add(token.lower())
    return {"names": names, "ids": ids}


def _parse_years_arg(years_arg: str) -> Set[int]:
    """
    Parse "--ghdb-years" jadi set tahun.
    Mendukung:
      - single year: "2024"
      - multiple: "2022,2024"
      - range: "2020-2023"
      - kombinasi: "2018,2020-2022,2024"
    """
    years = set()
    for token in years_arg.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            parts = token.split("-")
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                start, end = int(parts[0]), int(parts[1])
                if start > end:
                    start, end = end, start
                years.update(range(start, end + 1))
            else:
                logger.warning("Format range tahun tidak valid, dilewati: '%s'", token)
        elif token.isdigit():
            years.add(int(token))
        else:
            logger.warning("Format tahun tidak valid, dilewati: '%s'", token)
    return years


def filter_dorks(
    dorks: List[dict],
    categories_arg: Optional[str] = None,
    years_arg: Optional[str] = None,
    max_results: Optional[int] = None,
) -> List[dict]:
    """Terapkan filter kategori, tahun, dan batas jumlah pada list dork hasil fetch_all_dorks()."""
    result = dorks

    if categories_arg:
        parsed = _parse_categories_arg(categories_arg)
        names, ids = parsed["names"], parsed["ids"]

        def _match_category(d):
            if d["cat_id"] in ids:
                return True
            title_lower = d["cat_title"].lower()
            return any(name in title_lower for name in names)

        result = [d for d in result if _match_category(d)]

    if years_arg:
        years = _parse_years_arg(years_arg)
        result = [d for d in result if d["year"] in years]

    if max_results is not None and max_results > 0:
        result = result[:max_results]

    return result


# --------------------------------------------------------------------------
# Kategori (untuk --ghdb-list-categories)
# --------------------------------------------------------------------------

def summarize_categories(dorks: List[dict]) -> List[Dict[str, Any]]:
    """Hitung jumlah dork per kategori dari list dork hasil fetch_all_dorks()."""
    counts = {}
    for d in dorks:
        key = (d["cat_id"], d["cat_title"])
        counts[key] = counts.get(key, 0) + 1
    summary = [
        {"cat_id": cat_id, "cat_title": cat_title, "count": count}
        for (cat_id, cat_title), count in counts.items()
    ]
    summary.sort(key=lambda x: x["cat_id"])
    return summary


# --------------------------------------------------------------------------
# Simpan ke file
# --------------------------------------------------------------------------

def save_dorks(dorks: List[dict], output_file: str) -> bool:
    """
    Simpan list dork ke file. Format ditentukan otomatis dari ekstensi:
    .json -> JSON lengkap (termasuk metadata), selain itu -> txt (satu dork per baris).
    """
    output_dir = os.path.dirname(output_file)
    if output_dir:
        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as e:
            logger.error("Gagal membuat folder '%s': %s", output_dir, e)
            return False

    try:
        if output_file.lower().endswith(".json"):
            payload = [
                {
                    "text": d["text"],
                    "id": d["id"],
                    "date": d["date"],
                    "cat_id": d["cat_id"],
                    "cat_title": d["cat_title"],
                }
                for d in dorks
            ]
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
        else:
            with open(output_file, "w", encoding="utf-8") as f:
                for d in dorks:
                    f.write(f"{d['text']}\n")
        return True
    except OSError as e:
        logger.error("Gagal menulis file '%s': %s", output_file, e)
        return False


# --------------------------------------------------------------------------
# Entry point tingkat tinggi, dipanggil dari atdork.py
# --------------------------------------------------------------------------

def run_ghdb_scraper(
    output_file: Optional[str] = None,
    categories: Optional[str] = None,
    years: Optional[str] = None,
    max_results: Optional[int] = None,
    list_categories: bool = False,
    console=None,
) -> bool:
    """
    Fungsi utama yang dipanggil dari atdork.py saat --ghdb-scraper (atau
    --ghdb-list-categories) dipakai.

    Args:
        output_file: path file tujuan (opsional, kalau kosong hasil cuma ditampilkan).
        categories: filter kategori, comma-separated nama (partial) dan/atau ID numerik.
        years: filter tahun, comma-separated / range, contoh "2020-2023,2024".
        max_results: batasi jumlah total dork setelah difilter.
        list_categories: kalau True, tampilkan daftar kategori beserta jumlah dork lalu keluar
                         (mengabaikan output_file/max_results).
        console: instance rich.console.Console (opsional). Kalau None, pakai print() biasa.

    Returns:
        True kalau sukses, False kalau gagal mengambil data.
    """

    def _out(msg: str):
        if console is not None:
            console.print(msg)
        else:
            print(msg)

    _out("[bold cyan]🔍 Mengambil data GHDB dari Exploit-DB...[/bold cyan]" if console else "Mengambil data GHDB dari Exploit-DB...")

    data = fetch_all_dorks()
    if data is None:
        _out("[red]❌ Gagal mengambil data GHDB. Cek koneksi atau coba lagi nanti.[/red]" if console else "Gagal mengambil data GHDB.")
        return False

    all_dorks = data["dorks"]

    if list_categories:
        summary = summarize_categories(all_dorks)
        _out(f"[bold cyan]Kategori GHDB yang tersedia ({len(summary)} kategori):[/bold cyan]" if console else f"Kategori GHDB yang tersedia ({len(summary)} kategori):")
        for cat in summary:
            _out(f"  [green]{cat['cat_id']:>2}[/green] - {cat['cat_title']} ({cat['count']} dork)" if console else f"  {cat['cat_id']:>2} - {cat['cat_title']} ({cat['count']} dork)")
        return True

    filtered = filter_dorks(
        all_dorks,
        categories_arg=categories,
        years_arg=years,
        max_results=max_results,
    )

    _out(
        f"[green]✅ Ditemukan {len(filtered)} dork[/green] (dari total {data['total_dorks']} di GHDB)"
        if console
        else f"Ditemukan {len(filtered)} dork (dari total {data['total_dorks']} di GHDB)"
    )

    if not filtered:
        _out("[yellow]⚠️ Tidak ada dork yang cocok dengan filter yang diberikan.[/yellow]" if console else "Tidak ada dork yang cocok dengan filter yang diberikan.")
        return True

    if output_file:
        success = save_dorks(filtered, output_file)
        if success:
            _out(f"[green]💾 Disimpan ke: {output_file}[/green]" if console else f"Disimpan ke: {output_file}")
        else:
            _out(f"[red]❌ Gagal menyimpan ke: {output_file}[/red]" if console else f"Gagal menyimpan ke: {output_file}")
            return False
    else:
        preview = filtered[:20]
        for d in preview:
            _out(f"  - {d['text']}")
        if len(filtered) > 20:
            _out(f"  ... dan {len(filtered) - 20} dork lainnya (gunakan --ghdb-file untuk simpan semua)")

    return True
