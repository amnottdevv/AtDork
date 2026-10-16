# Environment (Isolated Workspace)

An **environment** is a single folder that becomes AtDork's entire world:
every file AtDork writes — results, logs, cache, resume/dedup state, config,
packages, even the Atdork-DB checkout — lives inside that root **and never
outside it**. Dork results are sensitive; an environment guarantees they do
not scatter across whatever directory you happen to run from.

```bash
atdork env create ~/osint-job                # one-time: create the workspace
atdork --env ~/osint-job -q "inurl:admin"    # run inside it
ls ~/osint-job/results/                      # the only place results appear
```

!!! info "Not a Python venv"
    Environments do not touch Python packages or the interpreter — AtDork stays
    a normal CLI. Think of it as a *workspace* (like a git root, but for all
    AtDork I/O): portable, self-contained, easy to archive or move.

---

## Commands

| Command | Description |
| :--- | :--- |
| `atdork env create <path> [--name NAME]` | Create the folder layout + marker (idempotent). |
| `atdork env init <path>` | Alias of `create`. |
| `atdork env list` | List registered environments (`(active)`, `(missing)` tags). |
| `atdork env use <path>` | Set the default active environment. |
| `atdork env which` | Show the resolved environment and every path it owns. |
| `atdork env info` | Size per area, results file count, DB clone status. |
| `atdork env destroy <path> [--delete]` | Unregister; `--delete` also removes the folder (asks first). |

### Activation (three ways, first hit wins)

1. `--env /path` — per-command
2. `ATDORK_ENV=/path` — per-shell (`export` it)
3. `atdork env use /path` — persistent default (stored in `~/.config/atdork/environments.yml`)

```bash
atdork env use ~/osint-job          # default for every future command
atdork env which                    # verify what is active and why
unset ATDORK_ENV                    # env vars only override when exported
```

An explicit `--env`/`ATDORK_ENV` pointing at a non-environment folder is a
hard error with a fix hint; a stale registry entry only warns.

---

## Layout

```
<root>/
├── .atdork-env              # marker (version, name, created_at)
├── .config/
│   ├── config.yml           # env-local config layer (see below)
│   └── packages/            # package store + Atdork-DB clone
├── cache/                   # cache database (--cache)
├── results/                 # every dork result file
├── logs/                    # atdork.log (rotating)
├── state/                   # atdork.db (resume/dedup history)
└── tmp/
```

## What gets redirected

While an environment is active, these write targets are **owned by the env**:

| Target | Default (no env) | With env |
| :--- | :--- | :--- |
| Results | `./results/` | `<root>/results/` |
| `-o` / `--output` file | any path | `<root>/results/<name>` (or a root-relative path you pass) |
| Log file | `./atdork.log` | `<root>/logs/atdork.log` |
| Resume/dedup DB | `./atdork.db` | `<root>/state/atdork.db` |
| Cache DB | `./atdork_cache.db` | `<root>/cache/atdork_cache.db` |
| Package store | `~/.atdork/packages` | `<root>/.config/packages` |
| Atdork-DB checkout | auto-discovery | `<root>/.config/packages/Atdork-DB` |

Clone the database into the environment once, then `atdork update` refreshes
it in place:

```bash
atdork update                          # clones/pulls Atdork-DB inside the env
atdork index                           # build/inspect the manifest there
```

---

## Strict path guard

Values you pass on the CLI are **kept but constrained**: they must resolve
inside the environment root, otherwise AtDork stops with a clear error —
nothing is written outside, ever.

```bash
atdork --env ~/osint-job -q "x" -o results/scan.json    # ✔ <root>/results/scan.json
atdork --env ~/osint-job -q "x" -o /tmp/loot.txt        # ✘ rejected: outside the root
atdork --env ~/osint-job -q "x" --db-path ../other.db   # ✘ rejected (.. escape)
```

Details:

- **Relative paths resolve against the env root** (the env is your working
  world): `results/x.json` means `<root>/results/x.json`, regardless of the
  shell's current directory.
- The check runs **after** `Path.resolve()` — symlink tricks and `..`
  sequences are followed before containment is tested.
- Values coming from defaults or config (not explicit CLI flags) are simply
  replaced with the env-owned locations; they cannot point outside.
- Input files (`--batch-file`, `--proxy-file`, wordlists) may still be read
  from anywhere — the guard constrains **writes**.

!!! warning "Isolation, not encryption"
    The guard guarantees zero files land outside the root; files *inside* it
    remain plaintext. For true secrecy encrypt the filesystem/volume holding
    the environment.

---

## Config precedence with an environment

```
defaults < global (~/.config/atdork/config.yml)
        < <root>/.config/config.yml        ← env-local config
        < --config <file>                  ← explicit file still wins
        < ATDORK_* env vars < CLI flags
```

Working-directory `atdork.yaml` discovery is **disabled** while an
environment is active: config is deterministic and workspace-scoped, so a
stray file in whatever folder you `cd` into can never leak into a scan.

```yaml
# <root>/.config/config.yml — per-job defaults, travels with the folder
version: 2
search:
  max_results: 30
  region: "us-en"
output:
  format: json
```

---

## Docker

Mount a volume and point `ATDORK_ENV` at it — the container's entire AtDork
I/O lands on the volume:

```bash
docker run --rm -v atdork-job:/data \
  -e ATDORK_ENV=/data ghcr.io/amnottdevv/atdork:latest \
  -q "inurl:admin" --max-results 10
```

---

## Troubleshooting

| Symptom | Fix |
| :--- | :--- |
| `'…' is not an AtDork environment (missing .atdork-env)` | Create it first: `atdork env create <path>`. |
| `'…' resolves to '…' which is outside the environment` | Use a path under the root (relative paths resolve against it). |
| `Registered environment '…' no longer exists` (warning) | Folder moved/deleted — `atdork env use <new-path>` or re-create. |
| Results still land in `./results/` | No env is actually active — check with `atdork env which`. |
| `db repo: not cloned yet` in `env info` | Run `atdork update` inside the environment. |
