# Package Manager (`atdork install`)

> **Data location:** dork data lives in the separate [Atdork-DB](https://github.com/amnottdevv/Atdork-DB) repository under `@folders` (e.g. `@ghdb/01_footholds.txt`). **Browse it in the [web catalog →](https://amnottdevv.github.io/Atdork-DB/)**. This page covers browsing, installing and updating those packages; see [Database Dork](database-scrapper.md) for loading them as queries.

## Introduction

Since v1.3.9.7 AtDork ships **code only** — the 123 dork files (994,603 dorks across 31 `@folders`) live in the Atdork-DB repository, which AtDork treats like a package registry. A generated `Index.idn` manifest describes every file (`ref | sha256 | bytes | dork-lines | description`), and the built-in package manager reads it to search, install, verify and update packages:

```bash
# Browse the index
atdork search cve

# Install (shorthand: 'c' resolves to the unique folder containing cve_1.txt)
atdork install c@cve_1.txt

# Run the installed package as a batch file
atdork --batch-file c@cve_1.txt -r 20
```

The easiest way to discover what's available is the **[web catalog](https://amnottdevv.github.io/Atdork-DB/)** — instant search, folder filters, per-package previews and copy-paste install commands. Docker users: the image bundles the whole database, so no clone is needed ([Docker](../docker.md)).

Nothing is downloaded from the internet by AtDork itself — `install` and `update` use `git` against a local Atdork-DB checkout (cloned once, auto-discovered or pointed at with `--db-repo`).

---

## Package References

Everywhere a dork file is accepted (`--batch-file`, `--database-dork`, `install`, `uninstall`), files are addressed with **package refs**:

| Ref | Meaning |
|-----|---------|
| `@cve/cve_1.txt` | Canonical: `@folder/file.txt` |
| `c@cve_1.txt` | Shorthand: the prefix before `@` is a folder hint, disambiguated by the file it contains |
| `cve_1.txt`, `01_footholds` | Bare file name (`.txt` optional), matched against the index |
| `@cve` | Whole folder — install every member, or load every `.txt` with `--database-dork` |

Invalid or unknown refs fail with an English error and — when close matches exist — a `Did you mean:` suggestion:

```
Error: No package matches '@cvee/cve_1.txt' in the index.
Did you mean: @cve/cve_1.txt
```

Refs are validated against path traversal (`..`, absolute paths) before touching the filesystem.

---

## Commands

Package commands are dispatched before the normal search flow — `atdork install ...` just works, no extra flags.

### `atdork search <keyword>`

Search the index by file or folder name and print matching refs with dork counts, sizes and descriptions:

```bash
atdork search shodan
```

### `atdork install <ref>`

Copy a package (or a whole folder) from the checkout into the local store:

```bash
atdork install @cms/wp.txt      # single file
atdork install @lfi @onion      # multiple at once
atdork install @cve             # whole folder
```

Installing an already-installed, unmodified package is idempotent (`already installed`).

### `atdork uninstall <ref>`

Remove an installed package (or folder) from the store. The Atdork-DB checkout is never touched.

Refs are validated before anything is removed: a reference containing `..`,
an absolute path, or a folder that escapes the store is rejected — `uninstall`
can only ever delete files inside the store.

### `atdork installed`

List what is in the store with integrity status:

| Status | Meaning |
|--------|---------|
| `up to date` | Installed copy matches the index sha256 |
| `modified` | You edited the installed copy (kept; use `--force` to overwrite) |
| `orphan` | The index no longer contains this ref |

### `atdork update`

`git pull --ff-only` the Atdork-DB checkout, then rebuild `Index.idn` — fresh GHDB data lands here weekly via the Atdork-DB workflow.

### `atdork index` / `atdork index --build`

Show the manifest header (entry count, total dorks, generation date) or rebuild `Index.idn` from the `@folders` — for Atdork-DB maintainers.

---

## Local Store

Installed packages live in `~/.atdork/packages/<folder>/<name>` (without the `@`). When loading a package, AtDork prefers the **installed copy**, then falls back to reading the Atdork-DB checkout directly — so `--database-dork @ghdb/01_footholds` works even if you never ran `install`, as long as the checkout exists.

---

## Configuration

| Setting | Flag | Env | Default |
|---------|------|-----|---------|
| `db_repo` | `--db-repo PATH` | `ATDORK_DB_REPO` | `~/Atdork-DB`, then sibling checkouts |
| `db_repo_url` | `--db-repo-url URL` | `ATDORK_DB_REPO_URL` | `https://github.com/amnottdevv/Atdork-DB.git` |
| `package_dir` | `--package-dir PATH` | `ATDORK_PACKAGE_DIR` | `~/.atdork/packages` |

Resolution order: env → last-used config → default. Point `db_repo` at any Atdork-DB checkout (e.g. a fork) and everything — search, install, `--database-dork`, `--batch-file` — follows it.

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| **"Atdork-DB repository not found"** | Clone `https://github.com/amnottdevv/Atdork-DB` to `~/Atdork-DB`, or pass `--db-repo PATH` / set `ATDORK_DB_REPO` |
| **"No package matches ..."** | Run `atdork search <keyword>` to find the exact ref; bare names auto-append `.txt` |
| **"Ambiguous shorthand"** | The prefix before `@` matches several folders — use the canonical `@folder/file.txt` form (the error lists candidates) |
| **Package shows `modified`** | Your local edits are preserved; `atdork install --force` would overwrite them |
| **Stale refs after manual edits** | Rebuild the manifest in the checkout: `atdork index --build` |
| **`install` fails with git errors** | Ensure `git` is on PATH and the checkout is a clean clone (`atdork update` pulls with `--ff-only`) |

Package commands exit with code `0` on success and `1` on any error.

---

## See Also

- [Dork Database](../database/index.md) — package refs, folder list and the [web catalog](https://amnottdevv.github.io/Atdork-DB/)
- [Database Dork](database-scrapper.md) — loading installed packages as query sets
- [Docker](../docker.md) — the image bundles the full database at `/opt/atdork-db`
- [GHDB Scraper](ghdb-scrapper.md) — live dork fetching from Exploit-DB
- [Batch Processing](batch-processing.md) — running many queries with `--batch-file`
