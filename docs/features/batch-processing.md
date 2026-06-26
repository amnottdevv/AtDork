# Batch Processing

## Introduction

AtDork's batch processing system allows you to run multiple dorks in a single session, either sequentially or in parallel. This is essential for large-scale OSINT operations where you need to scan multiple targets or run multiple dorks without manual intervention.

The batch system includes progress tracking, resume capability, database storage, and configurable concurrency to balance speed and reliability.

---

## What It Does

| Feature | Description |
|---------|-------------|
| **Batch File Support** | Run dorks from a text file (one per line) |
| **Parallel Execution** | Run multiple queries simultaneously (`--concurrency`) |
| **Sequential Fallback** | Automatically switches to sequential mode if too many failures occur |
| **Resume Capability** | Resume interrupted batches with `--resume` |
| **Database Storage** | Store all results in SQLite for history and deduplication |
| **Progress Tracking** | Real-time progress bar with percentage and elapsed time |
| **Per-Query Output** | Save each query result to a separate file (`--output-dir`) |
| **Single File Output** | Save all results to a single JSON/CSV file (`-o`) |

---

## How to Use

### Basic Batch File
```bash
atdork --batch-file dorks.txt -r 30 --format csv -o results.csv
```

**Batch file format (`dorks.txt`):**
```
# One dork per line
# Lines starting with # are ignored
site:edu filetype:xls
inurl:admin login
intitle:"index of" "backup"
filetype:env "DB_PASSWORD"
```

### With Concurrency (Parallel)
```bash
atdork --batch-file dorks.txt -r 40 --concurrency 5 --delay 2 --format json -o batch_results.json
```

### With Resilience and Adaptive Delay
```bash
atdork --batch-file dorks.txt --resilient --adaptive-delay --concurrency 3 --delay 2
```

### Save Each Query to Separate File
```bash
atdork --batch-file dorks.txt -r 30 --format json --output-dir ./results/
```

### Resume Interrupted Batch
```bash
atdork --resume
```

### View Search History
```bash
atdork --history
```

### Export Database to JSON/CSV
```bash
atdork --export-db all_results.json
```

### Disable Deduplication (Keep All Results)
```bash
atdork --batch-file dorks.txt --no-dedup -o all_results.json
```

---

## How It Works

### 1. Batch File Processing

**Input File (`dorks.txt`):**
```
# Comments are ignored
site:example.com filetype:pdf
inurl:admin login
intitle:"index of" "backup"
```

**Processing Flow:**
```
1. User provides --batch-file dorks.txt
   ↓
2. AtDork reads the file, ignoring blank lines and comments
   ↓
3. Each line becomes a separate query
   ↓
4. Queries are executed according to --concurrency setting
   ↓
5. Results are collected and saved to output
```

### 2. Concurrency Modes

| Mode | Description | When to Use |
|------|-------------|-------------|
| **Sequential (`--concurrency 1`)** | One query at a time | Default; safe but slower |
| **Parallel (`--concurrency 2-10`)** | Multiple queries simultaneously | Faster for large batches; requires stable proxies |

**Parallel Execution Flow:**
```
1. Create ThreadPoolExecutor with N workers
   ↓
2. Submit all queries to the pool
   ↓
3. Results are collected as they complete
   ↓
4. Progress bar updates in real-time
   ↓
5. If too many consecutive failures:
   └─ Automatically fallback to sequential mode
```

### 3. Fallback Mechanism

When running in parallel mode, AtDork monitors for failures:

- Tracks **consecutive failures** per query
- If **3 consecutive failures** occur, automatically switches to sequential mode
- This prevents wasting resources on a failing batch

**Fallback Flow:**
```
Parallel Mode Running
   ↓
Failure 1 → Count = 1
   ↓
Failure 2 → Count = 2
   ↓
Failure 3 → Count = 3 → FALLBACK TO SEQUENTIAL
   ↓
Sequential Mode
   ↓
Continue with remaining queries one by one
```

### 4. Resume Mechanism

When running with `--resume`, AtDork:

1. Checks the database for queries with status `pending` or `failed`
2. Re-runs only those queries
3. Skips already completed queries
4. Updates the database with new results

**Database Schema:**
```sql
CREATE TABLE IF NOT EXISTS queries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_text TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_id INTEGER NOT NULL,
    title TEXT,
    href TEXT,
    body TEXT,
    raw_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (query_id) REFERENCES queries(id),
    UNIQUE(query_id, href)
);
```

### 5. Database Storage

**Benefits:**
- **Resume**: Interrupted batches can be resumed
- **History**: View past searches with `--history`
- **Deduplication**: Prevent duplicate URLs in the same batch
- **Export**: Export all data to JSON or CSV

