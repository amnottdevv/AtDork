import os
import json
import csv
from datetime import datetime


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
            os.makedirs(output_dir, exist_ok=True)
        filename = f"dork_{timestamp}.{output_format}"
        path = os.path.join(output_dir or ".", filename)
        fmt = output_format

    # Tulis file
    if fmt == "txt":
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

    elif fmt == "json":
        with open(path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

    elif fmt == "csv":
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["title", "href", "body"])
            writer.writeheader()
            for res in results:
                writer.writerow({
                    "title": res.get("title", ""),
                    "href": res.get("href", ""),
                    "body": res.get("body", ""),
                })
    else:
        raise ValueError(f"Format tidak didukung: {fmt}")

    return path