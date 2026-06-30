"""
AtDork – Template Dork Loader (core/template_dork.py)

Load, validate, and serve dork lists from YAML template files.

Default YAML templates are loaded from packaged resources so they remain
available after installation from a wheel. Custom template directories
are also supported for user‑defined templates.

All public functions are designed to fail gracefully with clear error
messages rather than crashing the whole application.
"""

import logging
import os
import sys
from typing import Any, Dict, List, Optional, Union

import yaml

logger = logging.getLogger(__name__)

# Default directory for user‑supplied (file‑system) templates
DEFAULT_TEMPLATE_DIR: str = os.path.join("wordlists", "templates")

# Package name used to locate built‑in templates via importlib.resources
TEMPLATE_PACKAGE: str = "wordlists.templates"

# Recognised template file extensions
VALID_EXTENSIONS: tuple = (".yaml", ".yml")

# ------------------------------------------------------------------ #
#  Compatibility helpers for importlib.resources                      #
# ------------------------------------------------------------------ #

# In Python 3.11+ we can use importlib.resources.abc.Traversable as
# a type hint.  For older Python versions we simply fall back to Any.
# The run‑time code only uses string paths for now, so the type hint
# is purely for documentation purposes.
if sys.version_info >= (3, 11):
    from importlib import resources
    from importlib.resources.abc import Traversable
else:  # Python 3.9 / 3.10
    from importlib import resources
    Traversable = Any  # type: ignore[misc,no-redef]


# ------------------------------------------------------------------ #
#  Internal helpers                                                   #
# ------------------------------------------------------------------ #

def _is_default_template_dir(template_dir: str) -> bool:
    """Return ``True`` if *template_dir* equals the default location."""
    return os.path.normpath(template_dir) == os.path.normpath(DEFAULT_TEMPLATE_DIR)


def _get_template_root(template_dir: str) -> Union[str, Traversable]:
    """
    Return the root object for template lookups.

    If *template_dir* is the default directory we use the packaged
    resources (``importlib.resources``).  Otherwise we return the
    supplied directory path unchanged.
    """
    if _is_default_template_dir(template_dir):
        return resources.files(TEMPLATE_PACKAGE)
    return template_dir


def _display_template_path(filepath: Union[str, Traversable]) -> str:
    """Return a human‑readable representation of a template location."""
    if isinstance(filepath, str):
        return filepath
    # For packaged resources, show the package‑relative path.
    return f"{TEMPLATE_PACKAGE}/{filepath.name}"


def _basename(filepath: Union[str, Traversable]) -> str:
    """Return the base file name (without directory) of a template location."""
    if isinstance(filepath, str):
        return os.path.basename(filepath)
    return filepath.name


def _find_template_file(
    name: str, template_dir: str
) -> Union[str, Traversable]:
    """
    Locate a template YAML file by its *name* (without extension).

    Searches the default or user‑supplied *template_dir*.
    Returns a file‑system path (``str``) or a ``Traversable`` resource.
    """
    root = _get_template_root(template_dir)

    if isinstance(root, str):
        # File‑system directory
        if not os.path.isdir(root):
            raise FileNotFoundError(
                f"Template directory not found: '{root}'. "
                "Ensure the 'wordlists/templates/' folder exists or use --template-path."
            )
        for ext in VALID_EXTENSIONS:
            path = os.path.join(root, f"{name}{ext}")
            if os.path.isfile(path):
                return path
    else:
        # Packaged resource directory
        for ext in VALID_EXTENSIONS:
            resource = root.joinpath(f"{name}{ext}")
            if resource.is_file():
                return resource

    raise FileNotFoundError(
        f"Template '{name}' was not found in '{template_dir}'. "
        "Use --list-templates to see the available templates."
    )


def _parse_template(filepath: Union[str, Traversable]) -> Dict:
    """
    Parse a YAML template file into a normalised dictionary.

    Returns a dict with keys ``name``, ``description``, ``targeted``,
    ``generic``, and any additional metadata present in the YAML.
    """
    filename = _basename(filepath)

    try:
        if isinstance(filepath, str):
            stream = open(filepath, "r", encoding="utf-8")
        else:
            stream = filepath.open("r", encoding="utf-8")
        with stream as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise ValueError(
            f"YAML syntax error in template '{filename}': {exc}"
        ) from exc
    except Exception as exc:
        raise ValueError(
            f"Could not read template '{filename}': {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise ValueError(
            f"Template '{filename}' must be a YAML mapping, not {type(data).__name__}."
        )

    # Ensure we have at least one dork (targeted or generic)
    targeted = data.get("targeted", [])
    generic = data.get("generic", [])
    if not targeted and not generic:
        raise ValueError(
            f"Template '{data.get('name', filename)}' contains no dorks "
            "(neither 'targeted' nor 'generic')."
        )

    # Normalise lists
    if not isinstance(targeted, list):
        logger.warning("'targeted' is not a list – ignoring.")
        data["targeted"] = []
    else:
        data["targeted"] = [str(item) for item in targeted if item]

    if not isinstance(generic, list):
        logger.warning("'generic' is not a list – ignoring.")
        data["generic"] = []
    else:
        data["generic"] = [str(item) for item in generic if item]

    return data