**Database Commands:**
```bash
# View history
atdork --history

# Resume pending queries
atdork --resume

# Export to JSON
atdork --export-db results.json

# Export to CSV
atdork --export-db results.csv

# Disable deduplication
atdork --batch-file dorks.txt --no-dedup
```

### 6. Progress Tracking

AtDork displays a real-time progress bar:

```
Running batch queries... ━━━━━━━━━━━━━━━━━━━━ 45% (9/20) ⏱️ 12.3s
```

**Progress Bar Components:**
- **Spinner**: Indicates activity
- **Description**: Current query or status
- **Bar**: Visual progress
- **Percentage**: Completion percentage
- **Counter**: Current/Max queries
- **Elapsed Time**: Time since batch started

---

## Full Flag Reference

| Flag | Description | Default |
|------|-------------|---------|
| `--batch-file` | File with one query per line | None |
| `--batch-separator` | Separator for inline queries | `;` |
| `--concurrency` | Number of parallel threads | 1 |
| `--max-fallback-failures` | Failures before fallback to sequential | 3 |
| `--resume` | Resume pending queries | Disabled |
| `--history` | Show search history | Disabled |
| `--no-dedup` | Disable global URL deduplication | Disabled |
| `--export-db` | Export database to file (json/csv) | None |
| `-o, --output` | Save all results to single file | None |
| `--output-dir` | Save each query to separate file | None |
| `--format` | Output format: `txt`, `json`, `csv` | `txt` |
| `-v, --verbose` | Show results during batch | Disabled |

---

## Real-World Use Cases

### 1. Automated Weekly Monitoring
```bash
# Add to crontab (Linux/macOS)
0 6 * * 1 cd /path/to/atdork && atdork --batch-file weekly_dorks.txt --format csv --output-dir /reports/$(date +\%Y-\%W)/
```

### 2. Large-Scale Bug Bounty Recon
```bash
atdork --batch-file dorks.txt --concurrency 5 --delay 2 \
  --proxy-file proxies.txt --strict --resilient \
  --format json -o recon_results.json
```

### 3. Multi-Target Recon Using Templates
```bash
atdork --template sqli,xss,exposed_config,login_panels \
  --target target1.com --target target2.com --target target3.com \
  --proxy-file proxies.txt --strict --resilient \
  --concurrency 5 -v -o multi_target.json
```

### 4. Resume Failed Batch
```bash
atdork --resume --proxy-file proxies.txt --resilient
```

### 5. Export Database History for Reporting
```bash
atdork --export-db weekly_report.json
```

### 6. High-Concurrency Scan (with Stable Proxies)
```bash
atdork --batch-file dorks.txt --concurrency 10 --delay 1 \
  --proxy-file premium_proxies.txt --strict \
  --format json -o fast_scan.json
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| **Batch stuck** | Reduce `--concurrency`, increase `--timeout` to 15, enable `--resilient` |
| **Too many failures** | Enable `--resilient` and `--adaptive-delay`, add more proxies |
| **Database locked** | Close other AtDork instances, delete `atdork.db` and restart |
| **Resume not working** | Check database exists (`atdork.db`), verify queries are `pending` |
| **Parallel mode too slow** | Reduce `--concurrency` (more threads doesn't always mean faster) |
| **Results full of spam** | Enable `--strict-filter` or adjust validation flags |
| **Batch output missing** | Use `-v` to see results during batch, check `--output` path |

---

## Batch File Examples

### `dorks.txt` – General Recon
```
# Domain-specific
site:example.com filetype:pdf
site:example.com filetype:docx
site:example.com intitle:"index of"

# Admin panels
intitle:"admin panel" inurl:login
inurl:admin login
site:example.com wp-admin

# Exposed data
filetype:env "DB_PASSWORD"
filetype:log "password"
site:pastebin.com example.com
```

### `wordpress_dorks.txt` – WordPress-Specific
```
inurl:wp-content site:example.com
inurl:wp-admin site:example.com
inurl:wp-includes site:example.com
inurl:xmlrpc.php site:example.com
inurl:wp-json site:example.com
```

### `bug_bounty_dorks.txt` – Bug Bounty Focused
```
site:target.com inurl:product.php?id=
site:target.com inurl:category.php?id=
site:target.com inurl:news.php?id=
site:target.com filetype:env
site:target.com filetype:log
site:target.com intitle:"index of"
```

### `monitoring_dorks.txt` – Weekly Monitoring
```
# Check for new exposed configs
filetype:env "DB_PASSWORD"

# Check for new admin panels
intitle:"admin panel" inurl:login

# Check for new pastebin leaks
site:pastebin.com "password"

# Check for new backup files
filetype:bak intitle:"index of"
```