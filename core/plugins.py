"""
AtDork Plugin System (core/plugins.py) — installable .py tools.

Plugins extend AtDork with new commands without touching the core: they are
Python files installed through the package manager into
``<store>/@plugins/<tool>/`` (or placed in a local ``plugins.paths`` folder).

Contract — one ``PLUGIN`` metadata dict + a ``run`` entry point::

    PLUGIN = {
        "name": "dorkbuilder",          # trigger flag: --dorkbuilder
        "version": "1.0.0",
        "description": "Build dork lists from text + a category",
        "options": [
            {"name": "text", "help": "Text to hunt for"},
            {"name": "type", "choices": ["social-media", "..."],
             "default": "social-media"},
            {"name": "limit", "type": "int", "default": 20},
            {"name": "list-types", "action": "store_true"},
        ],
    }

    def run(args, ctx) -> int:
        ...

Mandatory flag format — every option is registered as ``--<plugin>-<option>``
(the engine prefixes the short names itself; a fully spelled flag that does
not match ``--<plugin>-`` is rejected at registration). Dests are always
``<plugin>_<option>`` (dashes become underscores), so plugin options can never
collide with core flags or with each other.

A plugin runs when the bare trigger ``--<plugin>`` is passed **or** when any
``--<plugin>-*`` argument appears on the command line.

Metadata is read with :mod:`ast` literal parsing — listing/registration never
executes plugin code; the module is imported only when actually triggered.
"""

from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from core.config import get_setting

logger = logging.getLogger(__name__)

PLUGIN_FOLDER = "@plugins"       # ref form in the index / on the CLI
STORE_FOLDER = "plugins"         # store layout is @-less: <store>/plugins/...

_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{1,30}$")
_OPTION_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
_VALID_TYPES: Dict[str, type] = {"str": str, "int": int, "float": float}
_VALID_ACTIONS = {"store_true"}


class PluginError(Exception):
    """Raised for invalid plugin metadata or failed plugin execution."""


# ── Metadata ───────────────────────────────────────────────────────────────

def validate_meta(meta: Any, source: str) -> List[str]:
    """Return a list of contract errors for a PLUGIN metadata object."""
    errors: List[str] = []

    def err(path: str, message: str) -> None:
        errors.append(f"{source}: PLUGIN.{path}: {message}")

    if not isinstance(meta, dict):
        err("", "must be a mapping")
        return errors

    name = meta.get("name")
    if not isinstance(name, str) or not _NAME_RE.fullmatch(name):
        err("name", "must match ^[a-z][a-z0-9_-]{1,30}$ "
                    "(lowercase; becomes the --<name> flag)")

    for key in ("version", "description"):
        value = meta.get(key)
        if value is not None and not isinstance(value, str):
            err(key, "must be a string")

    unknown = set(meta) - {"name", "version", "description", "options"}
    if unknown:
        err("", f"unknown key(s): {', '.join(sorted(unknown))}")

    options = meta.get("options")
    if options is None:
        return errors
    if not isinstance(options, list):
        err("options", "must be a list of option mappings")
        return errors

    seen = set()
    for idx, opt in enumerate(options):
        where = f"options[{idx}]"
        if not isinstance(opt, dict):
            err(where, "must be a mapping")
            continue
        opt_name = opt.get("name")
        if not isinstance(opt_name, str) or not _OPTION_RE.fullmatch(opt_name):
            err(where, "name must match ^[a-z][a-z0-9_-]*$ "
                       "(registered as --<plugin>-<name>)")
            continue
        if opt_name in seen:
            err(where, f"duplicate option '{opt_name}'")
        seen.add(opt_name)

        action = opt.get("action")
        if action is not None and action not in _VALID_ACTIONS:
            err(where, f"action must be one of: {', '.join(sorted(_VALID_ACTIONS))}")

        type_name = opt.get("type")
        if type_name is not None and type_name not in _VALID_TYPES:
            err(where, f"type must be one of: {', '.join(sorted(_VALID_TYPES))}")

        choices = opt.get("choices")
        if choices is not None and (
                not isinstance(choices, list) or not choices
                or not all(isinstance(c, str) for c in choices)):
            err(where, "choices must be a non-empty list of strings")

        opt_unknown = set(opt) - {"name", "help", "default", "type",
                                  "choices", "action"}
        if opt_unknown:
            err(where, f"unknown key(s): {', '.join(sorted(opt_unknown))}")

        if opt.get("action") == "store_true" and (type_name is not None
                                                  or choices is not None):
            err(where, "store_true options cannot declare type/choices")

        default = opt.get("default")
        if default is not None and type_name in _VALID_TYPES and not isinstance(default, _VALID_TYPES[type_name]):
            err(where, f"default does not match type '{type_name}'")

    return errors


