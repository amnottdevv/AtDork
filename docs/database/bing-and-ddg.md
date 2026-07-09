# Bing & DuckDuckGo Dorks (`database/bing/`, `database/ddg/`)

Bing and DuckDuckGo support several search operators that Google doesn't
(or supports differently). This page covers what's unique about each engine
and how the bundled dork files use those operators.

```
database/
├── bing/
│   ├── bing1.txt   # OR groups & contains:
│   └── bing2.txt   # location:, ip:, domain:, linkfromdomain:, language:, feed:, prefer:
└── ddg/
    └── ddg1.txt     # Verbatim error strings, !bang shortcuts, OR combos
```

Run these with `--backend bing` or `--backend duckduckgo` so AtDork sends the
query to the right engine:

```bash
atdork --database-dork bing/bing1 --backend bing -r 20
atdork --database-dork ddg/ddg1 --backend duckduckgo -r 20
```

---

## Bing vs DuckDuckGo at a glance

| Aspect | Bing | DuckDuckGo |
|--------|------|------------|
| Unique operators | `contains:`, `loc:`/`location:`, `ip:`, `domain:`, `linkfromdomain:`, `language:`, `feed:`, `prefer:` | `!bang` (14,000+ shortcuts), `\` (jump to first result), `!doodles`, `!safeoff` |
| `OR` grouping | Full support with `()`, e.g. `inurl:(A OR B)` | No `()` grouping — use plain `OR` or `" "` |
| File search | `contains:` — pages that *link to* a file type | `filetype:` — same as Google |
| Location filter | `loc:Indonesia` | Not available — use `site:.id` instead |
| IP search | `ip:8.8.8.8` — all sites on that host | Not available |
| Tracking | Standard | No tracking by default |

---

## 1. Bing — exclusive operators

| Operator | Purpose | Example |
|----------|---------|---------|
| `contains:` | Find pages that **link to** a given file type | `contains:sql site:.id` |
| `loc:` / `location:` | Filter by geographic location | `location:Indonesia inurl:?id=` |
| `ip:` | Find every site hosted on one IP (shared hosting) | `ip:103.8.12.100` |
| `domain:` | Domain match, more precise than `site:` | `domain:go.id` |
| `linkfromdomain:` | Pages linked *from* a given domain | `linkfromdomain:target.com inurl:admin` |
| `language:` | Filter by content language | `language:indonesian inurl:?q=` |
| `feed:` | Find RSS/Atom feeds | `feed:target.com` |
| `prefer:` | Boost weight of a keyword | `prefer:mysql inurl:?id=` |
| `inurl:(A OR B)` | Grouped OR | `inurl:(?id= OR ?page=)` |

### `bing1.txt` — sample entries (OR groups & `contains:`)

```text
inurl:(product.php?id= OR view.php?id= OR detail.php?id=)
inurl:(?page= OR ?file= OR ?path=)
inurl:(?cmd= OR ?command= OR ?exec=)
contains:sql inurl:backup
contains:.env site:.id
contains:(sql OR zip OR rar) inurl:backup
site:.go.id contains:sql
contains:sql -demo -test -example
```

### `bing2.txt` — sample entries (advanced operators)

```text
location:Indonesia inurl:?id=
ip:103.8.12.100 inurl:?id=
domain:go.id inurl:?id=
linkfromdomain:target.com inurl:admin
language:indonesian inurl:?q=
feed:target.com
prefer:mysql inurl:?id= intext:"Warning"
location:Indonesia domain:go.id inurl:?id= contains:sql
```

**Usage:**

```bash
atdork --database-dork bing/bing1 --backend bing --database-r 15
atdork --database-dork bing/bing2 --backend bing --database-preview
```

---

## 2. DuckDuckGo — exclusive features

| Feature | Purpose | Example |
|---------|---------|---------|
| `!bang` | Jump straight into a specific site's own search (14,000+ shortcuts) | `!github "Error in lines :"` |
| `\` | Go directly to the first result | `\ site:.id "Error in lines :"` |
| `!doodles` | Browse the Google Doodles archive | `!doodles` |
| `!safeoff` | Disable SafeSearch for one query | `!safeoff "Error"` |

Standard operators (`site:`, `intitle:`, `inurl:`, `filetype:`, `" "`, `-`, `OR`)
work the same as Google.

### `ddg1.txt` — sample entries

```text
"Error in your SQL syntax"
"Warning: mysql_fetch_array"
"failed to open stream: No such file"
"Warning: system()"
"PHP Version" inurl:phpinfo.php
"DB_PASSWORD" filetype:env
"INSERT INTO" filetype:sql
intitle:"Index of" "backup"
site:.go.id "Error in lines :"
!github "DB_PASSWORD" filetype:env
!pastebin "Error in your SQL syntax"
"Error in lines :" OR "Warning: mysql" site:.go.id
\ "phpinfo.php" inurl:phpinfo.php
"Error" -demo -test -example
```

**Usage:**

```bash
atdork --database-dork ddg/ddg1 --backend duckduckgo --database-r 20
```

---

## Dork examples by category

| Category | Bing | DuckDuckGo |
|----------|------|------------|
| SQL Injection | `inurl:(product.php?id= OR view.php?id=) site:.go.id` | `"Error in lines :" site:.id` |
| LFI / File Inclusion | `inurl:(?page= OR ?file=) contains:passwd site:.id` | `"failed to open stream: No such file" inurl:?page=` |
| XSS | `inurl:(?q= OR ?search=) intext:"<script>"` | `"<script>alert" site:.id` |
| RCE / Command Injection | `inurl:(?cmd= OR ?exec=) intext:"Warning: system"` | `"Warning: system()" inurl:?cmd=` |
| File Upload | `inurl:upload.php intext:"failed to move"` | `"failed to move uploaded file" site:.id` |
| Config & Secrets | `contains:.env site:.id` | `"DB_PASSWORD" filetype:env site:.id` |
| Database Dump | `contains:sql inurl:backup site:.id` | `"INSERT INTO" filetype:sql site:.id` |
| Admin Panel | `linkfromdomain:target.com inurl:admin` | `site:.id "admin" "login"` |

---

## ⚠️ Disclaimer & Legal Notice

These dorks are intended **only** for:

1. Security testing on websites/servers you own.
2. Official Bug Bounty programs with explicit written authorization from the target owner.
3. Academic/educational security research in a controlled environment (university labs, legal CTF platforms like HackTheBox, TryHackMe).

**Strictly prohibited:** breaking into systems without authorization, stealing personal data, spreading exploit results for illegal purposes, or defacing websites.

### Legal basis in Indonesia (UU ITE No. 19 of 2016)

| Article | Offense | Penalty |
|---------|---------|---------|
| Article 30 | Unauthorized access to another party's system | 6–12 years imprisonment |
| Article 32 | Altering/deleting another party's data | Up to 8 years imprisonment, fine up to Rp 2 billion |
| Article 35 | Distributing exploit results/misleading information | Up to 12 years imprisonment, fine up to Rp 12 billion |

The developers and this documentation are not responsible for misuse. Any legal consequences are entirely the user's responsibility.

## ✅ Correct, Ethical Usage

1. Confirm you have **written authorization** before targeting any domain you don't own.
2. Scope every dork with `site:target.com` / `domain:target.com` before running at scale.
3. Use exclusion filters (`-demo -test -sample`) to cut noise.
4. Add delay between requests (`--delay`) so you aren't mistaken for abuse against the search engine.
5. Report findings professionally through an official bug bounty program.

---

*See also: [Common Dorks](common-dorks.md) for the Google-style SQLi/LFI/XSS/RCE categories, and the [Database Dorks overview](index.md) for the full `database/` folder structure.*
