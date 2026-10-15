# Database Dork

> **Data location:** these dorks live in the [Atdork-DB](https://github.com/amnottdevv/Atdork-DB) repository under `@folders` (e.g. `@ghdb/01_footholds.txt`). Browse with `atdork search <keyword>`, install with `atdork install <ref>`.

## Introduction

AtDork ships **code only** — the dork data lives in the separate
[Atdork-DB](https://github.com/amnottdevv/Atdork-DB) repository, checked out
locally (by default `~/Atdork-DB`) and indexed by `Index.idn`. The current
index contains **~978,000 dorks across 100+ files in 29 `@folders`**, including:

- GHDB (Google Hacking Database) from Exploit-DB (`@ghdb/`, refreshed weekly)
- Search engine specific dorks (Bing, DuckDuckGo, Google, Yandex, Shodan, Censys)
- Platform and CMS specific dorks (`@cms/`, `@github/`, `@cloud/`)
- Vulnerability focused dorks (`@lfi/`, `@rfi/`, `@cve/`, `@vuln/`)
- Industry and niche specific dorks (`@crypto/`, `@gaming/`, `@iot/`, `@bug-bounty/`)

The Database Dork feature lets you load, filter, and execute these dorks without
manual copy-pasting. Dorks are addressed with **package refs** such as
`@cve/cve_1.txt`, whole folders such as `@ghdb`, and comma-separated
combinations — plus random selection and reproducible runs via RNG seeds. A
built-in package manager (`atdork search` / `install` / `uninstall` /
`installed`) lets you cache packages locally in `~/.atdork/packages/`.

This is distinct from the **GHDB Scraper** (`--ghdb-scraper`), which performs
live HTTP fetching from Exploit-DB. The Database Dork feature reads from local
files — no network required.

---

## What It Does

| Feature | Description |
|---------|-------------|
| Atdork-DB Packages | ~978,000 dorks across 29 `@folders`, resolved from the Atdork-DB checkout |
| Package Manager | `atdork search` / `install` / `uninstall` / `installed` — cache packages in `~/.atdork/packages/` |
| Manifest Index | `Index.idn` maps every `@folder/file.txt` to checksum, size, dork count, and description |
| List Available Files | `--list-database-dork` shows all index entries as `@folder/file.txt` with dork counts and sizes |
| Flexible Naming | Accepts canonical refs, shorthand (`c@cve_1.txt`), bare file names, and whole folders |
| Multi-file Combos | Load dorks from multiple files or folders in one command via comma |
| Whole-folder Loading | `--database-dork @ghdb` loads every `.txt` member of the folder |
| Random Selection | Pick N random dorks from the combined set without replacement |
| Reproducible Runs | Use `--database-seed` for deterministic random selection |
| Preview Mode | Inspect loaded dorks without executing them as searches |
| Path Safety | Parent traversal (`..`) and absolute paths are rejected |

---

## Categories

All dorks live in the Atdork-DB checkout under `@folders`. The `@ghdb/` folder
holds the numbered GHDB categories:

### GHDB (`@ghdb/` — 14 Files)

| Ref | Category | Dorks |
|-----|----------|-------|
| `@ghdb/01_footholds.txt` | Footholds | 121 |
| `@ghdb/02_files_containing_usernames.txt` | Files Containing Usernames | 47 |
| `@ghdb/03_sensitive_directories.txt` | Sensitive Directories | 450 |
| `@ghdb/04_web_server_detection.txt` | Web Server Detection | 205 |
| `@ghdb/05_vulnerable_files.txt` | Vulnerable Files | 86 |
| `@ghdb/06_vulnerable_servers.txt` | Vulnerable Servers | 129 |
| `@ghdb/07_error_messages.txt` | Error Messages | 124 |
| `@ghdb/08_files_containing_juicy_info.txt` | Files Containing Juicy Info | 1,743 |
| `@ghdb/09_files_containing_passwords.txt` | Files Containing Passwords | 401 |
| `@ghdb/10_sensitive_online_shopping_info.txt` | Sensitive Online Shopping Info | 15 |
| `@ghdb/11_network_or_vulnerability_data.txt` | Network or Vulnerability Data | 108 |
| `@ghdb/12_pages_containing_login_portals.txt` | Pages Containing Login Portals | 1,549 |
| `@ghdb/13_various_online_devices.txt` | Various Online Devices | 743 |
| `@ghdb/14_advisories_and_vulnerabilities.txt` | Advisories and Vulnerabilities | 2,219 |

The `@ghdb/` files are refreshed weekly by an automated workflow in the
Atdork-DB repository; run `atdork update` to pull the latest data and rebuild
the index.

### Folders (28 Total)

| Folder | Description |
|--------|-------------|
| `@admin/` | Admin panel and stats-page dorks (`adminpanel-dorks`, `awstats`) |
| `@bing/` | Bing-specific dorks (`bing1`, `bing2`) |
| `@bug-bounty/` | Bug bounty and responsible disclosure dorks (`bbdorks`) |
| `@carding/` | Carding and fraud-related dorks (security research only) |
| `@censys/` | Censys search queries (`censysdork`) |
| `@cloud/` | Cloud instance dorks — AWS, Azure, GCP, IBM (`amazondorks`, `aws`, `azure`, `googlecloud`, `ibmcloud`) |
| `@cms/` | CMS-specific dorks — WordPress, Joomla, Laravel, Magento (`wp`, `wp2`, `joomla`, `laravel`, `magento`) |
| `@common/` | Common dorks — SQLi, XSS, IDOR, etc. (`common1`–`common5`) |
| `@crypto/` | Crypto wallet and exchange dorks (incl. 600k-scale sets) |
| `@cve/` | CVE-focused dorks (`cve_1`) |
| `@duckduckgo/` | DuckDuckGo dorks with `!bang` shortcuts (`ddg1`, `ddgo`) |
| `@exploit-db/` | Additional Exploit-DB category files (`Footholds`, `Sensitive-Directories`, …) |
| `@gaming/` | Gaming-related dorks (`fortnite`, `minecraft`, …) |
| `@ghdb/` | Google Hacking Database, numbered categories (see above) |
| `@github/` | GitHub search for secrets — tokens, keys, passwords (`git-dorks`, `githubdorks`, …) |
| `@google/` | Google dorks (`googledorks1`, `googledorks2`) |
| `@iot/` | CCTV, IP camera, and IoT device dorks (`cctv`, `cctv3`, `various-iot-devices-dorks`) |
| `@lfi/` | Local File Inclusion dorks (`lfi`) |
| `@movie/` | Movie streaming dorks (`netflix-dorks`, `movie`) |
| `@network/` | IP range and web server detection dorks (`ipdorks`, `webserver-detection-dorks`) |
| `@onion/` | Tor and onion service dorks (`onion`) |
| `@rfi/` | Remote File Inclusion dorks (`rfi`) |
| `@sensitive/` | Sensitive files, dirs, logs, and hidden files dorks |
| `@shodan/` | Shodan queries (`shodan1`, `shodan2`, `shodanqueries`, ICS/IoT CSV) |
| `@shopping/` | E-commerce and shopping dorks (`10kshopping-dorks`, `webstore-dorks`) |
| `@social/` | Discord and LinkedIn dorks (`discord-tokens-dorks`, `linkedindorks`) |
| `@vuln/` | Vulnerable server dorks (`vuln-server-dorks`) |
| `@yandex/` | Yandex dorks (`yandex`) |

---

## CLI Flags

| Flag | Type | Description |
|------|------|-------------|
| `--db-repo PATH` | string | Path to the Atdork-DB checkout (default: auto-discover, or config key `db_repo`; env `ATDORK_DB_REPO`) |
| `--db-repo-url URL` | string | Git URL of the Atdork-DB repository (used by `atdork update`) |
| `--package-dir PATH` | string | Override the package store (default: `~/.atdork/packages`) |
| `--list-database-dork` | flag | List all index entries as `@folder/file.txt` with dork counts and sizes |
| `--database-dork SPEC` | string | Load dorks from package refs. Comma-separated. Accepts `@folder/file.txt`, `x/file.txt` shorthand, bare file names, and whole folders |
| `--database-r N` | int | Randomly select N dorks from the combined set |
| `--database-path PATH` | string | Root of a legacy local database copy |
| `--database-preview` | flag | Preview loaded dorks without running a search |
| `--database-seed N` | int | Optional RNG seed for reproducible `--database-r` |
| `--extract-database` | flag | Legacy: copy a local `./database` directory to a destination |
| `--extract-database-to PATH` | string | Custom destination for `--extract-database` |
| `--database-dork-extract PATH` | string | Legacy shortcut: copy a local database to `PATH` |
| `--force` | flag | Overwrite existing destination when extracting |

> **Note:** AtDork no longer bundles a dork database — it ships code only. The
> `--extract-database`, `--extract-database-to`, `--database-dork-extract`, and
> `--force` flags operate on a **legacy local `./database` directory** you
> provide (e.g. an old extraction kept for offline editing). New setups should
> use the Atdork-DB checkout and package refs instead.

---

## How to Use

### 1. Browse and List Available Packages

```bash
# Search the index by keyword (returns @folder/file.txt refs)
atdork search wp

# List every index entry with dork counts and sizes
atdork --list-database-dork
```

`atdork search wp` prints matching refs such as `@cms/wp.txt` (26,324 dorks)
and `@cms/wp2.txt` (474 dorks), ready to pass to `--database-dork` or
`atdork install`.

### 2. Install Packages Locally

```bash
# Install a whole folder into the package store
atdork install @cms

# Install a single file
atdork install @cve/cve_1.txt

# Show what is installed
atdork installed

# Remove an installed package
atdork uninstall @cve/cve_1.txt
```

Installed copies land in `~/.atdork/packages/` and take priority when
resolving `--database-dork` refs.

### 3. Update the Atdork-DB Checkout

```bash
# git pull the Atdork-DB checkout and rebuild the index
atdork update

# Show or manually rebuild the manifest
atdork index
atdork index --build
```

### 4. Load Dorks from a Single File

```bash
# Canonical ref: folder + file
atdork --database-dork @ghdb/01_footholds.txt -r 10 -v

# The .txt extension is optional
atdork --database-dork @ghdb/01_footholds

# Bare file name, matched against the index (.txt auto-appended)
atdork --database-dork 01_footholds

# Shorthand: unique single-letter folder prefix
atdork --database-dork c@cve_1.txt
```

### 5. Load Dorks from Multiple Files

```bash
# Combine refs, bare names, and shorthand in one command
atdork --database-dork @ghdb/01_footholds.txt,@cms/wp.txt -r 50
atdork --database-dork @cve/cve_1.txt,c@cve_1.txt,01_footholds --database-preview
```

All dorks are merged into a single list, deduplicated while preserving order.

### 6. Load Whole Folders

```bash
# Load EVERY .txt member of a folder
atdork --database-dork @ghdb --database-r 100 -r 10

# Combine multiple folders
atdork --database-dork @ghdb,@lfi --database-r 50 --database-preview

# A folder plus a specific file
atdork --database-dork @bug-bounty,@cve/cve_1.txt --database-preview
```

### 7. Random Selection

```bash
# Pick 10 random dorks from one file
atdork --database-dork @ghdb/01_footholds --database-r 10 -r 5

# Pick 100 random dorks from an entire folder
atdork --database-dork @github --database-r 100 -r 10
```

If `--database-r` exceeds the total dork count, all dorks are used and a warning is logged.

### 8. Reproducible Random Selection

```bash
# Same seed = same selection every time
atdork --database-dork @ghdb/01_footholds --database-r 10 --database-seed 42 -r 5
```

Useful for benchmarking, sharing configurations, or replaying specific dork sets.

### 9. Preview Without Executing

```bash
atdork --database-dork 01_footholds,@bing/bing1,@cms/wp \
  --database-r 5 --database-preview --database-seed 7
```

Preview shows the loaded dorks without executing them as search queries.

### 10. Custom Local Copy (Legacy)

```bash
# Point at a local database root (e.g. a hand-edited copy)
atdork --database-path /opt/my-dorks --database-dork custom_file --database-r 50
```

Legacy subdirectory paths such as `/bing/bing1` only resolve against a local
`./database` directory or a `--database-path` root. In index mode, use
`@`-refs instead (e.g. `@bing/bing1`).

---

## Directory Structure

Dork data lives in the Atdork-DB checkout (default `~/Atdork-DB`; override with
`--db-repo` or `ATDORK_DB_REPO`):

```
Atdork-DB/
├── Index.idn               # generated manifest: @folder/file.txt|sha256|bytes|dork-lines|description
├── @exploit-db/  @ghdb/  @shodan/  @censys/  @cloud/  @cms/  @common/  @crypto/
├── @cve/  @duckduckgo/  @bing/  @google/  @yandex/  @gaming/  @github/  @lfi/  @rfi/
├── @admin/  @sensitive/  @social/  @network/  @vuln/  @shopping/  @movie/  @onion/
├── @bug-bounty/  @carding/  @iot/
└── scripts/ + .github/workflows/   # weekly GHDB auto-refresh into @ghdb/
```

Installed packages are cached separately:

```
~/.atdork/packages/
└── @cms/wp.txt   # one copy per installed package ref
```

---

## How It Works

### Package Reference Grammar

`--database-dork` (and `--batch-file`) accept these ref forms:

| Ref | Meaning |
|-----|---------|
| `@cve/cve_1.txt` | Canonical: folder + file |
| `c@cve_1.txt` | Shorthand: unique folder prefix — `c` resolves to the folder starting with `c` that contains `cve_1.txt` |
| `cve_1.txt` / `01_footholds` | Bare file name, matched against the index (`.txt` auto-appended) |
| `@cve` | Whole folder — loads every `.txt` member |

### Resolution Order

When you run `--database-dork`, AtDork resolves each ref in this order:

1. Installed copy in the package store (`~/.atdork/packages/`)
2. The Atdork-DB checkout (`~/Atdork-DB`, or `--db-repo` / `ATDORK_DB_REPO`)
3. A legacy local `./database` directory, or the root given by `--database-path PATH`

Unknown refs print a `Did you mean:` suggestion with close matches from the
index, and `atdork search <keyword>` finds the right package by name.

### Path Safety

All file specs are sanitized to prevent directory traversal attacks:

- Parent traversal (`..`) is rejected with `ValueError`
- Absolute paths (`C:\...`, `/etc/passwd`) are rejected
- Legacy subdirectory paths (`/bing/bing1`) are only accepted against a local
  database root; index mode uses `@`-refs

### Random Selection Algorithm

`--database-r N` uses `random.sample()` without replacement from the deduplicated dork list. With `--database-seed S`, a `random.Random(S)` instance is created, guaranteeing identical output across runs and Python versions.

### Integration with Other Features

Database dorks merge with queries from `--template`, `-q`, and `--batch-file`
(the same package refs work there too):

```bash
# Combine database dorks + template + custom query
atdork \
  --database-dork @ghdb/01_footholds,@bing/bing1 --database-r 20 \
  --template sqli --target example.com \
  -q "site:example.com filetype:pdf" \
  -r 10 --concurrency 3 --verbose

# Batch-file accepts package refs directly
atdork --batch-file @cve/cve_1.txt -r 10

# Filter results for WordPress vulnerabilities
atdork --database-dork @ghdb/09_files_containing_passwords,@cms/wp \
  --filter-vuln wordpress -r 10

# Execute command on discovered URLs
atdork --database-dork @ghdb/12_pages_containing_login_portals,@common/common1 \
  --database-r 50 --exec "curl -s -I {} | head -1" --exec-parallel 5

# Send results to Discord
atdork --database-dork @ghdb/08_files_containing_juicy_info,@github/git-dorks \
  --database-r 100 --notify discord:https://discord.com/api/webhooks/...
```

---

## Common Workflows

### Quick Recon

```bash
# Run a randomized sample across multiple categories
atdork --database-dork @ghdb/01_footholds.txt,@ghdb/03_sensitive_directories.txt,@ghdb/12_pages_containing_login_portals.txt,@common/common1 \
  --database-r 30 --database-seed 42 \
  -r 10 --concurrency 3 --verbose \
  --output-dir recon_results/
```

### Password and Token Audit

```bash
atdork --database-dork @ghdb/09_files_containing_passwords.txt,@github/git-dorks,@github/githubdorks \
  --database-r 50 -r 15 --output passwords.json --format json
```

### CMS Vulnerability Scan

```bash
# Install once, then scan
atdork install @cms

atdork --database-dork @cms/wp,@cms/joomla,@cms/laravel \
  --database-r 200 --target example.com \
  -r 20 --concurrency 5 --cache --cache-ttl 24
```

### Search Engine Specific

```bash
# Bing-specific dorks
atdork --database-dork @bing/bing1,@bing/bing2 --database-r 50

# DuckDuckGo-specific dorks
atdork --database-dork @duckduckgo/ddg1 --database-r 30
```

### Reproducible Daily Scan

```bash
atdork --database-dork @ghdb/08_files_containing_juicy_info.txt,@common/common2,@common/common3 \
  --database-r 100 --database-seed 1337 \
  -r 10 --cache --cache-ttl 24 \
  --notify slack:https://hooks.slack.com/services/...
```

### Bug Bounty Focus

```bash
atdork --database-dork @bug-bounty --database-r 50 --target target.com \
  -r 10 --concurrency 5 --output bug-bounty-results.json
```

### Custom Local Dork File

```bash
# 1. Create a local copy root
mkdir -p mydorks/internal
echo 'site:mycompany.com intitle:"confidential"' > mydorks/internal/company_secrets.txt

# 2. Use your file alongside indexed packages
atdork --database-path mydorks/ --database-dork /internal/company_secrets,@common/common1 -r 20
```

---

## Troubleshooting

### Database directory not found

**Fix:** AtDork expects the Atdork-DB checkout. Either clone it and point
AtDork at it, or use a local copy:

```bash
# Clone the data repo once
git clone https://github.com/amnottdevv/Atdork-DB ~/Atdork-DB

# Or point AtDork at an existing checkout
atdork --db-repo /path/to/Atdork-DB ...
export ATDORK_DB_REPO=/path/to/Atdork-DB

# Or use a local database copy
atdork --database-path /path/to/local/db --database-dork <ref>
```

### Database dork file not found

Unknown refs now print a `Did you mean:` line with close matches from the
index. **Fix:** Run `atdork search <keyword>` to find the package, or
`atdork --list-database-dork` to see every `@folder/file.txt` entry.

### Parent directory traversal not allowed

**Cause:** You used `..` in the spec, which is blocked for security.

**Fix:** Use refs within the index or database root only. For external files, use `--database-path`.

### Destination already exists

```
Error: Destination already exists: '/path/to/mydork'.
Hint: pass --force to overwrite.
```

**Fix:** Add `--force` to overwrite or delete the folder manually. (Legacy extraction only.)

### Legacy subdirectory path resolves to nothing

**Cause:** Paths like `/bing/bing1` only work against a local `./database`
directory or a `--database-path` root — not in index mode.

**Fix:** Use `@`-refs instead: `@bing/bing1`.

---

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | Error (file not found, invalid ref, extraction failure, etc.) |

---

## See Also

- [GHDB Scraper](./ghdb-scrapper.md) — Live-fetch dorks from Exploit-DB
- [Template System](./template-system.md) — YAML-based dork collections
- [Batch Processing](./batch-processing.md) — Running many queries efficiently
- [Filter Vulnerability](./filter-vuln.md) — Filtering results by platform
