# Database Dork

## Introduction

AtDork ships with a bundled dorks collection containing **180,000+ curated dorks** organized into multiple categories and subdirectories. The collection includes:

- GHDB (Google Hacking Database) from Exploit-DB
- Search engine specific dorks (Bing, DuckDuckGo, Shodan, Censys)
- Platform and CMS specific dorks
- Vulnerability focused dorks (LFI, RFI, SQLi, XSS)
- Industry and niche specific dorks

The Database Dork feature lets you load, filter, and execute these bundled dorks without manual copy-pasting. It supports subdirectory paths, comma-separated file combinations, random selection, and reproducible runs via RNG seeds.

This is distinct from the **GHDB Scraper** (`--ghdb-scraper`), which performs live HTTP fetching from Exploit-DB. The Database Dork feature reads from local bundled files — no network required.

---

## What It Does

| Feature | Description |
|---------|-------------|
| Bundled Database | 180,000+ dorks across 20+ categories and subdirectories |
| Extract to Disk | Copy bundled database to a local directory for editing |
| List Available Files | Show all database files with their dork counts and sizes |
| Flexible Naming | Accept filenames with/without `.txt` extension, or subdirectory paths |
| Multi-file Combos | Load dorks from multiple files in one command via comma |
| Subdirectory Paths | Reference dorks in nested folders (e.g., `/bing/bing1.txt`) |
| Random Selection | Pick N random dorks from the combined set without replacement |
| Reproducible Runs | Use `--database-seed` for deterministic random selection |
| Preview Mode | Inspect loaded dorks without executing them as searches |
| Path Safety | Parent traversal (`..`) and absolute paths are rejected |

---

## Bundled Categories

### Root Directory (GHDB - 14 Files)

| # | File | Category |
|---|------|----------|
| 1 | `01_footholds.txt` | Footholds |
| 2 | `02_files_containing_usernames.txt` | Files Containing Usernames |
| 3 | `03_sensitive_directories.txt` | Sensitive Directories |
| 4 | `04_web_server_detection.txt` | Web Server Detection |
| 5 | `05_vulnerable_files.txt` | Vulnerable Files |
| 6 | `06_vulnerable_servers.txt` | Vulnerable Servers |
| 7 | `07_error_messages.txt` | Error Messages |
| 8 | `08_files_containing_juicy_info.txt` | Files Containing Juicy Info |
| 9 | `09_files_containing_passwords.txt` | Files Containing Passwords |
| 10 | `10_sensitive_online_shopping_info.txt` | Sensitive Online Shopping Info |
| 11 | `11_network_or_vulnerability_data.txt` | Network or Vulnerability Data |
| 12 | `12_pages_containing_login_portals.txt` | Pages Containing Login Portals |
| 13 | `13_various_online_devices.txt` | Various Online Devices |
| 14 | `14_advisories_and_vulnerabilities.txt` | Advisories and Vulnerabilities |

### Subdirectories

| Directory | Description |
|-----------|-------------|
| `bing/` | Bing-specific dorks (OR, contains:, location, ip, domain) |
| `duckduckgo/` | DuckDuckGo dorks with !bang shortcuts |
| `shodan-dorks/` | Shodan search queries for IoT and devices |
| `censys-dorks/` | Censys search queries |
| `cms/` | CMS-specific dorks (WordPress, Joomla, Drupal, Laravel) |
| `github-dorks/` | GitHub search for sensitive data (tokens, keys, passwords) |
| `bug-bounty-dorks/` | Bug bounty focused dorks |
| `lfi/` | Local File Inclusion dorks |
| `rfi/` | Remote File Inclusion dorks |
| `common/` | Common dorks (SQLi, XSS, IDOR, etc.) |
| `gaming-dorks/` | Gaming-related dorks |
| `cryptocurrency-dorks/` | Crypto wallet and exchange related dorks |
| `shopping-dorks/` | E-commerce and shopping dorks |
| `carding-dorks/` | Carding and fraud related (security research only) |
| `cctv/` | CCTV and IP camera dorks |
| `cloud-instance-dorks/` | AWS, Azure, GCP instance dorks |
| `onion-dorks/` | Tor and Onion service dorks |
| `movie-dorks/` | Movie streaming and piracy related |
| `misc/` | Miscellaneous dorks |
| `search-engines-dorks/` | Search engine specific dorks |
| `exploit-db/` | Additional Exploit-DB scraped dorks |

---

## CLI Flags

| Flag | Type | Description |
|------|------|-------------|
| `--extract-database` | flag | Extract bundled database to `./database` |
| `--extract-database-to PATH` | string | Custom destination for extraction |
| `--database-dork-extract PATH` | string | Shortcut: extract bundled database to `PATH` |
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

