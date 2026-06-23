"""
AtDork vulnerability filtering helpers.

Default wordlists are loaded from packaged resources so the filters work from an
installed wheel, not only from a repository checkout.
"""

import logging
import os
import re
from importlib import resources
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

DEFAULT_WORDLIST_DIR = "wordlists"
WORDLIST_PACKAGE = "wordlists"
PACKAGE_PREFIX = "pkg://"

# Cache: key = resolved resource id, value = compiled regex patterns
_wordlist_cache: Dict[str, List[re.Pattern]] = {}


def _is_default_wordlist_dir(wordlist_dir: str) -> bool:
    return os.path.normpath(wordlist_dir) == os.path.normpath(DEFAULT_WORDLIST_DIR)


def _package_resource_id(package: str, resource_name: str) -> str:
    return f"{PACKAGE_PREFIX}{package}/{resource_name}"


def _parse_package_resource(resource_id: str) -> Tuple[str, str]:
    relative = resource_id[len(PACKAGE_PREFIX):]
    package, _, resource_name = relative.rpartition("/")
    return package, resource_name


def _resource_exists(filename: str, wordlist_dir: str) -> bool:
    if _is_default_wordlist_dir(wordlist_dir):
        try:
            return resources.files(WORDLIST_PACKAGE).joinpath(filename).is_file()
        except ModuleNotFoundError:
            return False
    return os.path.isfile(os.path.join(wordlist_dir, filename))


def _describe_wordlist_source(wordlist_dir: str) -> str:
    if _is_default_wordlist_dir(wordlist_dir):
        return f"paket resource '{WORDLIST_PACKAGE}'"
    return f"direktori '{os.path.abspath(wordlist_dir)}'"


def resolve_filter_arg(filter_arg: str, wordlist_dir: str = DEFAULT_WORDLIST_DIR) -> Tuple[str, str, str]:
    """
    Resolve a filter name into its wordlist resource.

    Returns:
        Tuple (base_name, filter_type, resource_id_or_path)
    """
    if filter_arg.endswith("-link") or filter_arg.endswith("-url"):
        filter_type = "link"
        base_name = re.sub(r"-(link|url)$", "", filter_arg)
    else:
        filter_type = "path"
        base_name = filter_arg

    filename = f"{filter_arg}.txt"

    if _is_default_wordlist_dir(wordlist_dir):
        if _resource_exists(filename, wordlist_dir):
            return base_name, filter_type, _package_resource_id(WORDLIST_PACKAGE, filename)
    else:
        filepath = os.path.abspath(os.path.join(wordlist_dir, filename))
        if os.path.isfile(filepath):
            return base_name, filter_type, filepath

    error_msg = [
        f"Error: Wordlist file '{filename}' tidak ditemukan.",
        f"   Sumber yang dicek: {_describe_wordlist_source(wordlist_dir)}",
    ]

    if filter_arg.endswith("-link"):
        base = filter_arg[:-5]
        base_filename = f"{base}.txt"
        if _resource_exists(base_filename, wordlist_dir):
            error_msg.append(
                f"   Tip: Ditemukan '{base_filename}'. Apakah maksud Anda '--filter-vuln {base}'?"
            )
    else:
        link_filename = f"{filter_arg}-link.txt"
        if _resource_exists(link_filename, wordlist_dir):
            error_msg.append(
                f"   Tip: Ditemukan '{link_filename}'. Apakah maksud Anda '--filter-vuln {filter_arg}-link'?"
            )

    raise FileNotFoundError("\n".join(error_msg))


def load_wordlist(path: str) -> List[re.Pattern]:
    """
    Load a wordlist and compile each non-empty line into a regex pattern.
    """
    if path.startswith(PACKAGE_PREFIX):
        package, resource_name = _parse_package_resource(path)
        resource = resources.files(package).joinpath(resource_name)
        if not resource.is_file():
            raise FileNotFoundError(f"Wordlist tidak ditemukan: {path}")
        stream = resource.open("r", encoding="utf-8")
    else:
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Wordlist tidak ditemukan: {path}")
        stream = open(path, "r", encoding="utf-8")

    patterns = []
    with stream as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                patterns.append(re.compile(line, re.IGNORECASE))
            except re.error as exc:
                logger.warning("Pola regex tidak valid di %s: %s (%s)", path, line, exc)

    logger.info("Dimuat %d pola dari %s", len(patterns), path)
    return patterns


def get_wordlist(filter_arg: str, wordlist_dir: str = DEFAULT_WORDLIST_DIR) -> List[re.Pattern]:
    """
    Return compiled regex patterns for a filter, with caching.
    """
    _, _, location = resolve_filter_arg(filter_arg, wordlist_dir)
    cache_key = location if location.startswith(PACKAGE_PREFIX) else os.path.abspath(location)
    if cache_key in _wordlist_cache:
        return _wordlist_cache[cache_key]

    patterns = load_wordlist(location)
    _wordlist_cache[cache_key] = patterns
    return patterns


def get_filter_info(filter_arg: str, wordlist_dir: str = DEFAULT_WORDLIST_DIR) -> Tuple[List[re.Pattern], str, str]:
    """
    Return (patterns, filter_type, base_name) for a vulnerability filter.
    """
    base_name, filter_type, _ = resolve_filter_arg(filter_arg, wordlist_dir)
    patterns = get_wordlist(filter_arg, wordlist_dir)
    return patterns, filter_type, base_name


def filter_vulnerable(
    results: List[Dict],
    filter_arg: str = "wordpress",
    wordlist_dir: str = DEFAULT_WORDLIST_DIR,
    **kwargs,
) -> Tuple[List[Dict], List[Dict], str]:
    """
    Split search results into vulnerable and safe buckets.
    """
    if "platform" in kwargs:
        filter_arg = kwargs["platform"]

    if not isinstance(results, list):
        logger.warning("filter_vulnerable: results bukan list, mengembalikan kosong.")
        return [], [], "unknown"

    if not results:
        return [], [], "unknown"

    patterns, filter_type, _ = get_filter_info(filter_arg, wordlist_dir)

    vulnerable = []
    safe = []

    for res in results:
        text = f"{res.get('title', '')} {res.get('href', '')} {res.get('body', '')}"
        if any(pattern.search(text) for pattern in patterns):
            vulnerable.append(res)
        else:
            safe.append(res)

    logger.info(
        "Filter %s (tipe %s): %d rentan, %d aman dari %d total hasil",
        filter_arg,
        filter_type,
        len(vulnerable),
        len(safe),
        len(results),
    )
    return vulnerable, safe, filter_type
