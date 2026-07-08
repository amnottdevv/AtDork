# Database Dork (Bundled GHDB)

## Introduction

AtDork ships with a **bundled Google Hacking Database (GHDB)** dork collection scraped from [Exploit-DB](https://www.exploit-db.com/google-hacking-database). The database contains thousands of curated dorks organized into 14 categories — from footholds and sensitive directories to login portals and advisories.

The Database Dork feature (introduced in v1.3.9.5) lets you **load, filter, and execute** these bundled dorks without manually copy-pasting them. It supports subdirectory paths, comma-separated file combos, random selection, and reproducible runs via RNG seeds.

This is different from the **GHDB Scraper** (`--ghdb-scraper`), which performs a live HTTP fetch from Exploit-DB. The Database Dork feature reads from the **local bundled files** — no network required.

---

## What It Does

| Feature | Description |
|---------|-------------|
| **Bundled Database** | 14 categories, ~7,940 dorks, available offline after install |
| **Extract to Disk** | Copy the bundled database to a local directory for editing |
| **List Available Files** | Show all database files with their dork counts and sizes |
| **Flexible Naming** | Specs accept `01_footholds`, `01_footholds.txt`, or `/subdir/file` |
| **Multi-file Combos** | Load dorks from multiple files in one command via comma |
| **Subdirectory Paths** | Reference dorks in nested folders (e.g., `/db-1/1_none`) |
| **Random Selection** | Pick N random dorks from the combined set without replacement |
| **Reproducible Runs** | Use `--database-seed` for deterministic random selection |
| **Preview Mode** | Inspect loaded dorks without executing them as searches |
| **Path Safety** | Parent traversal (`..`) and absolute paths are rejected |

### Bundled Categories

| # | File | Category | Approx. Dorks |
|---|------|----------|---------------|
| 1 | `01_footholds.txt` | Footholds | 121 |
| 2 | `02_files_containing_usernames.txt` | Files Containing Usernames | 47 |
| 3 | `03_sensitive_directories.txt` | Sensitive Directories | 450 |
| 4 | `04_web_server_detection.txt` | Web Server Detection | 205 |
| 5 | `05_vulnerable_files.txt` | Vulnerable Files | 86 |
| 6 | `06_vulnerable_servers.txt` | Vulnerable Servers | 129 |
| 7 | `07_error_messages.txt` | Error Messages | 124 |
| 8 | `08_files_containing_juicy_info.txt` | Files Containing Juicy Info | 1,746 |
| 9 | `09_files_containing_passwords.txt` | Files Containing Passwords | 401 |
| 10 | `10_sensitive_online_shopping_info.txt` | Sensitive Online Shopping Info | 15 |
| 11 | `11_network_or_vulnerability_data.txt` | Network or Vulnerability Data | 108 |
| 12 | `12_pages_containing_login_portals.txt` | Pages Containing Login Portals | 1,549 |
| 13 | `13_various_online_devices.txt` | Various Online Devices | 743 |
| 14 | `14_advisories_and_vulnerabilities.txt` | Advisories and Vulnerabilities | 2,220 |

> **Total**: ~7,940 dorks (last updated 2026-07-07).

---

## CLI Flags

| Flag | Type | Description |
|------|------|-------------|
| `--extract-database` | flag | Extract bundled database to `./database` |
| `--extract-database-to PATH` | string | Custom destination for extraction (also triggers extraction if used alone) |
| `--database-dork-extract PATH` | string | Shortcut: extract bundled database to `PATH` (v1.3.9.5+) |
| `--force` | flag | Overwrite existing destination when extracting |
| `--list-database-dork` | flag | List all available database files with counts and sizes |
| `--database-dork SPEC` | string | Load dorks from file(s). Comma-separated. Supports subdirs. |
| `--database-r N` | int | Randomly select N dorks from the combined set |
| `--database-path PATH` | string | Custom database root (overrides auto-discovery) |
| `--database-preview` | flag | Preview loaded dorks without running a search |
| `--database-seed N` | int | Optional RNG seed for reproducible `--database-r` |

---

## How to Use

### 1. List Available Database Files

```bash
atdork --list-database-dork
```

**Output:**

```
AtDork Database Dorks (14 files)
┏━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━┓
┃  # ┃ Spec                              ┃    Dorks ┃       Size ┃
┡━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━┩
│  1 │ 01_footholds                      │      121 │     5.3 KB │
│  2 │ 02_files_containing_usernames     │       47 │     2.0 KB │
│  3 │ 03_sensitive_directories          │      450 │    16.3 KB │
│  4 │ 04_web_server_detection           │      205 │     8.8 KB │
│  5 │ 05_vulnerable_files               │       86 │     3.3 KB │
...
│    │ TOTAL                             │     7940 │            │
└────┴───────────────────────────────────┴──────────┴────────────┘
```

### 2. Extract Database to Disk

Four equivalent ways (all produce the same result):

```bash
# Option A: extract to default ./database
atdork --extract-database

# Option B: explicit path
atdork --extract-database --extract-database-to mydork/

# Option C: shortcut (most intuitive)
atdork --database-dork-extract mydork/

# Option D: implicit (path alone triggers extraction)
atdork --extract-database-to mydork/
```

**Overwrite an existing folder:**

```bash
atdork --database-dork-extract mydork/ --force
```

After extraction, you can freely edit the `.txt` files in the destination folder — AtDork will automatically prefer the local `./database` directory over the bundled one.

### 3. Load Dorks from a Single File

```bash
# Load all 121 dorks from 01_footholds as a batch
atdork --database-dork 01_footholds -r 10 -v
```

The `.txt` extension is optional. These are equivalent:

```bash
atdork --database-dork 01_footholds
atdork --database-dork 01_footholds.txt
```

### 4. Load Dorks from Multiple Files (Comma Combo)

```bash
# Combine footholds + sensitive directories + error messages
atdork --database-dork 01_footholds,03_sensitive_directories,07_error_messages -r 15
```

All dorks are merged into a single list, deduplicated while preserving order, then executed as a batch.

### 5. Random Selection

```bash
# Pick 10 random dorks from 01_footholds
atdork --database-dork 01_footholds --database-r 10 -r 5
```

If `--database-r` exceeds the total dork count, all dorks are used and a warning is logged.

### 6. Reproducible Random Selection

```bash
# Same seed = same selection every time
atdork --database-dork 01_footholds --database-r 10 --database-seed 42 -r 5
```

Useful for benchmarking, sharing scan configs with teammates, or replaying a specific dork set.

### 7. Subdirectory Paths

If you organize your extracted database into subfolders (e.g., `mydork/db-1/1_none.txt`), reference them with a leading slash:

```bash
atdork --database-dork /db-1/1_none --database-path mydork/

# Or combine with top-level files
atdork --database-dork /db-1/1_none,01_footholds --database-path mydork/ --database-r 20
```

### 8. Preview Without Executing

```bash
atdork --database-dork 01_footholds,09_files_containing_passwords --database-r 5 --database-preview --database-seed 7
```

**Output:**

```
Database dorks loaded: 5 from 2 file(s): 01_footholds.txt, 09_files_containing_passwords.txt
📂 Database dorks loaded: 5
From: 01_footholds, 09_files_containing_passwords
Random selection: 5 of ... dorks
RNG seed: 7

     1. inurl:"/sidekiq/busy"
     2. (intitle:"SHOUTcast Administrator")|(intext:"U SHOUTcast D.N.A.S. Status")
     3. inurl:/download_file/ intext:"index of /"
     4. ...
     5. ...

Total: 5 dorks ready.
Remove --database-preview to execute them as batch queries.
```

### 9. Custom Database Directory

If you maintain your own dork collection elsewhere:

```bash
atdork --database-path /opt/my-dorks --list-database-dork
atdork --database-path /opt/my-dorks --database-dork custom_file --database-r 50
```

---

## How It Works

### Resolution Order

When you run `--database-dork`, AtDork resolves the database root in this order:

1. **`--database-path PATH`** (explicit override, if provided)
2. **`./database` in current working directory** (extracted copy, takes precedence)
3. **Bundled on filesystem** (next to `atdork.py` or `core/`)
4. **Bundled via `importlib.resources`** (from installed wheel)

This means: if you run `--extract-database` once, all subsequent `--database-dork` calls automatically read from your local `./database` folder — no need to pass `--database-path` every time.

### Path Safety

All file specs are sanitized to prevent directory traversal attacks:

- Leading slashes are stripped (`/db-1/file` → `db-1/file`)
- Parent traversal (`..`) is rejected with `ValueError`
- Absolute paths (`C:\...`, `/etc/passwd`) are rejected
- Non-`.txt` extensions are rejected

This ensures that even untrusted user input (e.g., from a config file) cannot escape the database root.

### Random Selection Algorithm

`--database-r N` uses `random.sample()` (without replacement) from the deduplicated dork list. With `--database-seed S`, a `random.Random(S)` instance is created — guaranteeing identical output across runs and Python versions.

### Integration with Other Features

Database dorks are loaded as a list of query strings, then merged with queries from `--template`, `-q`, and `--batch-file`. The combined list is fed into the standard batch runner, which means all of these work transparently:

```bash
# Combine database dorks + template + custom query
atdork \
  --database-dork 01_footholds --database-r 20 \
  --template sqli --target example.com \
  -q "site:example.com filetype:pdf" \
  -r 10 --concurrency 3 --verbose

# Filter results for WordPress vulnerabilities
atdork --database-dork 09_files_containing_passwords --filter-vuln wordpress -r 10

# Execute a command on every discovered URL
atdork --database-dork 12_pages_containing_login_portals --database-r 50 \
  --exec "curl -s -I {} | head -1" --exec-parallel 5

# Send results to Discord
atdork --database-dork 08_files_containing_juicy_info --database-r 100 \
  --notify discord:https://discord.com/api/webhooks/...
```

---

## Common Workflows

### Workflow 1: Quick Recon on a Target

```bash
# 1. Extract database once
atdork --database-dork-extract mydork/

# 2. Run a randomized sample across multiple categories
atdork --database-dork 01_footholds,03_sensitive_directories,12_pages_containing_login_portals \
  --database-r 30 --database-seed 42 \
  -r 10 --concurrency 3 --verbose \
  --output-dir recon_results/
```

### Workflow 2: Password File Audit

```bash
# Focus on password-related dorks
atdork --database-dork 09_files_containing_passwords \
  --filter-vuln wordpress \
  -r 15 --output passwords.json --format json
```

### Workflow 3: Reproducible Daily Scan

```bash
# Same seed every day = same dork set, deterministic
atdork --database-dork 08_files_containing_juicy_info \
  --database-r 50 --database-seed 1337 \
  -r 10 --cache --cache-ttl 24 \
  --notify slack:https://hooks.slack.com/services/...
```

### Workflow 4: Build a Custom Database

```bash
# 1. Extract bundled database
atdork --database-dork-extract custom_db/

# 2. Add your own subdirectory
mkdir -p custom_db/internal
echo 'site:mycompany.com intitle:"confidential"' > custom_db/internal/company_secrets.txt

# 3. Use your custom file
atdork --database-dork /internal/company_secrets --database-path custom_db/ -r 20
```

---

## Troubleshooting

### "Database directory not found"

```
Error: Database directory not found. Run 'atdork --extract-database' to extract
the bundled GHDB database to the current directory, or specify a path with
--database-path.
```

**Cause:** AtDork cannot find any database directory (no `./database` in CWD, no bundled copy accessible).

**Fix:**

```bash
atdork --extract-database          # extract to ./database
# or
atdork --database-dork-extract ./  # shortcut
```

### "Database dork file not found: 'nonexistent.txt'"

**Cause:** The spec you provided doesn't match any file in the database root.

**Fix:** Run `atdork --list-database-dork` to see available files. Remember that the spec is matched against filenames in the database root — subdirectories must be included in the spec.

### "Parent directory traversal ('..') is not allowed"

**Cause:** You used `..` in the spec, which is blocked for security.

**Fix:** Use absolute paths within the database root only. If you need to reference a file outside the standard location, use `--database-path` to point to a different root.

### "Destination already exists"

```
Error: Destination already exists: '/path/to/mydork'.
Hint: pass --force to overwrite.
```

**Fix:** Add `--force` to overwrite, or delete the folder manually first.

### Extraction works but `--database-dork` still uses bundled data

**Cause:** AtDork prefers `./database` in the current working directory. If you extracted to a different folder, you must either:

- Run AtDork from the folder where you extracted, OR
- Pass `--database-path PATH` explicitly, OR
- Extract to the default location (`./database`)

---

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | Error (file not found, invalid spec, extraction failure, etc.) |

---

## See Also

- [GHDB Scraper](./ghdb-scrapper.md) — for live-fetching dorks from Exploit-DB
- [Template System](./template-system.md) — for YAML-based dork collections
- [Batch Processing](./batch-processing.md) — for running many queries efficiently
- [Filter Vulnerability](./filter-vuln.md) — for filtering results by platform
