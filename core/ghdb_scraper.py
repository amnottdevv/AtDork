#!/usr/bin/env python
"""
AtDork - GHDB Scraper (ghdb_scraper.py)
Mengambil Google Dorks dari Exploit-DB GHDB (Google Hacking Database)
lewat endpoint AJAX/JSON yang dipakai halaman GHDB itu sendiri.
"""

# Standard Python libraries.
import argparse
import json
import logging
import os
import time
import random

# Third party Python libraries.
from bs4 import BeautifulSoup
import requests
import urllib3

__version__ = "1.4.0"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
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

CATEGORIES = {
    1: "Footholds",
    2: "File Containing Usernames",
    3: "Sensitive Directories",
    4: "Web Server Detection",
    5: "Vulnerable Files",
    6: "Vulnerable Servers",
    7: "Error Messages",
    8: "File Containing Juicy Info",
    9: "File Containing Passwords",
    10: "Sensitive Online Shopping Info",
    11: "Network or Vulnerability Data",
    12: "Pages Containing Login Portals",
    13: "Various Online Devices",
    14: "Advisories and Vulnerabilities",
}

"""
Contoh struktur satu dork dari response JSON GHDB:

{
    "id": "2",
    "date": "2003-06-24",
    "url_title": "<a href='/ghdb/2'>intitle:'Ganglia Cluster Report for'</a>",
    "cat_id": ["8", "Files Containing Juicy Info"],
    "author_id": ["2168", "anonymous"],
    "author": {"id": "2168", "name": "anonymous"},
    "category": {
        "cat_id": "8",
        "cat_title": "Files Containing Juicy Info",
        "cat_description": "No usernames or passwords, but interesting stuff.",
        "last_update": "2020-06-12",
        "records_count": "845",
        "porder": 0
    }
}
"""


def _fetch_ghdb_json(timeout: int = 10, max_retries: int = 3):
    """
    Ambil response JSON mentah dari endpoint GHDB, dengan retry sederhana
    dan penanganan error yang lebih lengkap dibanding versi awal.

    Returns:
        dict JSON response, atau None kalau gagal setelah semua retry.
    """
    for attempt in range(1, max_retries + 1):
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
                response = None
        except requests.exceptions.RequestException as e:
            logger.warning("Request gagal (attempt %d): %s", attempt, e)
            response = None

        if response is not None:
            if response.status_code != 200:
                logger.warning("Status code bukan 200: %s", response.status_code)
            else:
                try:
                    return response.json()
                except ValueError:
                    logger.warning(
                        "Response bukan JSON valid (kemungkinan diblokir / format berubah / "
                        "halaman HTML challenge)"
                    )

        if attempt < max_retries:
            delay = random.uniform(1, 3)
            time.sleep(delay)

    return None


def _extract_dork_text(url_title_html: str) -> str:
    """Ekstrak teks dork murni dari fragmen HTML <a href=...>dork</a>."""
    soup = BeautifulSoup(url_title_html, "html.parser")
    a_tag = soup.find("a")
    if a_tag is None or not a_tag.contents:
        return ""
    # Beberapa url_title punya trailing tab/whitespace, strip() untuk membersihkan.
    return str(a_tag.contents[0]).strip()


