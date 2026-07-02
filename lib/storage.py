import os
import json
import csv
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


def save_results(
    results: list,
    query: str,
    output_path: str = None,
    output_format: str = "txt",
    output_dir: str = None,
) -> str:
    """
    Simpan hasil ke file.

    - Jika `output_path` diberikan, file disimpan persis di path tersebut.
    - Jika hanya `output_dir`, nama file dibuat otomatis di folder itu.
    - Jika tidak ada keduanya, simpan di direktori kerja saat ini dengan nama otomatis.
    - Format: 'txt', 'json', 'csv'

    Mengembalikan path file yang disimpan.
    
    Raises:
        OSError: Jika permission denied, disk penuh, atau path invalid
        ValueError: Jika format tidak didukung
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Tentukan path akhir
    if output_path:
        path = output_path
        # Ambil ekstensi untuk menentukan format jika tidak eksplisit
        ext = os.path.splitext(output_path)[1].lower()
        if ext == ".json":
            fmt = "json"
        elif ext == ".csv":
            fmt = "csv"
        else:
            fmt = "txt"
        # Namun jika user secara eksplisit memberi --format, pakai itu
        if output_format != "txt":   # karena default txt, jika berubah berarti disengaja
            fmt = output_format
    else:
        if output_dir:
            try:
                os.makedirs(output_dir, exist_ok=True)
            except OSError as e:
                logger.error(f"Gagal membuat direktori {output_dir}: {e}")
                raise
        filename = f"dork_{timestamp}.{output_format}"
        path = os.path.join(output_dir or ".", filename)
        fmt = output_format

    # FIX HIGH: Add comprehensive file I/O error handling
    try:
        if fmt == "txt":
            _save_txt(path, results, query)
        elif fmt == "json":
            _save_json(path, results)
        elif fmt == "csv":
            _save_csv(path, results)
        else:
            raise ValueError(f"Format tidak didukung: {fmt}")
        
        logger.info(f"Hasil disimpan ke {path}")
        return path
        
    except IOError as e:
        logger.error(f"IO error saat menyimpan file {path}: {e}")
        raise
    except OSError as e:
        logger.error(f"OS error saat menyimpan file {path}: {e}")
        raise
    except Exception as e:
        logger.error(f"Error tidak terduga saat menyimpan file {path}: {e}")
        raise


def _save_txt(path: str, results: list, query: str) -> None:
    """Simpan hasil ke format TXT dengan error handling."""
    try:
        # Pastikan direktori ada
        output_dir = os.path.dirname(path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        
        with open(path, "w", encoding="utf-8") as f:
            f.write(
                f"Dork Scanner Results\n"
                f"Query: {query}\n"
                f"Timestamp: {datetime.now()}\n"
                f"Total: {len(results)}\n\n"
            )
            for i, res in enumerate(results, 1):
                f.write(f"[{i}] TITLE: {res.get('title', 'N/A')}\n")
                f.write(f"    URL: {res.get('href', 'N/A')}\n")
                f.write(f"    SNIPPET: {res.get('body', 'N/A')}\n")
                f.write("-" * 80 + "\n")
    except IOError as e:
        logger.error(f"IO error saat menyimpan TXT {path}: {e}")
        raise
    except Exception as e:
        logger.error(f"Error saat menyimpan TXT {path}: {e}")
        raise


def _save_json(path: str, results: list) -> None:
    """Simpan hasil ke format JSON dengan error handling."""
    try:
        # Pastikan direktori ada
        output_dir = os.path.dirname(path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        
        with open(path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
    except IOError as e:
        logger.error(f"IO error saat menyimpan JSON {path}: {e}")
        raise
    except (TypeError, ValueError) as e:
        logger.error(f"JSON serialization error saat menyimpan {path}: {e}")
        raise
    except Exception as e:
        logger.error(f"Error saat menyimpan JSON {path}: {e}")
        raise


def _save_csv(path: str, results: list) -> None:
    """Simpan hasil ke format CSV dengan error handling."""
    try:
        # Pastikan direktori ada
        output_dir = os.path.dirname(path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["title", "href", "body"])
            writer.writeheader()
            for res in results:
                try:
                    writer.writerow({
                        "title": res.get("title", ""),
                        "href": res.get("href", ""),
                        "body": res.get("body", ""),
                    })
                except (ValueError, TypeError) as e:
                    logger.warning(f"Error menulis row ke CSV: {e}")
                    continue
    except IOError as e:
        logger.error(f"IO error saat menyimpan CSV {path}: {e}")
        raise
    except Exception as e:
        logger.error(f"Error saat menyimpan CSV {path}: {e}")
        raise
