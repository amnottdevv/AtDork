
# Database & History

## Introduction
AtDork can persistently store all queries and their results in a SQLite database. This enables **resuming interrupted batches**, viewing **search history**, **deduplication** across sessions, and **exporting** everything to JSON/CSV for reporting and analysis.

## Functions
| Flag | Description | Default |
|------|-------------|---------|
| `--db-path PATH` | Database file path. | `atdork.db` |
| `--resume` | Continue a previously interrupted batch (re‑runs queries with `pending` or `failed` status). | |
| `--history` | Display a list of all previously executed queries with their status. | |
| `--no-dedup` | Disable global URL deduplication. By default, duplicate URLs across queries are skipped. | |
| `--export-db PATH` | Export the entire database to a JSON or CSV file (format is guessed from the file extension). | |

## Usage Examples
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

# Use a custom database location and view history
atdork --db-path /secure/path/atdork.db --history
```

## How It Works

1. **Database Structure**  
   The `Database` class (from `core/database.py`) creates two tables:
   - `queries` – stores each unique query text, its status (`pending`, `running`, `completed`, `failed`), and timestamps.
   - `results` – stores individual search results (title, URL, snippet, and raw JSON). A `UNIQUE(query_id, href)` constraint prevents duplicate URLs for the same query.

2. **During a Search**  
   - Every query is inserted (or updated) with status `pending`, then set to `completed` (or `failed`) after execution.
   - Each result is inserted individually. If the same URL already exists for that query, the row is ignored – this is the built‑in **deduplication**.
   - Use `--no-dedup` to force all results to be stored, even if they are duplicates.

3. **Resuming a Batch**  
   - `--resume` reads all queries with status `pending` or `failed` from the database.
   - Those queries are re‑executed, and their status is updated accordingly. Completed queries are skipped.
   - This allows you to recover from a crash or an intentional pause without repeating work.

4. **Search History**  
   - `--history` simply prints a table of all queries stored in the database, along with their status and timestamps. It gives you an overview of past activity.

5. **Exporting Data**  
   - `--export-db <file>` joins the `queries` and `results` tables and writes:
     - A **JSON** file containing a dictionary `{query_text: [results]}`, or
     - A **CSV** file with columns `query_text, title, href, body`.
   - The format is auto‑detected from the file extension.

6. **Thread Safety**  
   The database uses SQLite’s WAL (Write‑Ahead Logging) mode and proper locking, so it is safe for concurrent access during multi‑threaded batch processing.

This persistent storage makes AtDork suitable for long‑running engagements, audit trails, and professional reporting.
