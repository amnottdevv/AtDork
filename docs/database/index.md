# Dork Database (Atdork-DB)

AtDork ships **code only** — the dork data lives in the separate
**[Atdork-DB](https://github.com/amnottdevv/Atdork-DB)** repository, which the
built-in package manager treats like a package registry.

| | |
| :--- | :--- |
| **Packages** | 123 dork files |
| **Folders** | 31 themed `@folders` |
| **Dorks** | 994,603 unique queries |
| **Refresh** | GHDB re-synced weekly by CI |

---

## 🔎 Browse the web catalog

**→ [https://amnottdevv.github.io/Atdork-DB/](https://amnottdevv.github.io/Atdork-DB/)**

The web catalog is the visual index of everything below:

- **Instant search** across every package (`s3`, `shodan`, `cve`, `discord`, …)
- **`@folder` filter chips** — click a category to see only its packages
- **Detail pages per package** — preview of the first lines, dork count, size,
  `sha256`, raw download, and every other package in the same folder
- **One-click install commands** — copy `atdork install <ref>` straight from the table

Every folder has its own README in the repository (generated into the catalog)
and a folder page in the catalog, e.g.
[@shodan](https://amnottdevv.github.io/Atdork-DB/#/f/shodan),
[@cms](https://amnottdevv.github.io/Atdork-DB/#/f/cms),
[@github](https://amnottdevv.github.io/Atdork-DB/#/f/github).

---

## 5-minute workflow

### 0. One-time setup — clone the data repo

AtDork looks for an Atdork-DB checkout in this order
(`--db-repo` → env `ATDORK_DB_REPO` → config `db_repo` → `~/Atdork-DB` →
sibling of the AtDork checkout → `./Atdork-DB`):

```bash
git clone https://github.com/amnottdevv/Atdork-DB.git ~/Atdork-DB
```

Skip this entirely with Docker — the image bundles the database
(see [Docker](../docker.md)).

### 1. Search the index

```bash
atdork search cve            # find packages mentioning "cve"
atdork search shodan         # all Shodan packages
atdork index                 # full package listing (ref | dorks | size | description)
```

### 2. Install packages

```bash
atdork install @cve/cve_1.txt      # canonical ref: folder + file
atdork install c@cve_1.txt         # shorthand (unique folder prefix)
atdork install @ghdb               # whole folder
atdork installed                   # what's in my store (~/.atdork/packages)?
```

### 3. Run them as queries

```bash
# Load an installed package (or any ref straight from Atdork-DB) as batch dorks
atdork --batch-file c@cve_1.txt -r 20

# Or load directly from the database root
atdork --database-dork @cve/cve_1.txt -r 20
atdork --database-dork @ghdb/01_footholds --database-preview   # show, don't run
atdork --database-dork @cms --database-r 50 --database-seed 7  # random 50 from the folder
```

### 4. Keep data fresh

```bash
atdork update     # git pull --ff-only on the Atdork-DB checkout
```

---

## Package ref grammar

| Ref | Meaning |
| :--- | :--- |
| `@cve/cve_1.txt` | Canonical — folder + file |
| `c@cve_1.txt` | Shorthand — unique folder prefix (`c` → `@cve`) |
| `cve_1.txt` | Bare file name (must be unique across the index) |
| `@cve` | Whole folder (install/uninstall, or load all `.txt` with `--database-dork`) |
| `@cve, @lfi` | Multiple refs, comma-separated |

Lines starting with `#` in any dork file are comments and are skipped by the
loader.

---

## All folders

Browse any folder in the [web catalog](https://amnottdevv.github.io/Atdork-DB/)
(click a name for its live folder page):

| Folder | Packages | Dorks | Theme |
| :--- | ---: | ---: | :--- |
| [`@crypto`](https://amnottdevv.github.io/Atdork-DB/#/f/crypto) | 9 | 637,139 | Crypto/BTC themed harvested sets |
| [`@targets`](https://amnottdevv.github.io/Atdork-DB/#/f/targets) | 7 | 11,596 | Domain lists for `site:` scoping |
| [`@movie`](https://amnottdevv.github.io/Atdork-DB/#/f/movie) | 3 | 91,733 | Open directory movie listings |
| [`@network`](https://amnottdevv.github.io/Atdork-DB/#/f/network) | 2 | 99,175 | Direct-IP access & server detection |
| [`@google`](https://amnottdevv.github.io/Atdork-DB/#/f/google) | 6 | 33,423 | Classic large Google dork collections |
| [`@gaming`](https://amnottdevv.github.io/Atdork-DB/#/f/gaming) | 5 | 30,329 | Gaming marketplaces & items |
| [`@cms`](https://amnottdevv.github.io/Atdork-DB/#/f/cms) | 5 | 27,678 | WordPress, Joomla, Magento, Laravel |
| [`@shopping`](https://amnottdevv.github.io/Atdork-DB/#/f/shopping) | 3 | 11,152 | Shop parameter dorks |
| [`@cloud`](https://amnottdevv.github.io/Atdork-DB/#/f/cloud) | 6 | 10,690 | S3/Azure/GCP buckets |
| [`@carding`](https://amnottdevv.github.io/Atdork-DB/#/f/carding) | 2 | 3,266 | E-commerce checkout parameters |
| [`@shodan`](https://amnottdevv.github.io/Atdork-DB/#/f/shodan) | 7 | 3,712 | Shodan queries & filters |
| [`@lfi`](https://amnottdevv.github.io/Atdork-DB/#/f/lfi) | 1 | 7,322 | Local File Inclusion parameters |
| [`@ghdb`](https://amnottdevv.github.io/Atdork-DB/#/f/ghdb) | 15 | 7,976 | Exploit-DB GHDB, weekly refresh |
| [`@rfi`](https://amnottdevv.github.io/Atdork-DB/#/f/rfi) | 1 | 2,866 | Remote File Inclusion parameters |
| [`@duckduckgo`](https://amnottdevv.github.io/Atdork-DB/#/f/duckduckgo) | 2 | 1,848 | DDG-tuned dorks |
| [`@common`](https://amnottdevv.github.io/Atdork-DB/#/f/common) | 5 | 1,627 | SQLi/LFI/XSS/RCE/debug classes |
| [`@iot`](https://amnottdevv.github.io/Atdork-DB/#/f/iot) | 4 | 1,370 | Cameras & embedded UIs |
| [`@admin`](https://amnottdevv.github.io/Atdork-DB/#/f/admin) | 2 | 462 | Admin login discovery |
| [`@github`](https://amnottdevv.github.io/Atdork-DB/#/f/github) | 5 | 819 | GitHub secret hunting |
| [`@exploit-db`](https://amnottdevv.github.io/Atdork-DB/#/f/exploit-db) | 15 | 6,229 | Exploit-DB categories mirror |
| [`@bing`](https://amnottdevv.github.io/Atdork-DB/#/f/bing) | 2 | 505 | Bing-only operators |
| [`@bug-bounty`](https://amnottdevv.github.io/Atdork-DB/#/f/bug-bounty) | 2 | 105 | Program & disclosure discovery |
| [`@sensitive`](https://amnottdevv.github.io/Atdork-DB/#/f/sensitive) | 5 | 3,160 | Exposed logs, hidden files |
| [`@censys`](https://amnottdevv.github.io/Atdork-DB/#/f/censys) | 1 | 221 | Censys ICS/service queries |
| [`@vuln`](https://amnottdevv.github.io/Atdork-DB/#/f/vuln) | 1 | 112 | Banner-based vuln discovery |
| [`@virustotal`](https://amnottdevv.github.io/Atdork-DB/#/f/virustotal) | 1 | 34 | VT Intelligence queries |
| [`@cve`](https://amnottdevv.github.io/Atdork-DB/#/f/cve) | 1 | 14 | CVE reference hunting |
| [`@yandex`](https://amnottdevv.github.io/Atdork-DB/#/f/yandex) | 1 | 10 | Cyrillic keyword dorks |
| [`@social`](https://amnottdevv.github.io/Atdork-DB/#/f/social) | 2 | 19 | Discord/LinkedIn dorks |
| [`@onion`](https://amnottdevv.github.io/Atdork-DB/#/f/onion) | 1 | 9 | Dark web (.onion) discovery |
| [`@test`](https://amnottdevv.github.io/Atdork-DB/#/f/test) | 1 | 2 | Reference-syntax demo |

---

## Category guides

Deep-dive pages for the most-used categories:

- [CMS Dorks](cms-dorks.md) — WordPress, Joomla, Magento, Laravel
- [Common Dorks](common-dorks.md) — SQLi / LFI / XSS / RCE classes
- [GitHub Secret-Exposure Dorks](github-dorks.md) — auditing your own repos
- [LFI Dorks](lfi-dorks.md) & [RFI Dorks](rfi-dorks.md) — file inclusion
- [Bing & DuckDuckGo Dorks](bing-and-ddg.md) — engine-specific operators
- [Censys Dorks](censys-dorks.md) — infrastructure & ICS discovery
- [Bug Bounty Dorks](bug-bounty-dorks.md) — finding in-scope programs

Also see the [Package Manager feature page](../features/package-manager.md)
for ref resolution, the store layout and `--db-repo` details, and
[Docker](../docker.md) for running everything in a container.

---

## ⚠️ Ethical use

The database is a collection of **search queries**, not of compromised data.
Use them only against targets you own or are explicitly authorized to test
(see each category page's disclaimer), and report findings responsibly.
