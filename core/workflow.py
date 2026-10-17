"""
AtDork Workflow Engine — sequential multi-step dork campaigns (fase 3).

A workflow is a named, structured definition written in YAML. Steps run
strictly in order ("AtDork mengerjakan satu perintah, selesai → perintah
berikutnya") with:

* ``when_results_below`` + ``retry_with`` — when a step yields fewer unique
  results than a threshold, a list of alternate queries runs automatically
  and the results are merged + deduplicated;
* ``workers`` — thread concurrency *inside* a step (across its queries);
  steps themselves stay sequential;
* ``worker_overrides`` — a per-step (or workflow-level) search-kwarg overlay
  applied on top of the step config (e.g. force the ``serper`` API backend
  for one pool);
* ``outputs`` — write step results to txt/json/csv files, always through the
  environment write guard when a workspace is active;
* persistent state per workflow (``state/workflows/<name>.json``) enabling
  ``--resume``: steps recorded as done/below_threshold are skipped.

Definition sources (merged by name, file wins over config):

1. the ``workflows:`` section of any config layer (global / env / ``--config``);
2. standalone files passed via ``--file`` / ``--workflow-file``;
3. auto-discovered files named ``workflow.yaml`` (etc.) in the active
   environment root and the current working directory ("root").

Every query string supports ``{target}``, ``{step}``, ``{date}`` and
``{run_id}`` substitution.
"""

import json
import logging
import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from core.batch_runner import run_batch
from core.case.circuit_breaker import CircuitBreaker
from core.case.fallback_manager import FallbackManager
from core.case.retry_handler import RetryHandler
from core.config import get_setting
from core.env import EnvError, EnvEscapeError
from lib.storage import save_results

logger = logging.getLogger(__name__)


# ── Constants ──────────────────────────────────────────────────────────────

#: Filenames auto-discovered in the environment root and the CWD.
WORKFLOW_FILENAMES = (
    "workflow.yaml",
    "workflow.yml",
    "workflows.yaml",
    "workflows.yml",
    "atdork-workflow.yaml",
    "atdork-workflow.yml",
)

#: Tokens usable in queries/outputs via ``{...}`` substitution.
SUBSTITUTION_KEYS = ("target", "step", "date", "run_id")

#: Search-dork keyword arguments a workflow/step may set (subset of
#: ``search_dork`` — passed through ``run_batch``).
STEP_SEARCH_KEYS = {
    "backend", "max_results", "region", "safesearch", "timelimit", "timeout",
    "retries", "delay", "user_agent", "verify", "fallback_backends",
    "fallback_chain", "forced_proxy",
}

_INT_SEARCH_KEYS = {"max_results", "timeout", "retries"}
_FLOAT_SEARCH_KEYS = {"delay"}
_BOOL_SEARCH_KEYS = {"verify", "fallback_backends"}
_STR_SEARCH_KEYS = {
    "backend", "region", "safesearch", "timelimit", "user_agent", "forced_proxy",
}

OUTPUT_FORMATS = {"txt", "json", "csv"}

_WORKFLOW_KEYS = {
    "description", "target", "workers", "steps", "on_error", "worker_overrides",
} | STEP_SEARCH_KEYS

_STEP_KEYS = {
    "name", "query", "queries", "when_results_below", "retry_with", "on_error",
    "outputs", "worker_overrides",
} | STEP_SEARCH_KEYS

_ON_ERROR_VALUES = ("stop", "continue")

_TOKEN_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")

#: Backend fallback chain when the config has no ``search.fallback``.
_LEGACY_BACKENDS = ["duckduckgo", "startpage", "yandex", "yahoo", "wikipedia"]


class WorkflowError(Exception):
    """Raised for invalid workflow definitions or failed workflow runs."""


# ── Substitution ───────────────────────────────────────────────────────────

def substitute(text: str, context: Dict[str, Any]) -> str:
    """Replace ``{known_key}`` tokens in *text* from *context*.

    Unknown tokens (or literal braces that are not word-like tokens, e.g.
    ``{pdf,docx}``) are left untouched — typos are caught earlier by
    :func:`validate_workflow`.
    """
    if not isinstance(text, str) or "{" not in text:
        return text

    def _repl(match: "re.Match") -> str:
        key = match.group(1)
        if key in context:
            return str(context[key])
        return match.group(0)

    return _TOKEN_RE.sub(_repl, text)


