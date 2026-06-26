\# Cache System



\## Introduction

The Cache System stores search results locally in a SQLite database, preventing redundant requests to search engines, reducing bandwidth usage, and enabling \*\*offline access\*\* to previously fetched results.



\## Functions

| Flag | Description | Default |

|------|-------------|---------|

| `--cache` | Enable caching. Every search result is saved and served from cache when available. | |

| `--cache-only` | Only use cached results; never contact search engines. | |

| `--cache-ttl N` | Time‑to‑live in hours. Cached entries older than this are ignored. | 24 |

| `--clear-cache` | Delete all cached entries before starting the session. | |

| `--cache-db PATH` | Specify a custom cache database file. | `atdork\_cache.db` |



\## Usage Examples

```bash

\# Cache all search results for 48 hours

atdork -q "site:gov filetype:pdf" -r 20 --cache --cache-ttl 48



\# Use only cached data (offline mode)

atdork -q "site:gov filetype:pdf" -r 20 --cache-only



\# Clear old cache and start fresh

atdork --clear-cache



\# Use a custom cache location

atdork -q "test" --cache --cache-db /path/to/my\_cache.db

```



\## How It Works



1\. \*\*Initialization\*\*  

&#x20;  When any cache flag is used, a `SearchCache` object is created. It opens (or creates) a SQLite database file (`atdork\_cache.db` by default) and ensures the `api\_cache` table exists. Expired entries are automatically removed on startup.



2\. \*\*Cache Write\*\*  

&#x20;  After a successful search, the query, backend engine, normalized parameters, and the result list are stored as a new row. The `expires\_at` column is set to the current time plus the TTL (in hours). If a row with the same query, engine, and parameters already exists, it is updated (upsert).



3\. \*\*Cache Read\*\*  

&#x20;  Before performing a search, AtDork checks the cache for an exact match:

&#x20;  - Query string

&#x20;  - Backend engine

&#x20;  - Normalized parameters (region, safesearch, timelimit, max\_results)  

&#x20;  If a non‑expired row is found, the cached results are returned immediately without contacting any search engine. The `hit\_count` and `last\_accessed` fields are updated.



4\. \*\*Cache‑Only Mode\*\*  

&#x20;  When `--cache-only` is active, AtDork \*\*only\*\* looks up the cache. If no valid cache entry exists, it returns zero results without making any network request.



5\. \*\*Cache Clearing\*\*  

&#x20;  `--clear-cache` deletes every row from the `api\_cache` table before the session begins, forcing fresh data to be fetched.



6\. \*\*Cache Statistics\*\*  

&#x20;  The `get\_stats()` method provides a summary of total entries, expired entries, total hits, and a list of engines that have cached data.



The cache key is built from the query, engine, and a sorted JSON representation of the search parameters, ensuring consistent and collision‑free lookups.

