# Plugins

**Plugins** extend AtDork with new commands without touching the core: a
plugin is a single Python file that declares a `PLUGIN` metadata dictionary
and a `run()` entry point. Installed through the package manager, every plugin
option surfaces on the main CLI using the **mandatory `--<plugin>-<option>`
flag format**, so plugin flags can never collide with core flags or with each
other.

```bash
atdork install @plugins/dorkbuilder
atdork --dorkbuilder-text "John wick" \
       --dorkbuilder-type social-media \
       --dorkbuilder-save dorks.txt
```

```text
▶ plugin dorkbuilder (~/.atdork/packages/plugins/dorkbuilder/dorkbuilder.py)
10 dork(s) for "John wick" [category: social-media]
  • site:linkedin.com/in "John wick"
  • site:twitter.com "John wick" OR site:x.com "John wick"
  ...
✔ saved 10 dorks → dorks.txt
```

---

## The plugin contract

A plugin is a `.py` file with one top-level `PLUGIN` literal dictionary and a
`run(args, ctx)` function:

```python
PLUGIN = {
    "name": "dorkbuilder",              # becomes the --dorkbuilder trigger
    "version": "1.0.0",
    "description": "Build ready-to-run dork lists from text + a category",
    "options": [
        {"name": "text", "help": "Text to hunt for"},
        {"name": "type", "choices": ["social-media", "all"],
         "default": "social-media"},
        {"name": "limit", "type": "int", "default": 0},
        {"name": "list-types", "action": "store_true"},
    ],
}

def run(args, ctx) -> int:
    text = args.dorkbuilder_text        # dest: <plugin>_<option>
    return 0
```

### Mandatory flag format

Option names are declared in **short form** (`"text"`); the engine always
registers them as `--<plugin>-<option>` (`--dorkbuilder-text`). A full flag
whose prefix does not match `--<plugin>-` is rejected at registration and the
plugin is reported as invalid. Dests are always `<plugin>_<option>` with dashes
flipped to underscores (`func-lain` → `--dorkbuilder-func-lain` →
`dorkbuilder_func_lain`), so a plugin can never shadow a core flag.

### `PLUGIN` keys

| Key | Required | Meaning |
| :--- | :--- | :--- |
| `name` | yes | Matches `^[a-z][a-z0-9_-]{1,30}$`; becomes the trigger flag. |
| `version` | no | Shown by `plugins list` / `plugins info`. |
| `description` | no | Help text for the trigger flag. |
| `options` | no | List of option mappings (below). |

### Option keys

| Key | Meaning |
| :--- | :--- |
| `name` | Short name (`[a-z][a-z0-9_-]*`), auto-prefixed to `--<plugin>-<name>`. |
| `help` | Help text for the flag. |
| `type` | `str` (default), `int`, or `float`. |
| `choices` | Non-empty list of allowed string values. |
| `default` | Default value when the flag is absent. |
| `action` | `"store_true"` for a boolean switch (no `type`/`choices`). |

---

## How a plugin runs

A plugin is triggered by **either**:

1. the bare flag `--<plugin>` (`store_true`), **or**
2. implicitly, when **any** `--<plugin>-*` argument appears on the command
   line.

Configuration defaults alone (`plugins.options`) never launch a plugin — only
real command-line arguments do. Every triggered plugin runs in order and the
first non-zero exit code wins.

```bash
atdork --dorkbuilder-list-types               # implicit: one option is enough
atdork --dorkbuilder --dorkbuilder-text "x"   # explicit trigger + option
```

Metadata is read with `ast.literal_eval` — listing and registering plugins
**never executes plugin code**. A plugin module is imported and run only when
it is actually triggered.

---

## `ctx`: what a plugin gets

`run(args, ctx)` receives the parsed namespace plus a `PluginContext`:

| Attribute / method | Purpose |
| :--- | :--- |
| `ctx.console` | Rich console for output. |
| `ctx.workspace` | Active environment, or `None`. |
| `ctx.package_dir` | Local package store directory. |
| `ctx.version` | AtDork version string. |
| `ctx.results_dir` | Environment results directory (or CWD). |
| `ctx.get_setting(key, default)` | Read a configuration value. |
| `ctx.guard_write(path)` | Resolve an output path through the environment write guard. |
| `ctx.search(query, **kwargs)` | Run one dork search through the normal AtDork engine. |

Always write files through `ctx.guard_write()` — it enforces the active
environment root and rejects paths that escape it.

---

## CLI

### `atdork plugins list`

Every discovered plugin with its version, status (`ready`, `disabled`, or
`invalid` with the contract error), trigger flag, option count, and path.

### `atdork plugins info <name>`

The full contract: version, description, source, path, install ref, status,
and a table of every flag with its dest, type, default, and choices.

### `atdork plugins run <name> [--opt KEY=VALUE]`

Run a plugin without the flag syntax. Each `--opt` is coerced using the
option's declared type. Handy for scripting:

```bash
atdork plugins run dorkbuilder --opt text=Acme --opt limit=3 --opt save=acme.txt
```

---

## Where plugins live

Discovery scans (later roots override earlier ones on a name collision):

1. the package store `<store>/plugins/` — populated by
   `atdork install @plugins/<tool>`;
2. every folder listed in `plugins.paths` in your
   [configuration](../configuration.md) (handy for local development).

A tool folder (`@plugins/<tool>/`) may contain helper `_*.py` files; only files
with a valid `PLUGIN` literal become commands, and the rest are installed as
supporting modules.

---

## Configuration

```yaml
version: 2
plugins:
  enabled: auto          # "auto" (all installed) or an explicit allow-list
  disabled: []           # plugin names to keep quiet
  paths: []              # extra local folders to scan
  options:               # per-plugin option defaults (CLI still wins)
    dorkbuilder:
      type: social-media
```

`enabled` accepts `"auto"` (default) or a list of names; `disabled` always
wins. The section is validated fail-fast on load — unknown keys, wrong types,
and malformed option defaults are rejected before anything runs. API keys and
secrets are never stored in plaintext.

---

## Installing plugins

Plugins ship in the [Atdork-DB](https://github.com/amnottdevv/Atdork-DB)
repository under `@plugins/`:

```bash
atdork search dorkbuilder                 # find it
atdork install @plugins/dorkbuilder       # whole tool folder (plugin + helpers)
atdork install @plugins/dorkbuilder/dorkbuilder.py   # a single file
atdork plugins list                      # verify it's ready
```

### Available plugins

| Plugin | What it does |
|---|---|
| `dorkbuilder` | Build ready-to-run dork lists from text + a category |
| `reportgen` | Summarize result files into an HTML/JSON report |
| `subdomain` | Discover indexed subdomains of a target via search dorks |
| `emaildork` | Build (and optionally run) email-discovery dorks |
| `vulndork` | Vulnerability-hunting dork sets by target / product / CVE |
| `geodork` | Geographically-scoped dork builder |
| `usernamehunt` | Find where a username/handle is used across the web |

Each tool ships with its own `README.md`. Browse them — with rendered
READMEs, options and source links — in the
[web catalog's Plugins section](https://amnottdevv.github.io/Atdork-DB/#/plugins).

---

## Security

Plugin metadata is parsed with `ast.literal_eval` — reading `PLUGIN` never
executes code, so listing or registering plugins is side-effect free. A plugin
module is imported **only** when one of its flags is actually triggered on the
command line.

Because a triggered plugin is real Python that runs in your interpreter, the
trust model is the package manager: only install plugins from a repository you
trust (`atdork install` verifies the `sha256` of every file against
`Index.idn`). Treat installing a plugin like installing any other package.

Output writing goes through `ctx.guard_write()`, which enforces the active
environment root — a plugin cannot write outside its workspace through the
guarded path. Invalid plugins (bad metadata, wrong prefix, missing `run()`) are
rejected at load time and reported by `plugins list`, never silently ignored.

Disable a plugin without uninstalling it via `plugins.disabled` in the
configuration.