def _check_tokens(value: str, where: str, errors: List[str]) -> None:
    """Record an error for every unknown ``{...}`` substitution token."""
    for match in _TOKEN_RE.finditer(value):
        key = match.group(1)
        if key not in SUBSTITUTION_KEYS:
            errors.append(
                f"{where}: unknown substitution '{{{key}}}' "
                f"(valid: {', '.join('{{' + k + '}}' for k in SUBSTITUTION_KEYS)})"
            )


# ── Validation ─────────────────────────────────────────────────────────────

def _check_search_types(scope: Dict[str, Any], where: str,
                        errors: List[str]) -> None:
    """Light type checks for the search-kwarg keys inside *scope*."""
    for key in sorted(set(scope) & STEP_SEARCH_KEYS):
        value = scope[key]
        if key in _INT_SEARCH_KEYS:
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                errors.append(f"{where}.{key}: must be an integer >= 0")
        elif key in _FLOAT_SEARCH_KEYS:
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
                errors.append(f"{where}.{key}: must be a number >= 0")
        elif key in _BOOL_SEARCH_KEYS:
            if not isinstance(value, bool):
                errors.append(f"{where}.{key}: must be true or false")
        elif key in _STR_SEARCH_KEYS:
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{where}.{key}: must be a non-empty string")
        elif key == "fallback_chain":
            if isinstance(value, str):
                continue
            if not (isinstance(value, list) and all(isinstance(v, str) for v in value)):
                errors.append(f"{where}.{key}: must be a string or list of strings")


def _check_worker_overrides(ov: Any, where: str, errors: List[str]) -> None:
    if ov is None:
        return
    if not isinstance(ov, dict):
        errors.append(f"{where}: must be a mapping of search kwargs")
        return
    unknown = set(ov) - STEP_SEARCH_KEYS
    if unknown:
        errors.append(
            f"{where}: unknown search key(s): {', '.join(sorted(unknown))} "
            f"(valid: {', '.join(sorted(STEP_SEARCH_KEYS))})"
        )
    _check_search_types(ov, where, errors)


def _step_name(step: Dict[str, Any], index: int) -> str:
    """Step name, defaulting to ``step-<n>`` (1-based)."""
    name = step.get("name") if isinstance(step, dict) else None
    return str(name).strip() if isinstance(name, str) and name.strip() else f"step-{index + 1}"


