"""
Atdork – Template Dork Loader (core/template_dork.py)
Memuat, memvalidasi, dan menyediakan daftar dork dari file YAML template.

Fitur:
- Memisahkan dork bertarget (memerlukan --target) dan generik
- Substitusi variabel {target}
- Seleksi dork tertentu (--select 1,3,5)
- Daftar template yang tersedia
- Penanganan error yang jelas dan tidak membuat crash
"""

import os
import logging
from typing import List, Dict, Optional, Union
import yaml

logger = logging.getLogger(__name__)

# Folder default untuk template
DEFAULT_TEMPLATE_DIR = os.path.join("wordlists", "templates")

# Nama file template harus berakhiran .yaml atau .yml
VALID_EXTENSIONS = (".yaml", ".yml")


def _find_template_file(name: str, template_dir: str) -> str:
    """
    Mencari file template berdasarkan nama (tanpa ekstensi).
    Mengembalikan path lengkap file YAML.
    Jika tidak ditemukan, raise FileNotFoundError.
    """
    if not os.path.isdir(template_dir):
        raise FileNotFoundError(
            f"Direktori template tidak ditemukan: '{template_dir}'. "
            "Pastikan folder 'wordlists/templates/' ada atau gunakan --template-path."
        )

    # Coba semua ekstensi yang valid
    for ext in VALID_EXTENSIONS:
        path = os.path.join(template_dir, f"{name}{ext}")
        if os.path.isfile(path):
            return path

    raise FileNotFoundError(
        f"Template '{name}' tidak ditemukan di '{template_dir}'. "
        f"Gunakan --list-templates untuk melihat daftar yang tersedia."
    )


def _parse_template(filepath: str) -> Dict:
    """
    Membaca dan memparsing file YAML template.
    Mengembalikan dictionary dengan keys: name, description, targeted, generic, dll.
    Jika YAML tidak valid, raise ValueError.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(
            f"Format YAML di template '{os.path.basename(filepath)}' tidak valid: {e}"
        )
    except Exception as e:
        raise ValueError(
            f"Tidak dapat membaca template '{os.path.basename(filepath)}': {e}"
        )

    if not isinstance(data, dict):
        raise ValueError(
            f"Template '{os.path.basename(filepath)}' harus berisi mapping YAML, "
            f"bukan {type(data).__name__}."
        )

    # Pastikan setidaknya ada satu dork (targeted atau generic)
    targeted = data.get("targeted", [])
    generic = data.get("generic", [])
    if not targeted and not generic:
        raise ValueError(
            f"Template '{data.get('name', os.path.basename(filepath))}' "
            "tidak memiliki dork (targeted maupun generic)."
        )

    # Normalisasi: pastikan targeted dan generic adalah list
    if not isinstance(targeted, list):
        logger.warning("'targeted' bukan list, diabaikan.")
        data["targeted"] = []
    else:
        data["targeted"] = [str(d) for d in targeted if d]
    if not isinstance(generic, list):
        logger.warning("'generic' bukan list, diabaikan.")
        data["generic"] = []
    else:
        data["generic"] = [str(d) for d in generic if d]

    return data


def _render_dorks(template: Dict, target: Optional[str] = None) -> List[str]:
    """
    Menggabungkan dan merender dork dari template.
    - Jika target diberikan, substitusi {target} di bagian targeted.
    - Jika target tidak diberikan, dork targeted di-skip (dengan warning).
    - Generic selalu disertakan.
    """
    dorks = []
    has_targeted = bool(template.get("targeted"))
    has_generic = bool(template.get("generic"))

    # Proses targeted
    if has_targeted:
        if target:
            dorks.extend([d.replace("{target}", target) for d in template["targeted"]])
        else:
            logger.warning(
                "Template '%s' memiliki dork bertarget, tetapi --target tidak diberikan. "
                "Dork targeted akan diabaikan.",
                template.get("name", "unknown")
            )

    # Proses generic
    dorks.extend(template.get("generic", []))

    if not dorks:
        raise ValueError(
            f"Tidak ada dork yang tersedia untuk template '{template.get('name')}'. "
            "Periksa kembali isi template atau berikan --target."
        )

    return dorks


def _select_dorks(dorks: List[str], select_str: str) -> List[str]:
    """
    Memilih dork berdasarkan nomor (1-based).
    select_str bisa berupa:
      - "1"       -> pilih dork ke-1
      - "1,3,5"   -> pilih dork ke-1, 3, dan 5
    Indeks yang tidak valid akan raise ValueError.
    """
    indices = []
    for part in select_str.split(","):
        part = part.strip()
        if not part.isdigit():
            raise ValueError(f"Format select tidak valid: '{part}' bukan angka.")
        idx = int(part)
        if idx < 1 or idx > len(dorks):
            raise ValueError(
                f"Indeks select tidak valid: {idx}. "
                f"Template ini memiliki {len(dorks)} dork (1-{len(dorks)})."
            )
        indices.append(idx - 1)  # konversi ke 0-based

    return [dorks[i] for i in indices]


def list_available_templates(template_dir: str = DEFAULT_TEMPLATE_DIR) -> List[Dict]:
    """
    Mengembalikan daftar template yang tersedia beserta informasi singkat.
    Setiap item: {'name': ..., 'description': ..., 'file': ...}
    """
    if not os.path.isdir(template_dir):
        return []

    available = []
    for filename in sorted(os.listdir(template_dir)):
        if filename.endswith(VALID_EXTENSIONS):
            name = os.path.splitext(filename)[0]
            filepath = os.path.join(template_dir, filename)
            try:
                data = _parse_template(filepath)
                available.append({
                    "name": name,
                    "description": data.get("description", ""),
                    "category": data.get("category", ""),
                    "file": filepath,
                })
            except Exception as e:
                logger.warning("Gagal membaca template %s: %s", filepath, e)
                available.append({
                    "name": name,
                    "description": f"(error: {e})",
                    "category": "",
                    "file": filepath,
                })
    return available


def load_template_dorks(
    template_name: str,
    target: Optional[str] = None,
    select: Optional[str] = None,
    template_path: Optional[str] = None,
) -> List[str]:
    """
    Fungsi utama untuk memuat dork dari template.

    Args:
        template_name: Nama template (tanpa ekstensi) atau path relatif ke file YAML.
        target: Domain atau string pengganti {target} di dork targeted.
        select: String seleksi indeks dork (contoh: "1" atau "1,3,5").
        template_path: Path ke folder template (default: wordlists/templates/).

    Returns:
        List string dork yang siap digunakan.

    Raises:
        FileNotFoundError: Jika template tidak ditemukan.
        ValueError: Jika format YAML salah, tidak ada dork, atau indeks select tidak valid.
    """
    # Tentukan direktori template
    template_dir = template_path or DEFAULT_TEMPLATE_DIR

    # Jika template_name mengandung path, gunakan langsung
    if os.path.isfile(template_name):
        filepath = template_name
        name = os.path.splitext(os.path.basename(template_name))[0]
    else:
        filepath = _find_template_file(template_name, template_dir)
        name = template_name

    # Parse YAML
    template = _parse_template(filepath)

    # Render dork
    dorks = _render_dorks(template, target)

    # Seleksi jika diminta
    if select:
        dorks = _select_dorks(dorks, select)

    return dorks
