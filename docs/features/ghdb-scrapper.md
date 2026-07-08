# GHDB Scraper (Live Fetch from Exploit-DB)

## Introduction

The **GHDB Scraper** is AtDork's live-fetch module for pulling the latest Google Dorks directly from the [Exploit-DB Google Hacking Database](https://www.exploit-db.com/google-hacking-database). Unlike the [Database Dork](./database-scrapper.md) feature which reads from a bundled static snapshot, the scraper performs real HTTP requests to Exploit-DB's AJAX endpoint and returns the freshest dorks available.

Use the scraper when you need:

- **Up-to-date dorks** (the bundled snapshot may be days or weeks old)
- **Filtering by category or year** on the live dataset
- **A quick refresh** of your local database
- **Export to JSON or TXT** for use with other tools

The scraper is implemented in [`core/ghdb_scraper.py`](../../core/ghdb_scraper.py) and is invoked via the `--ghdb-scraper` family of CLI flags.

---

## What It Does

| Feature | Description |
|---------|-------------|
| **Live HTTP Fetch** | Pulls dorks directly from `exploit-db.com/google-hacking-database` |
| **AJAX Endpoint** | Uses the same JSON endpoint as the GHDB web page itself |
| **Retry with SSL Fallback** | Automatically retries on failure and falls back to insecure SSL if needed |
| **Category Filtering** | Filter by category name (partial match) or numeric ID |
| **Year Filtering** | Filter by single year, comma-separated years, or ranges |
| **Result Limiting** | Cap the total number of dorks returned (`--ghdb-r`) |
| **Category Listing** | Show all categories with their dork counts (`--ghdb-list-categories`) |
| **Auto Format Detection** | Output to `.json` (with metadata) or `.txt` (one dork per line) |
| **No Search Execution** | Scraper only collects dorks — pipe them to `--batch-file` to execute |

---

## CLI Flags

All flags are in the `GHDB Scraper` argument group:

| Flag | Type | Description |
|------|------|-------------|
| `--ghdb-scraper` | flag | Run the scraper mode (required to fetch/save dorks) |
| `--ghdb-file PATH` | string | Save scraped dorks to a file (`.json` or `.txt`) |
| `--ghdb-categories SPEC` | string | Filter by category: names (partial) or IDs, comma-separated |
| `--ghdb-years SPEC` | string | Filter by year: single, comma-separated, or range (`2020-2023,2024`) |
| `--ghdb-r N` | int | Limit total dorks returned (after filtering) |
| `--ghdb-list-categories` | flag | List all categories with dork counts, then exit |

> **Note**: The scraper mode is exclusive — when active, AtDork does not perform any search, interactive mode, or template/batch processing. It only fetches and optionally saves dorks.

---

## How to Use

### 1. List Available Categories

Before scraping, see what categories exist and how many dorks each contains:

```bash
atdork --ghdb-list-categories
```

**Output:**

```
🔍 Mengambil data GHDB dari Exploit-DB...

Kategori GHDB yang tersedia (14 kategori):
   1 - Footholds (121 dork)
   2 - Files Containing Usernames (47 dork)
   3 - Sensitive Directories (450 dork)
   4 - Web Server Detection (205 dork)
   5 - Vulnerable Files (86 dork)
   6 - Vulnerable Servers (129 dork)
   7 - Error Messages (124 dork)
   8 - Files Containing Juicy Info (1746 dork)
   9 - Files Containing Passwords (401 dork)
  10 - Sensitive Online Shopping Info (15 dork)
  11 - Network or Vulnerability Data (108 dork)
  12 - Pages Containing Login Portals (1549 dork)
  13 - Various Online Devices (743 dork)
  14 - Advisories and Vulnerabilities (2220 dork)
```

The numeric IDs shown here can be used with `--ghdb-categories`.

### 2. Scrape All Dorks (No Filter)

Fetch all available dorks and preview the first 20:

```bash
atdork --ghdb-scraper
```

**Output:**

