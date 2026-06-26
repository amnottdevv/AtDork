# AtDork Advanced Features Guide

This document covers three powerful features that make AtDork a professional OSINT tool:
**Post‑Processing Hooks**, **Cache System**, and **Database & History**.

---

## 1. Post‑Processing Hooks

### Introduction
Post‑processing hooks allow you to run external commands on every URL discovered by AtDork.
This is useful for automating vulnerability scanning, header grabbing, screenshotting, or
any other action you want to perform on the results without manual effort.

### Functions
| Flag | Description | Default |
|------|-------------|---------|
| `--exec "command {}"` | Execute a command for **every** result URL. `{}` is replaced with the URL. | |
| `--exec-on-vuln "command {}"` | Execute only on URLs flagged as vulnerable (requires `--filter-vuln`). | |
| `--exec-parallel N` | Number of parallel processes. | 1 |
| `--exec-timeout N` | Timeout per command in seconds. | 30 |

### Usage Examples
```bash
# Check HTTP headers of every discovered URL
atdork -q "inurl:admin" -r 10 --exec "curl -sI {} | grep Server"

# Run WPScan only on WordPress-related results
atdork -q "inurl:wp-content" -r 30 --filter-vuln wordpress \
  --exec-on-vuln "wpscan --url {} --enumerate p" --exec-parallel 3 --exec-timeout 60

# Save all URLs to a file for later use
atdork -q "site:example.com" -r 50 --exec "echo {} >> urls.txt"
```

### How It Works
1. After all results are collected and filtered, AtDork extracts the URL (`href`) from each result.
2. If `--exec-on-vuln` is used, only URLs that pass the vulnerability filter are selected.
3. The command template is filled by replacing `{}` with the (shell‑escaped) URL.
4. Commands are executed using Python’s `subprocess.run()` in a thread pool (if `--exec-parallel > 1`).
5. Stdout, stderr, return code, and any error are captured and logged.
6. A short summary (success/failed/timeout) is printed after all commands finish.

---

## 2. Cache System

### Introduction
The cache system stores search results locally in a SQLite database. This prevents redundant
requests to search engines, reduces bandwidth, and allows **offline access** to previously
fetched results.

### Functions
| Flag | Description | Default |
|------|-------------|---------|
| `--cache` | Enable caching. Every search result is saved and served from cache when possible. | |
| `--cache-only` | Only use cached results; never contact search engines. | |
| `--cache-ttl N` | Time‑to‑live in hours. Cached entries older than this are ignored. | 24 |
| `--clear-cache` | Delete all cached entries before starting the session. | |
| `--cache-db PATH` | Specify a custom cache database file. | `atdork_cache.db` |

### Usage Examples
```bash
# Cache all search results for 48 hours
atdork -q "site:gov filetype:pdf" -r 20 --cache --cache-ttl 48

# Use only cached data (offline mode)
atdork -q "site:gov filetype:pdf" -r 20 --cache-only

# Clear old cache and start fresh
atdork --clear-cache

# Use a custom cache location
atdork -q "test" --cache --cache-db /path/to/my_cache.db
```

### How It Works
1. A `SearchCache` object is created when any cache flag is used.
2. A SQLite table `api_cache` is created (if not exists) with columns for query, engine, parameters (JSON), results (JSON), timestamps, and hit count.
3. On **cache write**: after a successful search, the query, engine, normalized parameters, and the result list are stored with an expiration timestamp.
4. On **cache read**: before a search, the cache is checked for an exact match (query + engine + params) that hasn’t expired. If found, the cached results are returned immediately.
5. `--cache-only` skips the network call entirely and returns empty if no cache hit.
6. `--clear-cache` deletes all rows from the table.
7. Expired entries are automatically cleaned up on initialization.

The cache key is built from:
- Query string
- Backend engine
- Parameters: region, safesearch, timelimit, max_results (all normalized to a sorted JSON string)

---

## 3. Database & History

### Introduction
AtDork can persistently store all queries and their results in a SQLite database. This enables
**resuming interrupted batches**, viewing **search history**, **deduplication** across sessions,
and **exporting** everything to JSON/CSV.

### Functions
| Flag | Description | Default |
|------|-------------|---------|
| `--db-path PATH` | Database file path. | `atdork.db` |
| `--resume` | Continue a previously interrupted batch (re‑runs queries with `pending` or `failed` status). | |
| `--history` | Display a list of all previously executed queries with their status. | |
| `--no-dedup` | Disable global URL deduplication (by default, duplicate URLs across queries are skipped). | |
| `--export-db PATH` | Export the entire database to a JSON or CSV file (format guessed from extension). | |

### Usage Examples
```bash
# Resume an interrupted batch
atdork --resume

# View past searches
atdork --history

# Export all stored results to JSON
atdork --export-db all_results.json

# Export to CSV
atdork --export-db all_results.csv

# Disable deduplication (keep every URL even if seen before)
atdork -q "test" --no-dedup

# Use a custom database location
atdork --db-path /secure/path/atdork.db --history
```

### How It Works
1. A `Database` object is created from `core/database.py`. It manages two tables:
   - `queries` (id, query_text, status, timestamps)
   - `results` (id, query_id, title, href, body, raw_json, created_at) with a `UNIQUE(query_id, href)` constraint.

2. **During a batch or single search**:
   - Each query is inserted/updated with status `pending` → `completed` or `failed`.
   - Results are inserted one by one; duplicates (same query_id + href) are silently ignored (unless `--no-dedup`).

3. **`--resume`**:
   - Reads all queries with status `pending` or `failed`, re‑executes them, and updates their status.

4. **`--history`**:
   - Prints all rows from the `queries` table with their status and timestamp.

5. **`--export-db`**:
   - Joins `queries` and `results`, then writes either a JSON (dict `{query_id: [results]}`) or a CSV (flat table with query_text, title, href, body).

6. **`--no-dedup`**:
   - When disabled, the `add_result()` method returns `True` only if a new row was actually inserted (using `INSERT OR IGNORE` and checking `cursor.rowcount`). The batch runner then counts only truly new results.

This database system makes AtDork suitable for long‑running engagements and professional reporting.