def retrieve_google_dorks(
    save_json_response_to_file: bool = False,
    save_all_dorks_to_file: bool = False,
    save_individual_categories_to_files: bool = False,
    output_dir: str = "dorks",
):
    """
    Mengambil seluruh Google Dorks dari GHDB dan (opsional) menyimpannya
    ke file JSON, file txt gabungan, dan/atau file per kategori.

    Args:
        save_json_response_to_file: simpan seluruh data mentah ke JSON.
        save_all_dorks_to_file: simpan semua dork ke satu file txt.
        save_individual_categories_to_files: simpan dork per kategori ke file terpisah.
        output_dir: folder tujuan penyimpanan file (dibuat otomatis kalau belum ada).

    Returns:
        dict berisi total_dorks, extracted_dorks (list), dan category_dict,
        atau None kalau gagal mengambil data.
    """
    json_response = _fetch_ghdb_json()
    if json_response is None:
        logger.error("Gagal mengambil data GHDB setelah beberapa percobaan")
        return None

    if "recordsTotal" not in json_response or "data" not in json_response:
        logger.error("Struktur JSON tidak sesuai ekspektasi (field recordsTotal/data hilang)")
        return None

    total_dorks = json_response["recordsTotal"]
    json_dorks = json_response["data"]

    extracted_dorks = []
    category_dict = {}

    for dork in json_dorks:
        extracted_dork = _extract_dork_text(dork.get("url_title", ""))
        if not extracted_dork:
            logger.warning("Dork id=%s tidak bisa diparsing, dilewati", dork.get("id"))
            continue
        extracted_dorks.append(extracted_dork)

        category = dork.get("category", {})
        try:
            numeric_category_id = int(category.get("cat_id"))
        except (TypeError, ValueError):
            numeric_category_id = -1
        category_name = category.get("cat_title", "Unknown")

        if numeric_category_id not in category_dict:
            category_dict[numeric_category_id] = {"category_name": category_name, "dorks": []}

        # Bersihkan trailing tab pada url_title sebelum disimpan mentah.
        dork["url_title"] = dork.get("url_title", "").replace("\t", "")
        category_dict[numeric_category_id]["dorks"].append(dork)

    category_dict = dict(sorted(category_dict.items()))

    needs_output_dir = (
        save_json_response_to_file or save_all_dorks_to_file or save_individual_categories_to_files
    )
    if needs_output_dir:
        try:
            os.makedirs(output_dir, exist_ok=True)
        except OSError as e:
            logger.error("Gagal membuat folder output '%s': %s", output_dir, e)
            needs_output_dir = False

    if save_individual_categories_to_files and needs_output_dir:
        for key, value in category_dict.items():
            logger.info(
                "Kategori %s ('%s') memiliki %d dork", key, value["category_name"], len(value["dorks"])
            )
            dork_file_name = value["category_name"].lower().replace(" ", "_").replace("/", "_")
            full_path = os.path.join(output_dir, f"{dork_file_name}.dorks")
            try:
                with open(full_path, "w", encoding="utf-8") as fh:
                    for dork in value["dorks"]:
                        extracted_dork = _extract_dork_text(dork.get("url_title", ""))
                        if extracted_dork:
                            fh.write(f"{extracted_dork}\n")
                logger.info("Kategori '%s' disimpan ke: %s", value["category_name"], full_path)
            except OSError as e:
                logger.error("Gagal menulis file %s: %s", full_path, e)

    if save_json_response_to_file and needs_output_dir:
        full_path = os.path.join(output_dir, "all_google_dorks.json")
        try:
            with open(full_path, "w", encoding="utf-8") as json_file:
                json.dump(json_dorks, json_file, indent=2)
            logger.info("Seluruh dork (JSON) disimpan ke: %s", full_path)
        except OSError as e:
            logger.error("Gagal menulis file %s: %s", full_path, e)

    if save_all_dorks_to_file and needs_output_dir:
        full_path = os.path.join(output_dir, "all_google_dorks.txt")
        try:
            with open(full_path, "w", encoding="utf-8") as fh:
                for dork in extracted_dorks:
                    fh.write(f"{dork}\n")
            logger.info("Seluruh dork (txt) disimpan ke: %s", full_path)
        except OSError as e:
            logger.error("Gagal menulis file %s: %s", full_path, e)

    logger.info("Total dork berhasil diambil: %s", total_dorks)

    return {
        "total_dorks": total_dorks,
        "extracted_dorks": extracted_dorks,
        "category_dict": category_dict,
    }


def main():
    epilog = f"Kategori dork:\n\n{json.dumps(CATEGORIES, indent=4)}"

    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=(
            f"GHDB Scraper v{__version__} - Mengambil Google Hacking Database dorks dari "
            "https://www.exploit-db.com/google-hacking-database."
        ),
        epilog=epilog,
    )

    parser.add_argument(
        "-i",
        dest="save_individual_categories_to_files",
        action="store_true",
        default=False,
        help="Simpan tiap kategori dork ke file terpisah.",
    )
    parser.add_argument(
        "-j",
        dest="save_json_response_to_file",
        action="store_true",
        default=False,
        help="Simpan seluruh response JSON ke dorks/all_google_dorks.json",
    )
    parser.add_argument(
        "-s",
        dest="save_all_dorks_to_file",
        action="store_true",
        default=False,
        help="Simpan semua dork ke dorks/all_google_dorks.txt",
    )
    parser.add_argument(
        "-o",
        dest="output_dir",
        default="dorks",
        help="Folder tujuan penyimpanan file (default: 'dorks').",
    )

    args = parser.parse_args()

    if not any(
        [
            args.save_individual_categories_to_files,
            args.save_json_response_to_file,
            args.save_all_dorks_to_file,
        ]
    ):
        logger.info("Tidak ada opsi simpan file yang dipilih, hasil hanya ditampilkan di terminal.")

    result = retrieve_google_dorks(**vars(args))

    if result is None:
        logger.error("Scraping gagal, tidak ada data yang diambil.")
        return

    if not any(
        [
            args.save_individual_categories_to_files,
            args.save_json_response_to_file,
            args.save_all_dorks_to_file,
        ]
    ):
        print(f"\nTotal dork: {result['total_dorks']}")
        for dork in result["extracted_dorks"][:20]:
            print(f"  - {dork}")
        if len(result["extracted_dorks"]) > 20:
            print(f"  ... dan {len(result['extracted_dorks']) - 20} dork lainnya")


if __name__ == "__main__":
    main()