```
🔍 Mengambil data GHDB dari Exploit-DB...
✅ Ditemukan 7940 dork (dari total 7940 di GHDB)
  - intitle:"ERROR: The requested URL could not be retrieved" "While trying to retrieve the URL" "The following error was encountered:"
  - intitle:MyShell 1.1.0 build 20010923
  - inurl:polly/CP
  - "Please re-enter your password It must match exactly"
  - "index of /" ( upload.cfm | upload.asp | upload.php | upload.cgi | upload.jsp | upload.pl )
  ... dan 7920 dork lainnya (gunakan --ghdb-file untuk simpan semua)
```

### 3. Save All Dorks to a File

```bash
# Save as plain text (one dork per line)
atdork --ghdb-scraper --ghdb-file dorks/all_dorks.txt

# Save as JSON (with metadata: id, date, category)
atdork --ghdb-scraper --ghdb-file dorks/all_dorks.json
```

**JSON output structure:**

```json
[
  {
    "text": "intitle:\"index of\" passwd",
    "id": "5052",
    "date": "2022-03-14",
    "cat_id": 9,
    "cat_title": "Files Containing Passwords"
  },
  ...
]
```

**TXT output structure:**

```
intitle:"index of" passwd
inurl:admin/password
filetype:env DB_PASSWORD
...
```

### 4. Filter by Category

You can filter by **category name** (partial, case-insensitive match) or **numeric ID**:

```bash
# By name (partial match — matches "Files Containing Passwords")
atdork --ghdb-scraper --ghdb-categories password --ghdb-file dorks/passwords.txt

# By numeric ID
atdork --ghdb-scraper --ghdb-categories 9 --ghdb-file dorks/passwords.txt

# Combine multiple categories
atdork --ghdb-scraper --ghdb-categories password,login,footholds --ghdb-file dorks/recon.txt

# Mix names and IDs
atdork --ghdb-scraper --ghdb-categories 9,12,juicy --ghdb-file dorks/combined.txt
```

**Category name matching is partial and case-insensitive** — `password` matches `Files Containing Passwords`, `pass` would also match. Use the full category title for precision.

### 5. Filter by Year

Filter dorks by their publication date on Exploit-DB:

```bash
# Single year
atdork --ghdb-scraper --ghdb-years 2024 --ghdb-file dorks/2024.txt

# Multiple years (comma-separated)
atdork --ghdb-scraper --ghdb-years 2022,2024 --ghdb-file dorks/recent.txt

# Range (inclusive)
atdork --ghdb-scraper --ghdb-years 2020-2023 --ghdb-file dorks/2020s.txt

# Combination of single years and ranges
atdork --ghdb-scraper --ghdb-years 2018,2020-2022,2024 --ghdb-file dorks/custom.txt
```

If a range is reversed (e.g., `2024-2020`), AtDork automatically swaps the bounds.

### 6. Combine Category + Year Filters

```bash
# Password-related dorks published in 2023 or 2024
atdork --ghdb-scraper \
  --ghdb-categories password \
  --ghdb-years 2023-2024 \
  --ghdb-file dorks/passwords_recent.json
```

Filters are applied with **AND logic** — a dork must match both the category filter AND the year filter to be included.

### 7. Limit the Number of Dorks

```bash
# Get only the first 60 dorks (after filtering)
atdork --ghdb-scraper --ghdb-r 60 --ghdb-file dorks/sample.txt
```

The limit is applied **after** all filters — you get up to N dorks from the filtered set, in the order returned by Exploit-DB.

### 8. Complete Example: Refresh Local Database

A common workflow is to refresh your local dork collection weekly:

```bash
# 1. Scrape the latest dorks, organized by category
mkdir -p dorks/weekly
atdork --ghdb-scraper --ghdb-categories 1 --ghdb-file dorks/weekly/01_footholds.txt
atdork --ghdb-scraper --ghdb-categories 3 --ghdb-file dorks/weekly/03_sensitive_directories.txt
atdork --ghdb-scraper --ghdb-categories 9 --ghdb-file dorks/weekly/09_passwords.txt

# 2. Use them with the Database Dork feature
atdork --database-path dorks/weekly --database-dork 01_footholds --database-r 20 -r 10
```