def _render_dorks(template: Dict, target: Optional[str] = None) -> List[str]:
    """
    Render the final list of dork strings from a parsed template.

    - If *target* is given, ``{target}`` is replaced in every dork in the
      ``targeted`` section.
    - If *target* is **not** given, ``targeted`` dorks are skipped with a
      warning, so that users are not accidentally running incomplete queries.
    - ``generic`` dorks are always included.
    """
    dorks: List[str] = []

    if template.get("targeted"):
        if target:
            for d in template["targeted"]:
                dorks.append(d.replace("{target}", target))
        else:
            logger.warning(
                "Template '%s' contains targeted dorks, but --target was not "
                "provided.  Targeted dorks will be skipped.",
                template.get("name", "unknown"),
            )

    dorks.extend(template.get("generic", []))

    if not dorks:
        # This should not happen because the parser already checks, but
        # we guard it anyway.
        raise ValueError(
            f"No dorks could be generated from template "
            f"'{template.get('name', 'unknown')}'."
        )

    return dorks


def _select_dorks(dorks: List[str], select_str: str) -> List[str]:
    """
    Select a subset of dorks by 1‑based index.

    *select_str* may be a single number (``"1"``) or a comma‑separated
    list of numbers (``"1,3,5"``).
    """
    indices: List[int] = []
    for part in select_str.split(","):
        part = part.strip()
        if not part.isdigit():
            raise ValueError(f"Invalid select index: '{part}' (must be a number).")
        idx = int(part)
        if idx < 1 or idx > len(dorks):
            raise ValueError(
                f"Select index {idx} is out of range. "
                f"Template contains {len(dorks)} dork(s) (1‑{len(dorks)})."
            )
        indices.append(idx - 1)

    return [dorks[i] for i in indices]


# ------------------------------------------------------------------ #
#  Public API                                                         #
# ------------------------------------------------------------------ #

def list_available_templates(
    template_dir: str = DEFAULT_TEMPLATE_DIR,
) -> List[Dict]:
    """
    Return metadata for every template found in *template_dir*.

    Each item is a dictionary with keys:
        - ``name`` (str) – template name without extension
        - ``description`` (str) – short description from the YAML
        - ``category`` (str) – category (e.g. 'web‑vuln', 'recon')
        - ``file`` (str) – human‑readable location
    """
    root = _get_template_root(template_dir)

    # Gather candidate entries
    if isinstance(root, str):
        if not os.path.isdir(root):
            return []
        entries: List[Union[str, Traversable]] = [
            os.path.join(root, filename)
            for filename in sorted(os.listdir(root))
        ]
    else:
        entries = sorted(root.iterdir(), key=lambda entry: entry.name)

    templates: List[Dict] = []
    for entry in entries:
        filename = _basename(entry)
        if not filename.endswith(VALID_EXTENSIONS):
            continue

        name = os.path.splitext(filename)[0]
        try:
            data = _parse_template(entry)
            templates.append({
                "name": name,
                "description": data.get("description", ""),
                "category": data.get("category", ""),
                "file": _display_template_path(entry),
            })
        except Exception as exc:
            logger.warning("Skipping template %s: %s", _display_template_path(entry), exc)
            templates.append({
                "name": name,
                "description": f"(error: {exc})",
                "category": "",
                "file": _display_template_path(entry),
            })

    return templates


def load_template_dorks(
    template_name: str,
    target: Optional[str] = None,
    select: Optional[str] = None,
    template_path: Optional[str] = None,
) -> List[str]:
    """
    Load rendered dork strings from a template.

    Parameters
    ----------
    template_name : str
        Template name (without extension) or a path to a YAML file.
    target : str, optional
        Domain or string to replace ``{target}`` in targeted dorks.
    select : str, optional
        Comma‑separated 1‑based indices of dorks to use (e.g. ``"1,3"``).
    template_path : str, optional
        Directory containing the template (default ``wordlists/templates/``).

    Returns
    -------
    List[str]
        The rendered dork strings ready for searching.

    Raises
    ------
    FileNotFoundError
        If the template cannot be found.
    ValueError
        If the YAML is invalid, the template contains no dorks, or
        the *select* indices are out of range.
    """
    # Determine the directory to search
    template_dir = template_path or DEFAULT_TEMPLATE_DIR

    # If the user provided a direct file path, use it; otherwise locate
    # the template in the designated directory.
    if os.path.isfile(template_name):
        filepath: Union[str, Traversable] = template_name
        name = os.path.splitext(os.path.basename(template_name))[0]
    else:
        filepath = _find_template_file(template_name, template_dir)
        name = template_name

    # Parse the YAML and render the dorks
    template = _parse_template(filepath)
    dorks = _render_dorks(template, target)

    # Optional index selection
    if select is not None:
        dorks = _select_dorks(dorks, select)

    return dorks
