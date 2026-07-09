# Common Dorks (`database/common/`)

The `common/` folder is the core of AtDork's bundled dork database. It groups
everyday web-vulnerability recon patterns into four files, split by
vulnerability class so you can load exactly the category you need for a given
engagement.

```
database/common/
├── common1.txt   # SQL Injection & IDOR
├── common2.txt   # LFI / RFI & Path Disclosure
├── common3.txt   # XSS & HTML Injection
└── common4.txt   # File Upload Bypass, RCE, Command Injection & SSRF
```

Extract the database first if you haven't already:

```bash
atdork --extract-database
```

Then browse what's available:

```bash
atdork --list-database-dork
```

---

## `common1.txt` – SQL Injection & IDOR

| Aspect | Description |
|--------|--------------|
| **Purpose** | Finds numeric/ID parameters (`?id=`, `?cat=`, `?pid=`, etc.) that are often left unvalidated, potentially vulnerable to SQL Injection or IDOR (accessing another user's data by manipulating an ID). |
| **Common targets** | `product.php?id=`, `view.php?id=`, `?cat=`, `?page=`, admin panels (`admin.php?id=`), profile/user pages (`profile.php?id=`). |
| **Sample entries** | ```text\ninurl:product.php?id=\ninurl:view.php?id=\ninurl:?cat=\nsite:target.com inurl:product.php?id=\ninurl:product.php?id= intext:"mysql"\ninurl:product.php?id= union\n``` |

**Usage example:**

```bash
# Load all SQLi/IDOR dorks and run them
atdork --database-dork common/common1 -r 30

# Preview instead of running
atdork --database-dork common/common1 --database-preview
```

---

## `common2.txt` – LFI / RFI & Path Disclosure

| Aspect | Description |
|--------|--------------|
| **Purpose** | Finds parameters that include a file (template, language, page). Without validation this can be exploited to read sensitive system files (LFI, e.g. `/etc/passwd`) or execute a file hosted on an external server (RFI). |
| **Common targets** | `?page=`, `?file=`, `?path=`, `?template=`, `?lang=`, `?include=`. |
| **Sample entries** | ```text\ninurl:?page=\ninurl:?file=\ninurl:?page= etc/passwd\ninurl:?page= intext:"failed to open stream"\ninurl:?page= wp-config.php\nintitle:"index of" "config"\n``` |

**Usage example:**

```bash
atdork --database-dork common/common2 -r 20 --filter-vuln lfi
```

---

## `common3.txt` – XSS & HTML Injection

| Aspect | Description |
|--------|--------------|
| **Purpose** | Finds parameters that reflect or store user input on a page without sanitization, potentially vulnerable to Cross-Site Scripting. |
| **Common targets** | `?q=`, `?search=`, `?s=`, `?comment=`, `?feedback=`, `?name=`, `?email=`. |
| **Sample entries** | ```text\ninurl:?q=\ninurl:?search=\ninurl:?q= intext:"<script>"\ninurl:comment.php intext:"<script>"\nsite:.go.id inurl:?q= intext:"cari"\n``` |

**Usage example:**

```bash
atdork --database-dork common/common3 --database-r 15 --database-seed 1
```

---

## `common4.txt` – File Upload Bypass, RCE, Command Injection & SSRF

| Aspect | Description |
|--------|--------------|
| **Purpose** | Finds weak file-upload features, parameters that execute system commands, and parameters that fetch content from another URL (SSRF). This is the most critical category, as it can lead to full server takeover. |
| **Common targets** | `upload.php`, `?cmd=`, `?exec=`, `?ping=`, `?url=`, `?fetch=`, `?proxy=`, `phpinfo.php`. |
| **Sample entries** | ```text\ninurl:upload.php\ninurl:?cmd=\ninurl:?url=\ninurl:phpinfo.php\ninurl:upload.php intext:"failed to move"\ninurl:ping.php?ip= intext:"PING"\n``` |

**Usage example:**

```bash
atdork --database-dork common/common4 -r 25 --exec "curl -sI {}"
```

---

## Combining multiple categories

```bash
# SQLi + LFI in one batch
atdork --database-dork common/common1,common/common2 -r 40 --format json -o recon.json

# All 4 categories, random sample of 50 dorks, reproducible via seed
atdork --database-dork common/common1,common/common2,common/common3,common/common4 \
  --database-r 50 --database-seed 7 --database-preview
```

---

## ⚠️ Disclaimer & Legal Notice

The categories above are intended **only** for:

1. Security testing on websites/servers you own.
2. Official Bug Bounty programs where you have explicit written authorization from the target owner.
3. Security research/education in a controlled environment (university labs, legal CTF platforms such as HackTheBox).

**Strictly prohibited** uses include: breaking into systems without authorization, stealing personal data, planting backdoors/webshells, selling illegal access, or defacing websites.

### Legal basis in Indonesia (UU ITE No. 19 of 2016)

| Article | Offense | Penalty |
|---------|---------|---------|
| Article 30(1) | Unauthorized access to an electronic system | Up to 6 years imprisonment, fine up to Rp 600 million |
| Article 32(1) | Altering/damaging/transferring another party's data | Up to 8 years imprisonment, fine up to Rp 2 billion |
| Article 35 | Spreading false or misleading information (including exploit results) | Up to 12 years imprisonment, fine up to Rp 12 billion |

The developers and this documentation are not responsible for misuse. Any legal consequences are entirely the user's responsibility.

## ✅ Correct, Ethical Usage

1. **Confirm you have written authorization** before targeting any domain you don't own.
2. **Scope your searches** with `site:target.com` on every dork before running them at scale.
3. **Use exclusion filters (`-`)** to cut out noise (`-demo -test -sample`).
4. **Add delay between requests** (`--delay`) so you aren't mistaken for spam/abuse against Google.
5. **Report findings professionally** through an official bug bounty program — don't exploit beyond what the scope permits.

---

*See also: [GHDB Scraper](../ghdb-scraper.md) for dorks scraped directly from Exploit-DB, and the [Database Dorks overview](index.md) for the overall `database/` folder structure.*