---

## How It Works

### The AJAX Endpoint

The scraper does **not** parse HTML — it calls the same JSON endpoint that the GHDB web page uses internally:

```
GET https://www.exploit-db.com/google-hacking-database
Headers:
  Accept: application/json, text/javascript, */*; q=0.01
  X-Requested-With: XMLHttpRequest
  User-Agent: Mozilla/5.0 ... (Chrome 126)
```

Exploit-DB's server returns a JSON payload shaped like DataTables' response:

```json
{
  "recordsTotal": 7940,
  "data": [
    {
      "id": "5052",
      "date": "2022-03-14",
      "url_title": "<a href=\"/ghdb/5052\">intitle:\"index of\" passwd</a>",
      "category": {
        "cat_id": "9",
        "cat_title": "Files Containing Passwords"
      }
    },
    ...
  ]
}
```

The scraper parses this JSON, extracts the dork text from the `url_title` HTML fragment using BeautifulSoup, normalizes the structure, and applies filters.

### Retry Strategy

The fetcher retries up to **3 times** with random delays between 1–3 seconds. If an SSL handshake fails, it retries once with certificate verification disabled (`verify=False`) and silences the urllib3 warning. This handles common transient issues like:

- Exploit-DB rate limiting
- Temporary SSL certificate mismatches
- Network timeouts
- Cloudflare challenges (sometimes retried successfully)

### Dork Text Extraction

The raw `url_title` field is an HTML anchor:

```html
<a href="/ghdb/5052">intitle:"index of" passwd</a>
```

The scraper extracts only the text content (`intitle:"index of" passwd`) using BeautifulSoup, ensuring the saved dork is clean and ready to use as a search query.

### Filter Logic

Filters are applied in this order:

1. **Category filter** (`--ghdb-categories`) — keeps dorks whose `cat_id` matches a provided ID, OR whose `cat_title` contains any provided name (case-insensitive partial match)
2. **Year filter** (`--ghdb-years`) — keeps dorks whose `year` is in the provided set
3. **Limit** (`--ghdb-r`) — keeps the first N dorks from the filtered list

Filters use AND logic between categories and years.

### Output Format Detection

The output format is determined by the file extension:

| Extension | Format | Content |
|-----------|--------|---------|
| `.json` | JSON array | Each entry: `{text, id, date, cat_id, cat_title}` |
| `.txt` (or anything else) | Plain text | One dork per line, no metadata |

---

## Integration with Other Features

The GHDB Scraper is a **collect-only** tool — it does not execute searches. To actually run the scraped dorks, pipe them through AtDork's batch system:

### Pattern 1: Scrape → Save → Execute

```bash
# 1. Scrape and save
atdork --ghdb-scraper --ghdb-categories password --ghdb-file dorks/passwords.txt

# 2. Execute the saved dorks as a batch
atdork --batch-file dorks/passwords.txt -r 10 --concurrency 3 --verbose
```

### Pattern 2: Scrape → Database Dork → Execute

```bash
# 1. Scrape into your database directory
atdork --ghdb-scraper --ghdb-categories 9 --ghdb-file database/09_passwords_fresh.txt

# 2. Use Database Dork feature to load and execute
atdork --database-dork 09_passwords_fresh --database-r 30 -r 10
```

### Pattern 3: Scrape → Manual Curation → Execute

```bash
# 1. Scrape everything from 2024
atdork --ghdb-scraper --ghdb-years 2024 --ghdb-file dorks/2024_all.txt

# 2. Manually edit the file (remove irrelevant dorks, add your own)

# 3. Run the curated list
atdork --batch-file dorks/2024_all.txt -r 15 --output-dir results/2024/
```

---

## Scraping vs. Bundled Database

| Aspect | GHDB Scraper (`--ghdb-scraper`) | Database Dork (`--database-dork`) |
|--------|----------------------------------|-----------------------------------|
| **Source** | Live HTTP fetch from exploit-db.com | Bundled `.txt` files in the package |
| **Network** | Required | Not required |
| **Freshness** | Always latest | Snapshot from last package release |
| **Speed** | Slow (network + retries) | Fast (local file read) |
| **Filtering** | By category and year at fetch time | By file selection and `--database-r` |
| **Output** | Saves dorks to file | Loads dorks into the batch runner |
| **Use case** | Refresh dork collection, get latest | Run scans offline, reproducibility |