def load_plugin_meta(path: Path) -> Dict[str, Any]:
    """Read the top-level ``PLUGIN = {...}`` literal from *path* via AST.

    Never executes the file. Raises :class:`PluginError` when the literal is
    missing, not a mapping, or the file cannot be parsed.
    """
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as e:
        raise PluginError(f"Cannot read {path}: {e}") from e
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as e:
        raise PluginError(f"{path}: syntax error: {e}") from e

    meta: Any = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if "PLUGIN" in targets:
                meta = node.value
                break
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "PLUGIN" and node.value is not None:
                meta = node.value
                break

    if meta is None:
        raise PluginError(f"{path}: no top-level PLUGIN = {{...}} assignment")
    try:
        value = ast.literal_eval(meta)
    except (ValueError, SyntaxError) as e:
        raise PluginError(f"{path}: PLUGIN must be a literal dict, not an "
                          f"expression ({e})") from e
    if not isinstance(value, dict):
        raise PluginError(f"{path}: PLUGIN must be a dict")
    return value


# ── Discovery ──────────────────────────────────────────────────────────────

@dataclass
class PluginDef:
    """One discovered plugin (metadata + file location + status)."""
    name: str
    version: str
    description: str
    options: List[Dict[str, Any]]
    path: Path
    source: str            # "store" or the local path it was found under
    enabled: bool = True
    error: Optional[str] = None   # contract violations found at load time

    @property
    def ref(self) -> str:
        return f"{PLUGIN_FOLDER}/{self.name}"

    def flag_for(self, option: str) -> str:
        return f"--{self.name}-{option}"


