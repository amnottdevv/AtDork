# Configuration (atdork.yml)

AtDork can be configured with YAML files instead of long CLI flag chains.
The loader understands **schema v2**: nested sections for search behaviour,
API engines, profiles, resilience tuning and output — while every legacy
flat key from schema v1 keeps working unchanged.

A ready-to-copy example lives at
[`examples/atdork.yml`](https://github.com/amnottdevv/AtDork/blob/master/examples/atdork.yml).

---

## Where config files are read from

Discovery is **layered** — every file that exists is loaded and merged,
lowest precedence first:

| # | Layer | Location |
|---|-------|----------|
| 1 | Built-in defaults | (compiled into AtDork) |
| 2 | Global file | `~/.config/atdork/config.yml` (or `.yaml` / `atdork.yml` / `atdork.yaml` — first match wins) |
| 3 | Working directory | `./atdork.yaml` or `./AtDork.yaml` or `./atdork.yml` (first match wins) |
| 4 | Explicit file | `--config path/to/atdork.yml` (or env `ATDORK_CONFIG` when `--config` is absent) |
| 5 | Environment | `ATDORK_<KEY>` variables (flat keys only) |
| 6 | CLI flags | always win |

A single `--config` file therefore *overrides* the CWD file, which overrides
the global file, which overrides the defaults — for every key each layer sets.

```bash
atdork -q "inurl:admin" --config ./team-config.yml   # ./team-config.yml wins over all files
ATDORK_CONFIG=~/.config/atdork/config.yml atdork -q "test"
```

---

## Complete example

```yaml
# atdork.yml — schema v2
version: 2

# ── Search behaviour ─────────────────────────────────────────────
search:
  max_results: 30              # 1–100
  region: "us-en"              # <country>-<language>
  safesearch: "moderate"       # on | moderate | off
  timelimit: null              # d | w | m | y | null
  backend: "auto"              # auto, google, serper, a profile name, ...
  fallback:                    # explicit fallback chain (see engines.md)
    - google
    - serper
    - brave
  timeout: 10
  retries: 2
  delay: 0.0
  concurrency: 4

# ── Third-party search APIs (see engines.md) ────────────────────
engines:
  serper:
    type: api
    api_key: ${SERPER_API_KEY} # resolved from the environment — never a literal
    qps: 1                     # local rate limit, requests per second (0 = off)
  serpapi:
    type: api
    api_key: ${SERPAPI_KEY}
    qps: 1
  brave:
    type: api
    api_key: ${BRAVE_API_KEY}
    qps: 1

# ── Named backend chains: --backend resilient ───────────────────
profiles:
  resilient: [google, serper, brave]
  cheap: [duckduckgo, mojeek]  # scraping only, no API credits

# ── Resilience tuning (used with --resilient) ───────────────────
resilience:
  circuit_breaker:
    failure_threshold: 5       # failures before the breaker opens (default 3)
    reset_timeout: 90          # seconds before the breaker tries again
  cooldown: 90                 # overrides reset_timeout if both are set

# ── Output ──────────────────────────────────────────────────────
output:
  format: json                 # txt | json | csv
  dir: ./results               # alias: output_dir
  no_snippet: false
```

---

## Section reference

### `search:`

Search knobs. Every key here **overrides** the same key written at the file
root (legacy style) or the built-in default.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `max_results` | int | `20` | Results per query (1–100). |
| `region` | str | `us-en` | `<country>-<language>` region code. |
| `safesearch` | str | `moderate` | `on`, `moderate`, `off`. |
| `timelimit` | str/null | `null` | `d`, `w`, `m`, `y`. |
| `backend` | str | `auto` | Backend, comma list, API engine, or profile name. |
| `fallback` | list/str | *(ddgs default chain)* | Explicit fallback order, e.g. `[google, serper, brave]`. Replaces the built-in chain; also feeds `--resilient`. |
| `timeout` | int | `10` | Per-attempt timeout (seconds). |
| `retries` | int | `2` | Retries per backend. |
| `delay` | float | `0.0` | Delay between requests (seconds). |
| `user_agent` | str/null | `null` | `null` = auto-rotate. |
| `proxy` / `proxy_file` | str/null | `null` | Proxy URL(s) or file. |
| `tor` | bool | `false` | Enable Tor fallback. |
| `strict` | bool | `false` | Fail instead of falling back to direct. |
| `proxy_cooldown` | int | `60` | Seconds before a banned proxy is retried. |
| `max_failures` | int | `3` | Consecutive failures before permanent proxy removal. |
| `concurrency` | int | `1` | Worker threads. |
| `batch_separator` | str | `;` | Separator for inline multi-query strings. |
| `resilient` | bool | `false` | Same as `--resilient`. |
| `adaptive_delay` | bool | `false` | Same as `--adaptive-delay`. |
| `no_fallback_backends` | bool | `false` | Same as `--no-fallback-backends`. |

### `engines:`

Third-party search APIs keyed by engine name. Full guide:
[Engines & Providers](engines.md).

```yaml
engines:
  serper:
    type: api                  # only supported type
    api_key: ${SERPER_API_KEY}
    qps: 1.0
    timeout: 10
    # provider-specific options: engine, gl, hl, location, country, ...
```

A configured name **overrides** a built-in scraping backend of the same name
— `engines.brave` makes `--backend brave` use the official Brave Search API.

### `profiles:`

Named backend chains usable as `--backend <name>`:

```yaml
profiles:
  resilient: [google, serper, brave]
```

```bash
atdork -q "inurl:admin" --backend resilient
```

A profile is an *explicit* choice, so it is honoured even with
`--no-fallback-backends`. Entries may include API engines.

### `resilience:`

Applied when `--resilient` (or `search.resilient: true`) is active:

| Key | Default | Description |
|-----|---------|-------------|
| `circuit_breaker.failure_threshold` | `3` | Failures before the circuit opens. |
| `circuit_breaker.reset_timeout` | `120` | Seconds before the breaker half-opens. |
| `cooldown` | *(unset)* | Cooldown in seconds; overrides `reset_timeout` when both are set. |

### `output:`

| Key | Maps to | Description |
|-----|---------|-------------|
| `format` | `format` | `txt`, `json`, `csv`. |
| `dir` / `output_dir` | `output_dir` | Default results directory. |
| `no_snippet` | `no_snippet` | Hide snippets in terminal output. |

### `workflows`

Reserved for the workflow engine (sequential multi-step runs). Accepted and
validated as a mapping, not yet executed.

---

## Environment variable interpolation

Any YAML **string value** may reference the environment:

```yaml
engines:
  serper:
    api_key: ${SERPER_API_KEY}          # must be set, or config load fails
proxy: socks5://${PROXY_USER}:${PROXY_PASS}@10.0.0.1:9050
user_agent: ${USER_AGENT:-AtDork/1.4}   # ${VAR:-default} — default when unset
```

Rules:

- `${VAR}` — expanded from the environment. **In `engines.*.api_key` an unset
  variable aborts startup** with an exact error:

  ```
  Config error: /home/you/atdork.yml: engines.serper.api_key: environment 'SERPER_API_KEY' is not set
  ```

  In any other key an unset variable logs a warning and degrades to an empty
  string.
- `${VAR:-default}` — uses `default` when `VAR` is unset (never fails).
- Interpolation happens per file, before merging layers.

**API keys are never stored in plaintext in AtDork's docs or examples — always
inject them via `${ENV}`, and never commit a file containing real keys.**
Keys that do end up in config are masked in logs/repr
(`***cd34`) and stripped from error messages by the redactor.

---

## Environment & CLI overrides

Flat (root/search) keys can be overridden with `ATDORK_<KEY>` — types are
coerced automatically:

```bash
export ATDORK_MAX_RESULTS=50     # int
export ATDORK_DEBUG=true         # bool: true/1/yes
export ATDORK_BACKEND=serper     # str
```

Nested sections (`engines`, `profiles`, ...) are never replaced by env
strings. CLI flags always beat the file:

```bash
atdork -q "test" --max-results 5 --backend google   # flags win over yml + env
```

---

## Legacy schema v1 files

Files without any v2 section and without `version:` keep the old behaviour:

```yaml
# v1 — still fully supported
max_results: 50
region: "uk-en"
backend: "google"
format: "json"
```

- Unknown keys are ignored (debug log), as in previous versions.
- `search:`, `output:` etc. are simply absent; defaults apply.

### Migrating to v2

1. Add `version: 2`.
2. Move search knobs under `search:` (optional — root keys still work).
3. Move `format`/`output_dir` under `output:` (optional).
4. Add `engines:`/`profiles:` as needed.
5. Once `version: 2` (or any section) is present, validation is strict:
   typos and unknown keys fail fast with the list of known keys.

---

## Validation & errors

| Problem | Behaviour |
|---------|-----------|
| Unknown key in a v2 file | `ConfigError` listing known keys |
| Unknown key inside `search:`/`output:` | `ConfigError` listing known keys |
| Wrong section type (e.g. `profiles.x` not a list) | `ConfigError` with the exact path |
| Unparseable YAML | `ConfigError: ... failed to parse YAML: ...` |
| Unsupported `version:` | `ConfigError` (supported: 1, 2) |
| `engines.*.api_key` → unset `${VAR}` | `ConfigError` naming file + path + variable |
| Engine present but key empty at query time | clear runtime error, engine skipped, fallback continues |

Config errors abort startup with a non-zero exit code so a broken file never
silently changes search behaviour.

---

## Security checklist

- Store keys in the environment (`export SERPER_API_KEY=...`), reference them
  with `${SERPER_API_KEY}`.
- Keep `atdork.yml` out of version control when it contains anything
  environment-specific, or keep values in `${VAR}` form.
- Logs and error messages pass through the redactor — API keys, URL
  credentials and bearer tokens are masked automatically.
- `~/.config/atdork/config.yml` is a good place for stable personal defaults;
  use `--config` for per-project/team overrides.