This displays all available database files with their dork counts and file sizes.

### 2. Extract Database to Disk

```bash
# Extract to default ./database
atdork --extract-database

# Extract to custom location
atdork --database-dork-extract mydork/

# Overwrite existing folder
atdork --database-dork-extract mydork/ --force
```

After extraction, you can freely edit the `.txt` files. AtDork automatically prefers the local `./database` directory over the bundled version.

### 3. Load Dorks from a Single File

```bash
# Load all dorks from 01_footholds
atdork --database-dork 01_footholds -r 10 -v
```

The `.txt` extension is optional:
```bash
atdork --database-dork 01_footholds
atdork --database-dork 01_footholds.txt
```

### 4. Load Dorks from Multiple Files

```bash
# Combine multiple GHDB files
atdork --database-dork 01_footholds,03_sensitive_directories,07_error_messages -r 15

# Combine GHDB with subdirectory files
atdork --database-dork 01_footholds,/cms/wordpress,/github-dorks/tokens -r 50
```

All dorks are merged into a single list, deduplicated while preserving order.

### 5. Random Selection

```bash
# Pick 10 random dorks from 01_footholds
atdork --database-dork 01_footholds --database-r 10 -r 5

# Pick 100 random dorks from entire database
atdork --database-dork . --database-r 100 -r 10
```

If `--database-r` exceeds the total dork count, all dorks are used and a warning is logged.

### 6. Reproducible Random Selection

```bash
# Same seed = same selection every time
atdork --database-dork 01_footholds --database-r 10 --database-seed 42 -r 5
```

Useful for benchmarking, sharing configurations, or replaying specific dork sets.

### 7. Subdirectory Paths

Reference dorks in subdirectories with a leading slash:

```bash
# Load from bing subdirectory
atdork --database-dork /bing/bing1 --database-path mydork/

# Load from duckduckgo subdirectory
atdork --database-dork /duckduckgo/ddg1

# Combine subdirectory with root files
atdork --database-dork /bing/bing1,/cms/wordpress,01_footholds --database-r 20
```

### 8. Preview Without Executing

```bash
atdork --database-dork 01_footholds,/bing/bing1,/cms/wordpress \
  --database-r 5 --database-preview --database-seed 7
```

Preview shows the loaded dorks without executing them as search queries.

### 9. Custom Database Directory

```bash
atdork --database-path /opt/my-dorks --list-database-dork
atdork --database-path /opt/my-dorks --database-dork custom_file --database-r 50
```

### 10. Load Everything

```bash
# Load ALL dorks from the entire database
atdork --database-dork . --database-r 1000 -r 10 --concurrency 5

# Load all dorks from a specific directory
atdork --database-dork /cms --database-r 500 -r 20
```

---

## Directory Structure

After extraction, the `database/` directory contains:

```
database/
├── 01_footholds.txt
├── 02_files_containing_usernames.txt
├── 03_sensitive_directories.txt
├── 04_web_server_detection.txt
├── 05_vulnerable_files.txt
├── 06_vulnerable_servers.txt
├── 07_error_messages.txt
├── 08_files_containing_juicy_info.txt
├── 09_files_containing_passwords.txt
├── 10_sensitive_online_shopping_info.txt
├── 11_network_or_vulnerability_data.txt
├── 12_pages_containing_login_portals.txt
├── 13_various_online_devices.txt
├── 14_advisories_and_vulnerabilities.txt
├── README.md
│
├── bing/
├── duckduckgo/
├── shodan-dorks/
├── censys-dorks/
├── cms/
├── github-dorks/
├── bug-bounty-dorks/
├── lfi/
├── rfi/
├── common/
├── gaming-dorks/
├── cryptocurrency-dorks/
├── shopping-dorks/
├── carding-dorks/
├── cctv/
├── cloud-instance-dorks/
├── onion-dorks/
├── movie-dorks/
├── misc/
└── search-engines-dorks/
```

---

## How It Works

### Resolution Order

When you run `--database-dork`, AtDork resolves the database root in this order:

1. `--database-path PATH` (explicit override, if provided)
2. `./database` in current working directory (extracted copy, takes precedence)
3. Bundled on filesystem (next to `atdork.py` or `core/`)
4. Bundled via `importlib.resources` (from installed wheel)

Once extracted, all subsequent `--database-dork` calls automatically read from your local `./database` folder.

### Path Safety

All file specs are sanitized to prevent directory traversal attacks:

- Leading slashes are stripped (`/bing/bing1` → `bing/bing1`)
- Parent traversal (`..`) is rejected with `ValueError`
- Absolute paths (`C:\...`, `/etc/passwd`) are rejected
- Non-`.txt` extensions are rejected

### Random Selection Algorithm