def _plugins_config(config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg = config if config is not None else get_setting("plugins")
    return cfg if isinstance(cfg, dict) else {}


def _option_defaults(cfg: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    options = cfg.get("options")
    if not isinstance(options, dict):
        return {}
    return {str(name): value for name, value in options.items()
            if isinstance(value, dict)}


def discover_plugins(config: Optional[Dict[str, Any]] = None,
                     package_dir: Optional[str] = None) -> List[PluginDef]:
    """Find plugins in the package store and the ``plugins.paths`` folders.

    Store first, local paths after (a local plugin with the same name
    overrides the installed one — handy for development). Files starting with
    ``_`` are helpers, not entry points, and are skipped silently.
    """
    from core.package_manager import get_package_dir

    cfg = _plugins_config(config)
    roots: List[tuple] = []
    store = Path(get_package_dir(package_dir)) / STORE_FOLDER
    roots.append((store, "store"))

    paths = cfg.get("paths")
    if isinstance(paths, list):
        for raw_path in paths:
            if isinstance(raw_path, str) and raw_path.strip():
                root = Path(raw_path).expanduser()
                roots.append((root, str(root)))

    found: Dict[str, PluginDef] = {}
    for root, source in roots:
        if not root.is_dir():
            continue
        for file_path in sorted(root.rglob("*.py")):
            rel = file_path.relative_to(root)
            if file_path.name.startswith("_") or file_path.name == "conftest.py":
                continue
            if any(part.startswith(".") or part == "__pycache__"
                   for part in rel.parts):
                continue
            try:
                meta = load_plugin_meta(file_path)
            except PluginError as e:
                # A .py without PLUGIN inside a tool folder is a helper —
                # skip quietly. Structured (but invalid) metadata surfaces.
                logger.debug("plugin candidate skipped: %s", e)
                continue
            errors = validate_meta(meta, file_path.name)
            name = meta.get("name") if isinstance(meta.get("name"), str) else file_path.stem
            definition = PluginDef(
                name=name,
                version=str(meta.get("version", "")),
                description=str(meta.get("description", "")),
                options=[o for o in (meta.get("options") or [])
                         if isinstance(o, dict) and isinstance(o.get("name"), str)],
                path=file_path,
                source=source,
                error="; ".join(errors) if errors else None,
            )
            found[definition.name] = definition   # later root wins

    cfg_disabled = cfg.get("disabled")
    disabled = {str(n) for n in cfg_disabled} if isinstance(cfg_disabled, list) else set()
    enabled_cfg = cfg.get("enabled", "auto")
    if isinstance(enabled_cfg, list):
        allow = {str(n) for n in enabled_cfg}
    else:
        allow = None   # "auto" (or anything else) = everything installed

    for definition in found.values():
        definition.enabled = (definition.name not in disabled
                              and (allow is None or definition.name in allow))
    return list(found.values())


def register_warnings(defs: Sequence[PluginDef]) -> List[str]:
    """Name/flag collisions between plugins (prefix ambiguity)."""
    warnings: List[str] = []
    names = [d.name for d in defs]
    seen_pairs = set()
    for a in names:
        for b in names:
            if a != b and b.startswith(a + "-") and (a, b) not in seen_pairs:
                seen_pairs.add((a, b))
                warnings.append(
                    f"plugin '{a}' is a flag-prefix of '{b}' — "
                    f"--{a}-... args may activate both"
                )
    return warnings


# ── Argument registration ──────────────────────────────────────────────────

def register_plugin_args(parser, config: Optional[Dict[str, Any]] = None,
                         warn: Optional[Callable[[str], None]] = None
                         ) -> List[PluginDef]:
    """Register ``--<plugin>`` and ``--<plugin>-<option>`` flags on *parser*.

    Returns the discovered plugins (enabled ones are registered; warnings go
    to *warn* or the log). Call this after every core flag is defined.
    """
    emit = warn or (lambda msg: logger.warning("%s", msg))
    defs = discover_plugins(config=config)
    if not defs:
        return []

    existing: Dict[str, Any] = dict(parser._option_string_actions)
    group = parser.add_argument_group("plugins")
    defaults = _option_defaults(_plugins_config(config))

    registered: List[PluginDef] = []
    for definition in sorted(defs, key=lambda d: d.name):
        if definition.error:
            emit(f"[plugin] {definition.name} ignored: {definition.error}")
            continue
        # Disabled plugins still register their flags — otherwise their args
        # would die as "unrecognized arguments"; dispatch rejects them with a
        # clear "disabled in config" message instead.

        trigger = f"--{definition.name}"
        if trigger in existing:
            emit(f"[plugin] {definition.name}: flag {trigger} collides with a "
                 f"core flag — trigger via --{definition.name}-<option> instead")
        else:
            group.add_argument(trigger, action="store_true", dest=definition.name,
                               help=f"[plugin] {definition.description or definition.name}")
            existing[trigger] = None

        for opt in definition.options:
            flag = f"--{definition.name}-{opt['name']}"
            if flag in existing:
                emit(f"[plugin] {definition.name}: flag {flag} already registered — "
                     f"option '{opt['name']}' skipped")
                continue
            dest = flag[2:].replace("-", "_")
            kwargs: Dict[str, Any] = {
                "dest": dest,
                "help": f"[plugin {definition.name}] {opt.get('help', '')}".rstrip(),
            }
            if opt.get("action") == "store_true":
                kwargs["action"] = "store_true"
                kwargs["default"] = False
            else:
                kwargs["default"] = opt.get("default")
                type_name = opt.get("type")
                if type_name in _VALID_TYPES:
                    kwargs["type"] = _VALID_TYPES[type_name]
                if isinstance(opt.get("choices"), list):
                    kwargs["choices"] = opt["choices"]
            group.add_argument(flag, **kwargs)
            existing[flag] = None

        # Config defaults for this plugin's options (CLI still overrides).
        for key, value in defaults.get(definition.name, {}).items():
            dest = f"{definition.name}_{key}".replace("-", "_")
            if dest in {a.dest for a in parser._actions}:
                parser.set_defaults(**{dest: value})

        registered.append(definition)

    for message in register_warnings(registered):
        emit(f"[plugin] {message}")
    return registered


# ── Trigger detection & execution ──────────────────────────────────────────

def triggered_plugins(defs: Sequence[PluginDef], argv: Sequence[str],
                      args=None) -> List[PluginDef]:
    """Plugins the user asked for on this command line.

    Explicit: the bare ``--<name>`` trigger (store_true on *args*).
    Implicit: any ``--<name>-...`` token in *argv* (config defaults alone
    never trigger a plugin).
    """
    triggered: List[PluginDef] = []
    for definition in defs:
        # Disabled/invalid plugins are still detected so dispatch can answer
        # with a clear message instead of falling through to interactive mode.
        hit = bool(args is not None and getattr(args, definition.name, False))
        if not hit:
            prefix = f"--{definition.name}"
            for token in argv:
                if (token == prefix or token.startswith(prefix + "-")
                        or token.startswith(prefix + "=")):
                    hit = True
                    break
        if hit:
            triggered.append(definition)
    return triggered


@dataclass
class PluginContext:
    """What a plugin gets besides the argparse namespace."""
    console: Any
    workspace: Any = None
    package_dir: Optional[str] = None
    version: str = ""
    config: Dict[str, Any] = field(default_factory=dict)

    def get_setting(self, key: str, default: Any = None) -> Any:
        from core.config import get_setting as _get_setting
        return _get_setting(key, default)

    @property
    def results_dir(self) -> Path:
        if self.workspace is not None:
            return Path(self.workspace.results_dir)
        return Path.cwd()

    def guard_write(self, path) -> Path:
        """Resolve a plugin output path (environment-aware, strict guard)."""
        if self.workspace is not None:
            from core.env import EnvError
            try:
                return Path(self.workspace.guard_write(str(path)))
            except EnvError as e:
                raise PluginError(f"output escapes the environment root: {e}") from e
        return Path(path)

    def search(self, query: str, **kwargs):
        """Run one dork search through the normal AtDork engine."""
        from core.scanner import search_dork
        kwargs.setdefault("max_results", 20)
        return search_dork(query, **kwargs)


def make_context(workspace=None, console=None, config: Optional[Dict] = None) -> PluginContext:
    from core.package_manager import get_package_dir
    version = ""
    try:
        from atdork import VERSION
        version = VERSION
    except Exception:  # pragma: no cover - atdork not importable (embedders)
        pass
    return PluginContext(
        console=console,
        workspace=workspace,
        package_dir=str(get_package_dir()),
        version=version,
        config=dict(config or {}),
    )


def run_plugin(definition: PluginDef, args, ctx: PluginContext) -> int:
    """Import *definition*'s module and call its ``run(args, ctx)``."""
    import importlib.util

    try:
        spec = importlib.util.spec_from_file_location(
            f"atdork_plugin_{definition.name.replace('-', '_')}",
            str(definition.path),
        )
        if spec is None or spec.loader is None:  # pragma: no cover - defensive
            raise PluginError(f"Cannot load plugin module: {definition.path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except PluginError:
        raise
    except Exception as e:
        raise PluginError(
            f"plugin '{definition.name}' failed to import "
            f"({type(e).__name__}: {e})"
        ) from e

    meta = getattr(module, "PLUGIN", None)
    if not isinstance(meta, dict) or meta.get("name") != definition.name:
        raise PluginError(
            f"plugin '{definition.name}': PLUGIN name mismatch "
            f"({meta.get('name') if isinstance(meta, dict) else 'missing/invalid'} "
            f"in {definition.path})"
        )
    entry = getattr(module, "run", None)
    if not callable(entry):
        raise PluginError(f"plugin '{definition.name}' has no run(args, ctx) function")

    result = entry(args, ctx)
    if result is None:
        return 0
    if isinstance(result, bool) or not isinstance(result, int):
        raise PluginError(
            f"plugin '{definition.name}': run() must return an int exit code, "
            f"got {result!r}"
        )
    return int(result)


def dispatch_plugin(args, argv: Sequence[str], workspace=None, console=None,
                    config: Optional[Dict[str, Any]] = None) -> Optional[int]:
    """Run every plugin triggered on this command line.

    Returns ``None`` when no plugin was requested (caller continues with the
    normal flow), otherwise the aggregated exit code (first non-zero wins).
    """
    defs = discover_plugins(config=config)
    triggered = triggered_plugins(defs, argv, args)
    if not triggered:
        return None

    ctx = make_context(workspace=workspace, console=console, config=config)
    exit_code = 0
    for definition in triggered:
        if console is not None:
            console.print(f"[magenta]▶ plugin[/magenta] {definition.name} "
                          f"[dim]({definition.path})[/dim]")
        if definition.error:
            if console is not None:
                console.print(f"[red]Plugin error:[/red] {definition.name} is "
                              f"invalid: {definition.error}")
            rc = 1
        elif not definition.enabled:
            if console is not None:
                console.print(f"[red]Plugin disabled:[/red] {definition.name} is "
                              f"disabled in config (plugins.enabled / "
                              f"plugins.disabled)")
            rc = 1
        else:
            try:
                rc = run_plugin(definition, args, ctx)
            except PluginError as e:
                if console is not None:
                    console.print(f"[red]Plugin error:[/red] {e}")
                rc = 1
            except Exception as e:  # plugin crashed outside its contract
                logger.exception("plugin '%s' crashed", definition.name)
                if console is not None:
                    console.print(f"[red]Plugin '{definition.name}' crashed:[/red] "
                                  f"{type(e).__name__}: {e} "
                                  f"[dim](use --debug for the traceback)[/dim]")
                rc = 1
        if rc and not exit_code:
            exit_code = rc
    return exit_code
