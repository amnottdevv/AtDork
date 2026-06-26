# Output Formats

## Introduction

AtDork provides flexible output options to suit different workflows and integration needs. Whether you need a quick terminal view, a structured JSON file for programmatic processing, or a CSV for spreadsheet analysis, AtDork has you covered.

Results can be exported in multiple formats, stored in a SQLite database for history and deduplication, and saved either as a single file or per-query files.

---

## What It Does

| Feature | Description |
|---------|-------------|
| **Terminal Output** | Beautiful formatted display with colors and snippets |
| **JSON Export** | Structured format for programmatic processing |
| **CSV Export** | Spreadsheet-friendly format for analysis |
| **TXT Export** | Human-readable plain text format |
| **SQLite Database** | Local database for history, resume, and deduplication |
| **Database Export** | Export entire database to JSON or CSV |
| **Deduplication** | Automatically remove duplicate URLs |
| **Snippet Control** | Show or hide result snippets |

---

## How to Use

### Terminal Output (Default)

```bash
atdork -q "site:gov filetype:pdf" -r 10
```

**Output:**
```
[1] Government Report 2024
   URL: https://example.gov/report.pdf
   Cuplikan: This report contains...
   ──────────────────────────────────────────────────
[2] Budget Document 2024
   URL: https://example.gov/budget.pdf
   Cuplikan: The budget for 2024...
   ──────────────────────────────────────────────────
Total: 10 results
```

### Hide Snippets in Terminal

```bash
atdork -q "site:gov filetype:pdf" -r 10 --no-snippet
```

### Save to JSON

```bash
atdork -q "site:gov filetype:pdf" -r 10 --format json -o results.json
```

### Save to CSV

```bash
atdork -q "site:gov filetype:pdf" -r 10 --format csv -o results.csv
```

### Save to TXT

```bash
atdork -q "site:gov filetype:pdf" -r 10 --format txt -o results.txt
```

### Batch with Separate Output Files

```bash
atdork --batch-file dorks.txt -r 30 --format json --output-dir ./results/
```

### Batch with Single Output File

```bash
atdork --batch-file dorks.txt -r 30 --format json -o batch_results.json
```

### Disable Deduplication (Keep All Results)

```bash
atdork -q "site:example.com" -r 50 --no-dedup -o all_results.json
```

### View Search History

```bash
atdork --history
```

### Export Database to JSON

```bash
atdork --export-db all_results.json
```

### Export Database to CSV

```bash
atdork --export-db all_results.csv
```

---

## How It Works

### 1. Output Processing Flow

```
1. User provides query and output options
   ↓
2. AtDork executes search
   ↓
3. Results are validated and filtered
   ↓
4. Deduplication (if enabled):
   ├─ Check database for existing URLs
   └─ Remove duplicate results
   ↓
5. Results are stored in SQLite database
   ↓
6. Output is generated:
   ├─ Terminal: display results
   ├─ File: save in requested format
   └─ Database: store for history/resume
```

### 2. Output Formats

| Format | File Extension | Structure | Best For |
|--------|----------------|-----------|----------|
| **TXT** | `.txt` | Human-readable with headers | Quick manual review |
| **JSON** | `.json` | Structured key-value pairs | Programmatic processing |
| **CSV** | `.csv` | Tabular format | Spreadsheet analysis |

### 3. File Structure Examples

**JSON Output:**
```json
[
  {
    "title": "Government Report 2024",
    "href": "https://example.gov/report.pdf",
    "body": "This report contains detailed information..."
  },
  {
    "title": "Budget Document 2024",
    "href": "https://example.gov/budget.pdf",
    "body": "The budget for 2024 includes..."
  }
]
```

**CSV Output:**
```csv
title,href,body
"Government Report 2024","https://example.gov/report.pdf","This report contains detailed information..."
"Budget Document 2024","https://example.gov/budget.pdf","The budget for 2024 includes..."
```

**TXT Output:**
```
Dork Scanner Results
Query: site:gov filetype:pdf
Timestamp: 2026-06-25 14:30:00
Total: 2 results

[1] TITLE: Government Report 2024
    URL: https://example.gov/report.pdf
    SNIPPET: This report contains detailed information...
--------------------------------------------------------------------------------
[2] TITLE: Budget Document 2024
    URL: https://example.gov/budget.pdf
    SNIPPET: The budget for 2024 includes...
--------------------------------------------------------------------------------
```