`--database-r N` uses `random.sample()` without replacement from the deduplicated dork list. With `--database-seed S`, a `random.Random(S)` instance is created, guaranteeing identical output across runs and Python versions.

### Integration with Other Features

Database dorks merge with queries from `--template`, `-q`, and `--batch-file`:

```bash
# Combine database dorks + template + custom query
atdork \
  --database-dork 01_footholds,/bing/bing1 --database-r 20 \
  --template sqli --target example.com \
  -q "site:example.com filetype:pdf" \
  -r 10 --concurrency 3 --verbose

# Filter results for WordPress vulnerabilities
atdork --database-dork 09_files_containing_passwords,/cms/wordpress \
  --filter-vuln wordpress -r 10

# Execute command on discovered URLs
atdork --database-dork 12_pages_containing_login_portals,/common/common1 \
  --database-r 50 --exec "curl -s -I {} | head -1" --exec-parallel 5

# Send results to Discord
atdork --database-dork 08_files_containing_juicy_info,/github-dorks/tokens \
  --database-r 100 --notify discord:https://discord.com/api/webhooks/...
```

---

## Common Workflows

### Quick Recon

```bash
# 1. Extract database once
atdork --database-dork-extract mydork/

# 2. Run randomized sample across multiple categories
atdork --database-dork 01_footholds,03_sensitive_directories,12_pages_containing_login_portals,/common/common1 \
  --database-r 30 --database-seed 42 \
  -r 10 --concurrency 3 --verbose \
  --output-dir recon_results/
```

### Password and Token Audit

```bash
atdork --database-dork 09_files_containing_passwords,/github-dorks/tokens,/github-dorks/passwords \
  --database-r 50 -r 15 --output passwords.json --format json
```

### CMS Vulnerability Scan

```bash
atdork --database-dork /cms/wordpress,/cms/joomla,/cms/drupal \
  --database-r 200 --target example.com \
  -r 20 --concurrency 5 --cache --cache-ttl 24
```

### Search Engine Specific

```bash
# Bing-specific dorks
atdork --database-dork /bing/bing1,/bing/bing2 --database-r 50

# DuckDuckGo-specific dorks
atdork --database-dork /duckduckgo/ddg1 --database-r 30
```

### Reproducible Daily Scan

```bash
atdork --database-dork 08_files_containing_juicy_info,/common/common2,/common/common3 \
  --database-r 100 --database-seed 1337 \
  -r 10 --cache --cache-ttl 24 \
  --notify slack:https://hooks.slack.com/services/...
```

### Bug Bounty Focus

```bash
atdork --database-dork /bug-bounty-dorks/programs,/bug-bounty-dorks/scope \
  --database-r 50 --target target.com \
  -r 10 --concurrency 5 --output bug-bounty-results.json
```

### Custom Database

```bash
# 1. Extract bundled database
atdork --database-dork-extract custom_db/

# 2. Add custom file
mkdir -p custom_db/internal
echo 'site:mycompany.com intitle:"confidential"' > custom_db/internal/company_secrets.txt

# 3. Use custom file alongside bundled
atdork --database-dork /internal/company_secrets,/common/common1 \
  --database-path custom_db/ -r 20
```

---

## Troubleshooting

### Database directory not found

```
Error: Database directory not found. Run 'atdork --extract-database' to extract
the bundled GHDB database to the current directory, or specify a path with
--database-path.
```

**Fix:**
```bash
atdork --extract-database
# or
atdork --database-dork-extract ./
```

### Database dork file not found

**Fix:** Run `atdork --list-database-dork` to see available files. Subdirectories must be included with a leading slash.

### Parent directory traversal not allowed

**Cause:** You used `..` in the spec, which is blocked for security.

**Fix:** Use paths within the database root only. For external files, use `--database-path`.

### Destination already exists

```
Error: Destination already exists: '/path/to/mydork'.
Hint: pass --force to overwrite.
```

**Fix:** Add `--force` to overwrite or delete the folder manually.

### Extraction works but `--database-dork` still uses bundled data

**Cause:** AtDork prefers `./database` in the current working directory.

**Fix:** Either run AtDork from the extraction folder, pass `--database-path PATH`, or extract to `./database`.

### Spec '.' matches multiple items

**Cause:** Using `--database-dork .` loads ALL dorks from the entire database.

**Fix:** This is expected behavior. Use `--database-r` to limit the number.

---

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | Error (file not found, invalid spec, extraction failure, etc.) |

---

## See Also

- [GHDB Scraper](./ghdb-scrapper.md) — Live-fetch dorks from Exploit-DB
- [Template System](./template-system.md) — YAML-based dork collections
- [Batch Processing](./batch-processing.md) — Running many queries efficiently
- [Filter Vulnerability](./filter-vuln.md) — Filtering results by platform
