"""
AtDork template dork loader.

Default YAML templates are loaded from packaged resources so they remain
available after installation from a wheel.
"""

import logging
import os
from importlib import resources
from importlib.resources.abc import Traversable
from typing import Dict, List, Optional, Union

import yaml

logger = logging.getLogger(__name__)

DEFAULT_TEMPLATE_DIR = os.path.join("wordlists", "templates")
TEMPLATE_PACKAGE = "wordlists.templates"
VALID_EXTENSIONS = (".yaml", ".yml")


def _is_default_template_dir(template_dir: str) -> bool:
    return os.path.normpath(template_dir) == os.path.normpath(DEFAULT_TEMPLATE_DIR)


def _get_template_root(template_dir: str) -> Union[str, Traversable]:
    if _is_default_template_dir(template_dir):
        return resources.files(TEMPLATE_PACKAGE)
    return template_dir


def _display_template_path(filepath: Union[str, Traversable]) -> str:
    if isinstance(filepath, str):
        return filepath
    return f"{TEMPLATE_PACKAGE}/{filepath.name}"


def _basename(filepath: Union[str, Traversable]) -> str:
    if isinstance(filepath, str):
        return os.path.basename(filepath)
    return filepath.name


def _find_template_file(name: str, template_dir: str) -> Union[str, Traversable]:
    """
    Find a template YAML file by name (without extension).
    """
    root = _get_template_root(template_dir)
    if isinstance(root, str):
        if not os.path.isdir(root):
            raise FileNotFoundError(
                f"Direktori template tidak ditemukan: '{root}'. "
                "Pastikan folder 'wordlists/templates/' ada atau gunakan --template-path."
            )

        for ext in VALID_EXTENSIONS:
            path = os.path.join(root, f"{name}{ext}")
            if os.path.isfile(path):
                return path
    else:
        for ext in VALID_EXTENSIONS:
            resource = root.joinpath(f"{name}{ext}")
            if resource.is_file():
                return resource

    raise FileNotFoundError(
        f"Template '{name}' tidak ditemukan di '{template_dir}'. "
        "Gunakan --list-templates untuk melihat daftar yang tersedia."
    )


def _parse_template(filepath: Union[str, Traversable]) -> Dict:
    """
    Parse a YAML template file into a normalized dictionary.
    """
    filename = _basename(filepath)
    try:
        if isinstance(filepath, str):
            stream = open(filepath, "r", encoding="utf-8")
        else:
            stream = filepath.open("r", encoding="utf-8")
        with stream as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise ValueError(f"Format YAML di template '{filename}' tidak valid: {exc}") from exc
    except Exception as exc:
        raise ValueError(f"Tidak dapat membaca template '{filename}': {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(
            f"Template '{filename}' harus berisi mapping YAML, bukan {type(data).__name__}."
        )

    targeted = data.get("targeted", [])
    generic = data.get("generic", [])
    if not targeted and not generic:
        raise ValueError(
            f"Template '{data.get('name', filename)}' tidak memiliki dork (targeted maupun generic)."
        )

    if not isinstance(targeted, list):
        logger.warning("'targeted' bukan list, diabaikan.")
        data["targeted"] = []
    else:
        data["targeted"] = [str(item) for item in targeted if item]

    if not isinstance(generic, list):
        logger.warning("'generic' bukan list, diabaikan.")
        data["generic"] = []
    else:
        data["generic"] = [str(item) for item in generic if item]

    return data


def _render_dorks(template: Dict, target: Optional[str] = None) -> List[str]:
    """
    Render targeted and generic dorks from a parsed template.
    """
    dorks = []
    has_targeted = bool(template.get("targeted"))

    if has_targeted:
        if target:
            dorks.extend([dork.replace("{target}", target) for dork in template["targeted"]])
        else:
            logger.warning(
                "Template '%s' memiliki dork bertarget, tetapi --target tidak diberikan. "
                "Dork targeted akan diabaikan.",
                template.get("name", "unknown"),
            )

    dorks.extend(template.get("generic", []))

    if not dorks:
        raise ValueError(
            f"Tidak ada dork yang tersedia untuk template '{template.get('name')}'. "
            "Periksa kembali isi template atau berikan --target."
        )

    return dorks


def _select_dorks(dorks: List[str], select_str: str) -> List[str]:
    """
    Select dorks by 1-based index.
    """
    indices = []
    for part in select_str.split(","):
        part = part.strip()
        if not part.isdigit():
            raise ValueError(f"Format select tidak valid: '{part}' bukan angka.")
        idx = int(part)
        if idx < 1 or idx > len(dorks):
            raise ValueError(
                f"Indeks select tidak valid: {idx}. Template ini memiliki {len(dorks)} dork (1-{len(dorks)})."
            )
        indices.append(idx - 1)

    return [dorks[i] for i in indices]


def list_available_templates(template_dir: str = DEFAULT_TEMPLATE_DIR) -> List[Dict]:
    """
    Return available template metadata for a directory or packaged template set.
    """
    root = _get_template_root(template_dir)
    if isinstance(root, str):
        if not os.path.isdir(root):
            return []
        entries: List[Union[str, Traversable]] = [
            os.path.join(root, filename)
            for filename in sorted(os.listdir(root))
        ]
    else:
        entries = sorted(root.iterdir(), key=lambda entry: entry.name)

    available = []
    for entry in entries:
        filename = _basename(entry)
        if not filename.endswith(VALID_EXTENSIONS):
            continue

        name = os.path.splitext(filename)[0]
        try:
            data = _parse_template(entry)
            available.append({
                "name": name,
                "description": data.get("description", ""),
                "category": data.get("category", ""),
                "file": _display_template_path(entry),
            })
        except Exception as exc:
            logger.warning("Gagal membaca template %s: %s", _display_template_path(entry), exc)
            available.append({
                "name": name,
                "description": f"(error: {exc})",
                "category": "",
                "file": _display_template_path(entry),
            })

    return available


def load_template_dorks(
    template_name: str,
    target: Optional[str] = None,
    select: Optional[str] = None,
    template_path: Optional[str] = None,
) -> List[str]:
    """
    Load rendered dorks from a template name or YAML path.
    """
    template_dir = template_path or DEFAULT_TEMPLATE_DIR

    if os.path.isfile(template_name):
        filepath: Union[str, Traversable] = template_name
    else:
        filepath = _find_template_file(template_name, template_dir)

    template = _parse_template(filepath)
    dorks = _render_dorks(template, target)

    if select:
        dorks = _select_dorks(dorks, select)

    return dorks