### 4. Database Schema

**Queries Table:**
```sql
CREATE TABLE IF NOT EXISTS queries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    query_text TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

**Results Table:**
```sql
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

### 5. Deduplication Logic

```
1. For each result, extract URL (href)
   ↓
2. Check database for existing href
   ↓
3. If href exists → skip this result
   ↓
4. If href is new → insert into database
   ↓
5. Only new results are included in output
```

**Disable Deduplication:**
```bash
atdork -q "test" --no-dedup
```

### 6. Database Export

**Export to JSON:**
```bash
atdork --export-db all_results.json
```

**Export to CSV:**
```bash
atdork --export-db all_results.csv
```

**Database Export Structure:**
```json
{
  "1": [
    {"title": "...", "href": "...", "body": "..."},
    {"title": "...", "href": "...", "body": "..."}
  ],
  "2": [
    {"title": "...", "href": "...", "body": "..."}
  ]
}
```

### 7. Per-Query Output Files

When using `--output-dir`, each query gets its own file:

```
results/
├── site_gov_filetype_pdf.json
├── site_edu_filetype_xls.json
├── inurl_admin_login.json
└── intitle_index_of_backup.json
```

**File Naming:**
- Special characters are replaced with underscores
- Filename is truncated to 50 characters
- Extension matches `--format` (default: `.txt`)

---

## Full Flag Reference

| Flag | Description | Default |
|------|-------------|---------|
| `-o, --output` | Save all results to single file | None |
| `--output-dir` | Save each query to separate file | None |
| `--format` | Output format: `txt`, `json`, `csv` | `txt` |
| `--no-snippet` | Hide snippets in terminal | Disabled |
| `--verbose`, `-v` | Show results in batch mode | Disabled |
| `--no-dedup` | Disable URL deduplication | Disabled |
| `--export-db` | Export database to file (json/csv) | None |
| `--history` | Show search history | Disabled |
| `--db-path` | SQLite database path | `atdork.db` |

---

## Real-World Use Cases

### 1. Generate JSON Report for Processing

```bash
atdork --template sqli,xss,lfi --target target.com \
  --format json -o recon_results.json
```

### 2. Create CSV for Spreadsheet Analysis

```bash
atdork --batch-file dorks.txt -r 30 --format csv -o analysis.csv
```

### 3. Batch with Separate Files for Each Query

```bash
atdork --batch-file dorks.txt -r 20 --format json --output-dir ./reports/
```

### 4. View History and Export Database

```bash
# View history
atdork --history

# Export all data
atdork --export-db all_results.json
```

### 5. Quick Terminal View with Snippets

```bash
atdork -q "site:gov filetype:pdf" -r 10 -v
```

### 6. Export Database for Weekly Reporting

```bash
atdork --export-db weekly_report_$(date +\%Y-\%m-\%d).json
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| **File not saved** | Check `--output` path has write permissions |
| **JSON parsing errors** | Ensure output is valid JSON (use `jq` to validate) |
| **CSV columns misaligned** | Check field names in `--format csv` |
| **Too many duplicate results** | Use `--no-dedup` to keep all results |
| **Database locked** | Close other AtDork instances, delete `atdork.db` |
| **History empty** | Ensure `--db-path` points to correct database |
| **Export database fails** | Check path has write permissions |

---

## Output Structure Examples

### Terminal Output (Default)

```
Hasil untuk: site:gov filetype:pdf

1. Government Report 2024
   URL: https://example.gov/report.pdf
   Cuplikan: This report contains detailed information...
   ──────────────────────────────────────────────────
2. Budget Document 2024
   URL: https://example.gov/budget.pdf
   Cuplikan: The budget for 2024 includes...
   ──────────────────────────────────────────────────
Total: 10 results
```

### JSON Output
```json
[
  {
    "title": "Government Report 2024",
    "href": "https://example.gov/report.pdf",
    "body": "This report contains detailed information..."
  }
]
```

### CSV Output
```csv
title,href,body
"Government Report 2024","https://example.gov/report.pdf","This report contains detailed information..."
```

### TXT Output
```
Dork Scanner Results
Query: site:gov filetype:pdf
Timestamp: 2026-06-25 14:30:00
Total: 2 results

[1] TITLE: Government Report 2024
    URL: https://example.gov/report.pdf
    SNIPPET: This report contains detailed information...
--------------------------------------------------------------------------------
```