def validate_workflow(name: str, definition: Any,
                      target: Optional[str] = None) -> List[str]:
    """Full validation of one workflow definition.

    Returns a list of error strings (empty = valid). Errors are prefixed with
    ``workflows.<name>`` and carry step paths like ``steps[2]`` so they are
    directly actionable.
    """
    errors: List[str] = []

    def err(path: str, message: str) -> None:
        prefix = f"workflows.{name}" + (f".{path}" if path else "")
        errors.append(f"{prefix}: {message}")

    if not isinstance(definition, dict):
        err("", "workflow must be a mapping")
        return errors

    unknown = set(definition) - _WORKFLOW_KEYS
    if unknown:
        err("", f"unknown key(s): {', '.join(sorted(unknown))} "
                f"(valid: {', '.join(sorted(_WORKFLOW_KEYS))})")

    _check_search_types(definition, f"workflows.{name}", errors)
    _check_worker_overrides(definition.get("worker_overrides"),
                            f"workflows.{name}.worker_overrides", errors)

    workers = definition.get("workers")
    if workers is not None and (
            not isinstance(workers, int) or isinstance(workers, bool)
            or not 1 <= workers <= 64):
        err("workers", "must be an integer between 1 and 64")

    wf_on_error = definition.get("on_error")
    if wf_on_error is not None and wf_on_error not in _ON_ERROR_VALUES:
        err("on_error", f"must be one of: {', '.join(_ON_ERROR_VALUES)}")

    steps = definition.get("steps")
    if not isinstance(steps, list) or not steps:
        err("steps", "must be a non-empty list")
        return errors

    effective_target = target or definition.get("target")
    uses_target = False
    seen_names = set()

    for idx, step in enumerate(steps):
        where = f"steps[{idx}]"
        if not isinstance(step, dict):
            err(where, "must be a mapping")
            continue

        unknown = set(step) - _STEP_KEYS
        if unknown:
            err(where, f"unknown key(s): {', '.join(sorted(unknown))}")

        sname = _step_name(step, idx)
        if sname in seen_names:
            err(where, f"duplicate step name '{sname}'")
        seen_names.add(sname)

        _check_search_types(step, f"workflows.{name}.{where}", errors)
        _check_worker_overrides(step.get("worker_overrides"),
                                f"workflows.{name}.{where}.worker_overrides", errors)

        query = step.get("query")
        queries = step.get("queries")
        if query is None and queries is None:
            err(where, "requires 'query' or 'queries'")
        if query is not None and queries is not None:
            err(where, "'query' and 'queries' are mutually exclusive")
        if query is not None and (not isinstance(query, str) or not query.strip()):
            err(where, "query must be a non-empty string")
        if queries is not None and (
                not isinstance(queries, list) or not queries
                or not all(isinstance(q, str) and q.strip() for q in queries)):
            err(where, "queries must be a non-empty list of strings")

        step_strings: List[str] = []
        if isinstance(query, str):
            step_strings.append(query)
        if isinstance(queries, list):
            step_strings.extend(q for q in queries if isinstance(q, str))

        when = step.get("when_results_below")
        if when is not None and (
                not isinstance(when, int) or isinstance(when, bool) or when < 0):
            err(where, "when_results_below must be an integer >= 0")

        retry = step.get("retry_with")
        if retry is not None:
            if when is None:
                err(where, "retry_with requires when_results_below")
            if not isinstance(retry, list) or not retry or not all(
                    isinstance(q, str) and q.strip() for q in retry):
                err(where, "retry_with must be a non-empty list of strings")
            elif isinstance(retry, list):
                step_strings.extend(retry)

        step_on_error = step.get("on_error") or wf_on_error or "stop"
        if step_on_error not in _ON_ERROR_VALUES:
            err(where, f"on_error must be one of: {', '.join(_ON_ERROR_VALUES)}")

        outputs = step.get("outputs")
        if outputs is not None:
            if not isinstance(outputs, list):
                err(where, "outputs must be a list")
            else:
                for oi, out in enumerate(outputs):
                    owhere = f"{where}.outputs[{oi}]"
                    if not isinstance(out, dict):
                        err(owhere, "must be a mapping with 'file' (+ optional 'format')")
                        continue
                    extra = set(out) - {"file", "format"}
                    if extra:
                        err(owhere, f"unknown key(s): {', '.join(sorted(extra))}")
                    file_expr = out.get("file")
                    if not isinstance(file_expr, str) or not file_expr.strip():
                        err(owhere, "'file' is required (relative paths resolve "
                                    "inside the environment root / CWD)")
                    fmt = out.get("format")
                    if fmt is not None and fmt not in OUTPUT_FORMATS:
                        err(owhere, f"format must be one of: {', '.join(sorted(OUTPUT_FORMATS))}")

        for text in step_strings:
            _check_tokens(text, f"workflows.{name}.{where}", errors)
            if "{target}" in text:
                uses_target = True

    for key in ("description",):
        value = definition.get(key)
        if value is not None and not isinstance(value, str):
            err(key, "must be a string")

    target_value = definition.get("target")
    if target_value is not None and (not isinstance(target_value, str) or not target_value.strip()):
        err("target", "must be a non-empty string")

    if uses_target and not (isinstance(effective_target, str) and effective_target.strip()):
        err("target", "queries use {target} but no workflow-level 'target' "
                      "is set (set one or pass --target)")

    return errors


# ── Discovery & loading ────────────────────────────────────────────────────

def discover_workflow_files(workspace=None, cwd: Optional[os.PathLike] = None) -> List[Path]:
    """Find workflow files in the CWD and the environment root.

    CWD files come first and the environment root's files are appended last:
    when merged by :func:`collect_workflows` (later wins), the workspace
    definition therefore takes precedence over the CWD on name collisions —
    mirroring the config layer order (env > CWD). The same file reached
    through both roots is only returned once.
    """
    roots: List[Path] = [Path(cwd) if cwd is not None else Path.cwd()]
    if workspace is not None:
        roots.append(Path(getattr(workspace, "root", workspace)))

    found: List[Path] = []
    seen = set()
    for root in roots:
        for filename in WORKFLOW_FILENAMES:
            path = root / filename
            try:
                key = path.resolve()
            except OSError:  # pragma: no cover — unresolvable path
                key = path
            if path.is_file() and key not in seen:
                seen.add(key)
                found.append(path)
    return found