**Recommended workflow:**

1. Use `--ghdb-scraper` weekly/monthly to refresh your local dork collection
2. Save the scraped dorks into `database/*.txt` (or a custom path)
3. Use `--database-dork` for daily scanning — it's faster and works offline

---

## Troubleshooting

### "Gagal mengambil data GHDB. Cek koneksi atau coba lagi nanti."

```
❌ Gagal mengambil data GHDB. Cek koneksi atau coba lagi nanti.
```

**Cause:** The scraper could not fetch data after 3 retries. Common reasons:

- No internet connection
- Exploit-DB is down or rate-limiting you
- A firewall is blocking requests to `exploit-db.com`
- Cloudflare is challenging your request

**Fix:**

1. Test connectivity: `curl -I https://www.exploit-db.com/google-hacking-database`
2. Wait a few minutes and retry (rate limits usually clear quickly)
3. If behind a corporate proxy, set `HTTPS_PROXY` env var before running
4. As a fallback, use the bundled database: `atdork --list-database-dork`

### "Response bukan JSON valid (kemungkinan diblokir / format berubah)"

**Cause:** Exploit-DB returned HTML instead of JSON — usually a Cloudflare challenge page or a CAPTCHA.

**Fix:**

1. Open `https://www.exploit-db.com/google-hacking-database` in a browser
2. If you see a Cloudflare challenge, solve it once to whitelist your IP
3. Retry the scraper immediately after

### "Tidak ada dork yang cocok dengan filter yang diberikan"

**Cause:** Your filter combination returned zero matches.

**Fix:**

1. Run `atdork --ghdb-list-categories` to verify category names and IDs
2. Check your year range — Exploit-DB dorks date back to the early 2000s, but recent years have more entries
3. Loosen the filter (e.g., use `password` instead of `passwords`, or `2020-2024` instead of `2024`)

### Scraper succeeds but returns fewer dorks than expected

**Cause:** This is usually correct behavior — the `recordsTotal` field reflects all dorks on Exploit-DB, but the `data` array may be paginated or filtered by the server.

**Fix:** The scraper fetches a single page (the same one the web UI shows by default). To get all dorks, save to a file and combine with the bundled database:

```bash
atdork --ghdb-scraper --ghdb-file dorks/fresh.txt
# Combine with bundled
cat database/09_files_containing_passwords.txt dorks/fresh.txt | sort -u > combined.txt
```

---

## Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Success (dorks fetched and optionally saved) |
| `1` | Failure (network error, invalid filter, write error, etc.) |

---

## Environment Variables

The scraper uses the `requests` library, which respects standard proxy environment variables:

| Variable | Purpose |
|----------|---------|
| `HTTP_PROXY` | Proxy for HTTP requests |
| `HTTPS_PROXY` | Proxy for HTTPS requests (recommended for Exploit-DB) |
| `NO_PROXY` | Comma-separated hosts to bypass the proxy |

Example:

```bash
export HTTPS_PROXY=http://corporate-proxy:8080
atdork --ghdb-scraper --ghdb-file dorks.txt
```

---

## Rate Limiting & Ethical Use

- The scraper sends **one HTTP request per invocation** (no pagination loop), so it's gentle on Exploit-DB's infrastructure
- Retries use random delays (1–3 seconds) to avoid looking like a burst attack
- The User-Agent mimics a real browser to reduce the chance of being blocked
- If you script automated runs, **keep frequency reasonable** — once per day or week is more than enough
- Always respect Exploit-DB's terms of service

---

## See Also

- [Database Dork](./database-scrapper.md) — for loading bundled dorks offline
- [Batch Processing](./batch-processing.md) — for executing scraped dorks as a batch
- [Template System](./template-system.md) — for YAML-based curated dork collections
- [Output Formats](./output-formats.md) — for saving scrape results in different formats