def load_workflow_file(path: os.PathLike) -> Dict[str, Any]:
    """Load a standalone workflow YAML file → ``{name: definition}``.

    Accepts either a top-level ``workflows:`` mapping (config-compatible) or a
    bare ``name: {steps: [...]}`` mapping. Raises :class:`WorkflowError` on
    missing file, invalid YAML, or wrong shape.
    """
    path = Path(path)
    if not path.is_file():
        raise WorkflowError(f"Workflow file not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise WorkflowError(f"Invalid YAML in {path}: {e}") from e
    except OSError as e:
        raise WorkflowError(f"Cannot read {path}: {e}") from e

    if data is None:
        raise WorkflowError(f"{path}: file is empty")

    if isinstance(data, dict) and "workflows" in data:
        workflows = data["workflows"]
    elif isinstance(data, dict) and data and all(
            isinstance(v, dict) and "steps" in v for v in data.values()):
        workflows = data
    else:
        raise WorkflowError(
            f"{path}: missing top-level 'workflows:' mapping "
            f"(expected `workflows:\\n  <name>:\\n    steps: [...]`)"
        )

    if not isinstance(workflows, dict) or not workflows:
        raise WorkflowError(f"{path}: 'workflows' must be a non-empty mapping")
    return workflows


def collect_workflows(
    files: Optional[List[os.PathLike]] = None,
    config_workflows: Any = None,
) -> Dict[str, Tuple[Any, str]]:
    """Merge workflow definitions from config layers and files.

    Returns ``{name: (definition, source)}``; definitions from files override
    same-named ones from config (explicit file > config layer).
    """
    merged: Dict[str, Tuple[Any, str]] = {}
    if isinstance(config_workflows, dict):
        for name, definition in config_workflows.items():
            merged[str(name)] = (definition, "config")
    for file_path in files or []:
        for name, definition in (load_workflow_file(file_path) or {}).items():
            merged[str(name)] = (definition, str(file_path))
    return merged


# ── Persistent run state ───────────────────────────────────────────────────

class WorkflowRun:
    """Per-workflow state (JSON) that makes ``--resume`` possible."""

    def __init__(self, name: str, state_path: os.PathLike,
                 data: Optional[Dict[str, Any]] = None):
        self.name = name
        self.state_path = Path(state_path)
        self.data: Dict[str, Any] = data if isinstance(data, dict) else {}
        self.data.setdefault("name", name)
        self.data.setdefault("run_id", uuid.uuid4().hex[:12])
        self.data.setdefault("started_at",
                             datetime.now().isoformat(timespec="seconds"))
        self.data.setdefault("steps", {})
        self.data.setdefault("status", "running")

    @property
    def run_id(self) -> str:
        return str(self.data.get("run_id", ""))

    @classmethod
    def load(cls, name: str, state_path: os.PathLike) -> "WorkflowRun":
        """Load saved state; a missing or corrupt file starts fresh."""
        path = Path(state_path)
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = None
            if isinstance(data, dict) and isinstance(data.get("steps"), dict):
                return cls(name, path, data)
            logger.warning("Corrupt workflow state at %s — starting fresh.", path)
        return cls(name, path)

    def step_status(self, step_name: str) -> Optional[str]:
        record = self.data["steps"].get(step_name)
        return record.get("status") if isinstance(record, dict) else None

    def mark_step(self, step_name: str, record: Dict[str, Any]) -> None:
        self.data["steps"][step_name] = record
        self.data["updated_at"] = datetime.now().isoformat(timespec="seconds")

    def save(self) -> None:
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self.state_path.write_text(
                json.dumps(self.data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as e:
            logger.warning("Cannot save workflow state to %s: %s",
                           self.state_path, e)


# ── Engine ─────────────────────────────────────────────────────────────────

class WorkflowEngine:
    """Execute one workflow definition: sequential steps, threshold retries,
    worker concurrency inside a step, guarded outputs, resumable state."""

    def __init__(self, name: str, definition: Dict[str, Any], *,
                 target: Optional[str] = None,
                 workers: Optional[int] = None,
                 workspace=None,
                 console=None,
                 cache=None,
                 case_modules: Optional[Dict] = None):
        self.name = name
        self.definition = definition if isinstance(definition, dict) else {}
        self.workspace = workspace
        self.console = console
        self.cache = cache
        self.target = (target if target is not None
                       else self.definition.get("target"))
        wf_workers = self.definition.get("workers")
        self.workers = int(workers or wf_workers or 1)
        self.case_modules = (case_modules if case_modules is not None
                             else self._build_case_modules())

    # ── helpers ────────────────────────────────────────────────────────

    def _say(self, message: str) -> None:
        if self.console is not None:
            self.console.print(message)
        else:
            logger.info("%s", re.sub(r"\[/?[a-z ]+\]", "", message))

    def context(self, step: str = "", run_id: str = "") -> Dict[str, str]:
        """Substitution context for this run."""
        return {
            "target": str(self.target or ""),
            "step": step,
            "date": datetime.now().strftime("%Y%m%d"),
            "run_id": run_id,
        }

    def validate(self) -> List[str]:
        return validate_workflow(self.name, self.definition, target=self.target)

    def state_file(self) -> Path:
        """``<env>/state/workflows/<name>.json`` — or ``~/.atdork/state/...``."""
        if self.workspace is not None:
            base = Path(self.workspace.state_dir) / "workflows"
        else:
            base = Path.home() / ".atdork" / "state" / "workflows"
        safe = re.sub(r"[^\w.-]", "_", self.name)
        return base / f"{safe}.json"

    def resolved_queries(self, step: Dict[str, Any], ctx: Dict[str, str]
                         ) -> Tuple[List[str], List[str]]:
        """Substituted ``(primary_queries, retry_queries)`` for one step."""
        if step.get("query") is not None:
            primary = [substitute(str(step["query"]), ctx)]
        else:
            primary = [substitute(str(q), ctx) for q in (step.get("queries") or [])]
        retry = [substitute(str(q), ctx)
                 for q in (step.get("retry_with") or [])]
        return primary, retry

    def _sub_value(self, value: Any, ctx: Dict[str, str]) -> Any:
        if isinstance(value, str):
            return substitute(value, ctx)
        if isinstance(value, list):
            return [self._sub_value(v, ctx) for v in value]
        return value

    def _step_kwargs(self, step: Dict[str, Any], ctx: Dict[str, str]) -> Dict[str, Any]:
        """Merged search kwargs: workflow defaults → step → worker_overrides."""
        kwargs = {k: v for k, v in self.definition.items() if k in STEP_SEARCH_KEYS}
        kwargs.update({k: v for k, v in step.items() if k in STEP_SEARCH_KEYS})
        overrides = step.get("worker_overrides")
        if not isinstance(overrides, dict):
            overrides = self.definition.get("worker_overrides")
        if isinstance(overrides, dict):
            kwargs.update({k: v for k, v in overrides.items()
                           if k in STEP_SEARCH_KEYS})
        return {k: self._sub_value(v, ctx) for k, v in kwargs.items()}

    def _build_case_modules(self) -> Dict[str, Any]:
        """Resilience modules mirroring ``--resilient`` defaults."""
        resilience = get_setting("resilience")
        if not isinstance(resilience, dict):
            resilience = {}
        cb_cfg = resilience.get("circuit_breaker")
        if not isinstance(cb_cfg, dict):
            cb_cfg = {}
        try:
            threshold = int(cb_cfg.get("failure_threshold", 3))
            cooldown = float(resilience.get("cooldown",
                                            cb_cfg.get("reset_timeout", 120.0)))
        except (TypeError, ValueError):
            threshold, cooldown = 3, 120.0
        circuit = CircuitBreaker(threshold=threshold, cooldown=cooldown)

        chain: List[str] = []
        search_cfg = get_setting("search")
        if isinstance(search_cfg, dict):
            raw_chain = search_cfg.get("fallback")
            if isinstance(raw_chain, str):
                chain = [b.strip() for b in raw_chain.split(",") if b.strip()]
            elif isinstance(raw_chain, list):
                chain = [str(b).strip() for b in raw_chain if str(b).strip()]

        try:
            retries = int(self.definition.get("retries")
                          or get_setting("retries") or 2)
        except (TypeError, ValueError):
            retries = 2

        return {
            "circuit_breaker": circuit,
            "fallback_manager": FallbackManager(
                backends=chain or list(_LEGACY_BACKENDS),
                circuit_breaker=circuit,
            ),
            "retry_handler": RetryHandler(max_retries=retries, base_delay=2.0),
        }

    @staticmethod
    def _dedupe(*groups: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
        """Merge result groups, keeping the first hit per href/url/title."""
        seen = set()
        out: List[Dict[str, Any]] = []
        for group in groups:
            for res in group or []:
                if isinstance(res, dict):
                    key = (res.get("href") or res.get("url")
                           or (str(res.get("title", "")),
                               str(res.get("snippet", res.get("body", "")))))
                else:
                    key = str(res)
                if key in seen:
                    continue
                seen.add(key)
                out.append(res)
        return out

    # ── outputs ────────────────────────────────────────────────────────

    def _write_outputs(self, step: Dict[str, Any], results: List[Dict[str, Any]],
                       ctx: Dict[str, str], label: str) -> List[str]:
        written: List[str] = []
        for out in step.get("outputs") or []:
            file_expr = substitute(str(out.get("file", "")), ctx)
            path = Path(file_expr)
            if not path.is_absolute():
                base = (Path(self.workspace.results_dir) if self.workspace is not None
                        else Path.cwd())
                path = base / path
            fmt = out.get("format")
            if not fmt:
                ext = path.suffix.lower().lstrip(".")
                fmt = ext if ext in OUTPUT_FORMATS else "txt"
            if self.workspace is not None:
                try:
                    path = Path(self.workspace.guard_write(str(path)))
                except (EnvEscapeError, EnvError) as e:
                    raise WorkflowError(
                        f"output path escapes the environment root: {file_expr} ({e})"
                    ) from e
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                save_results(results, query=label, output_path=str(path),
                             output_format=fmt)
            except (OSError, ValueError) as e:
                raise WorkflowError(f"cannot write output {path}: {e}") from e
            written.append(str(path))
            self._say(f"    [dim]→ saved {len(results)} results → {path}[/dim]")
        return written

    # ── step execution ─────────────────────────────────────────────────

    def _execute_step(self, step: Dict[str, Any], ctx: Dict[str, str]) -> Dict[str, Any]:
        primary, retry = self.resolved_queries(step, ctx)
        kwargs = self._step_kwargs(step, ctx)
        label = f"[{ctx['step']}]"

        success_flags: List[bool] = []

        def _on_done(query: str, results: list, success: bool) -> None:
            success_flags.append(bool(success))

        self._say(f"  [cyan]Step[/cyan] {ctx['step']}: "
                  f"{len(primary)} quer{'y' if len(primary) == 1 else 'ies'}")
        results_map = run_batch(
            primary,
            case_modules=self.case_modules,
            concurrency=self.workers,
            cache=self.cache,
            on_query_done=_on_done,
            **kwargs,
        )
        merged = self._dedupe(*results_map.values())
        if primary and not any(success_flags):
            raise WorkflowError(
                f"all {len(primary)} queries failed for step '{ctx['step']}' "
                f"(backend errors exhausted — see log)"
            )

        threshold = step.get("when_results_below")
        below = isinstance(threshold, int) and len(merged) < threshold
        if below and retry:
            self._say(f"    [yellow]below threshold[/yellow] "
                      f"({len(merged)} < {threshold}) → {len(retry)} retry "
                      f"quer{'y' if len(retry) == 1 else 'ies'}")
            retry_success: List[bool] = []

            def _on_retry_done(query: str, results: list, success: bool) -> None:
                retry_success.append(bool(success))

            retry_map = run_batch(
                retry,
                case_modules=self.case_modules,
                concurrency=self.workers,
                cache=self.cache,
                on_query_done=_on_retry_done,
                **kwargs,
            )
            merged = self._dedupe(merged, *retry_map.values())
            if retry and not any(retry_success):
                self._say("    [yellow]all retry queries failed[/yellow]")
            below = len(merged) < threshold

        outputs = self._write_outputs(step, merged, ctx, label)
        status = "below_threshold" if below else "done"
        if below:
            self._say(f"    [yellow]step finished below threshold[/yellow] "
                      f"({len(merged)} < {threshold} unique results)")
        else:
            self._say(f"  [green]✓ {ctx['step']}[/green]: {len(merged)} unique results")
        return {
            "status": status,
            "results": len(merged),
            "queries": primary,
            "retry_queries": retry if below else [],
            "below_threshold": below,
            "outputs": outputs,
            "finished_at": datetime.now().isoformat(timespec="seconds"),
        }

    # ── full run ───────────────────────────────────────────────────────

    def run(self, *, resume: bool = False, only_step: Optional[str] = None,
            dry_run: bool = False) -> Dict[str, Any]:
        """Run the workflow; returns a summary dict.

        Raises :class:`WorkflowError` when the definition is invalid or an
        ``only_step`` filter names an unknown step.
        """
        errors = self.validate()
        if errors:
            raise WorkflowError(
                f"Invalid workflow '{self.name}':\n  - " + "\n  - ".join(errors)
            )

        full_steps = [(_step_name(s, i), s)
                      for i, s in enumerate(self.definition.get("steps") or [])]
        if only_step is not None:
            known = [n for n, _ in full_steps]
            if only_step not in known:
                raise WorkflowError(
                    f"Unknown step '{only_step}' in workflow '{self.name}' "
                    f"(steps: {', '.join(known)})"
                )
            full_steps = [(n, s) for n, s in full_steps if n == only_step]

        state_path = self.state_file()
        if resume:
            state = WorkflowRun.load(self.name, state_path)
        else:
            state = WorkflowRun(self.name, state_path)
            state.data["steps"] = {}
            if not dry_run:
                state.save()

        summary: Dict[str, Any] = {
            "name": self.name,
            "run_id": state.run_id,
            "target": self.target,
            "status": "completed",
            "steps": [],
            "total_results": 0,
            "dry_run": dry_run,
            "state_file": str(state_path),
        }
        self._say(f"[bold]Workflow[/bold] {self.name} "
                  f"(run {state.run_id}, {len(full_steps)} step(s), "
                  f"{self.workers} worker(s))")

        for sname, step in full_steps:
            ctx = self.context(step=sname, run_id=state.run_id)

            if dry_run:
                primary, retry = self.resolved_queries(step, ctx)
                self._say(f"  [dim](dry-run)[/dim] {sname}:")
                for query in primary:
                    self._say(f"    [dim]▶ {query}[/dim]")
                for query in retry:
                    self._say(f"    [dim]↳ retry: {query}[/dim]")
                summary["steps"].append({
                    "name": sname, "status": "planned",
                    "queries": primary, "retry_with": retry,
                })
                continue

            if resume and state.step_status(sname) in ("done", "below_threshold"):
                previous = state.data["steps"].get(sname) or {}
                self._say(f"  [dim]↷ {sname} already "
                          f"{previous.get('status', 'done')} — skipped (resume)[/dim]")
                skipped = dict(previous)
                skipped["name"] = sname
                skipped["skipped"] = True
                summary["steps"].append(skipped)
                summary["total_results"] += int(previous.get("results", 0) or 0)
                continue

            try:
                record = self._execute_step(step, ctx)
            except WorkflowError as e:
                record = {
                    "status": "failed", "error": str(e), "results": 0,
                    "finished_at": datetime.now().isoformat(timespec="seconds"),
                }
            except Exception as e:  # unexpected — record, honor on_error
                logger.exception("Workflow step '%s' crashed", sname)
                record = {
                    "status": "failed", "error": f"{type(e).__name__}: {e}",
                    "results": 0,
                    "finished_at": datetime.now().isoformat(timespec="seconds"),
                }

            record["name"] = sname
            summary["steps"].append(record)
            summary["total_results"] += int(record.get("results", 0) or 0)
            state.mark_step(sname, record)
            state.save()

            if record["status"] == "failed":
                on_error = (step.get("on_error")
                            or self.definition.get("on_error") or "stop")
                if on_error != "continue":
                    summary["status"] = "failed"
                    self._say(f"  [red]✗ {sname} failed[/red]: "
                              f"{record.get('error', 'unknown error')} — stopping "
                              f"(on_error: stop; use --resume to continue later)")
                    break
                self._say(f"  [red]✗ {sname} failed[/red]: "
                          f"{record.get('error', 'unknown error')} — continuing "
                          f"(on_error: continue)")

        state.data["status"] = summary["status"]
        state.data["finished_at"] = datetime.now().isoformat(timespec="seconds")
        if not dry_run:
            state.save()
        return summary


# ── Convenience for the CLI layer ──────────────────────────────────────────

def run_workflow(
    name: str,
    definition: Dict[str, Any],
    *,
    target: Optional[str] = None,
    workers: Optional[int] = None,
    workspace=None,
    console=None,
    cache=None,
    resume: bool = False,
    only_step: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """One-shot helper: build an engine for *definition* and run it."""
    engine = WorkflowEngine(
        name, definition, target=target, workers=workers,
        workspace=workspace, console=console, cache=cache,
    )
    return engine.run(resume=resume, only_step=only_step, dry_run=dry_run)
