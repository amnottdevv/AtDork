# Vulnerability Filter (`--filter-vuln`)

## Introduction

The `--filter-vuln` flag is AtDork's specialized vulnerability detection system. It automatically identifies potentially vulnerable results based on platform-specific signatures, helping security researchers and bug bounty hunters quickly focus on high-value targets.

The filter scans result URLs, titles, and descriptions against curated wordlists of platform-specific patterns. When a match is found, the result is flagged as "vulnerable" and separated from safe results.

---

## What It Does

| Feature | Description |
|---------|-------------|
| **Platform Detection** | Identifies platforms like WordPress, Joomla, Drupal, and more |
| **Vulnerability Pattern Matching** | Matches known vulnerable paths, parameters, and signatures |
| **Link vs Path Modes** | `-link` mode matches URLs only; default mode matches all fields |
| **Custom Wordlists** | Create your own wordlists for specific platforms or technologies |
| **Smart Filtering** | Results are classified as "vulnerable" or "safe" with clear counts |
| **Post-Processing Ready** | Use `--exec-on-vuln` to run commands only on vulnerable results |

### Supported Platforms

AtDork includes built-in wordlists for:

| Platform | Wordlist File | Example Signature |
|----------|---------------|-------------------|
| WordPress | `wordpress.txt` | `wp-content`, `wp-admin`, `wp-includes` |
| Joomla | `joomla.txt` | `components/com_`, `administrator` |
| Drupal | `drupal.txt` | `sites/default`, `core/` |
| SQL Injection | `sqli.txt` | `id=`, `page=`, `?q=` |
| XSS | `xss.txt` | `search=`, `s=`, `query=` |
| LFI (Local File Inclusion) | `lfi.txt` | `page=../../`, `file=` |
| Exposed Config | `exposed_config.txt` | `.env`, `config.php`, `settings.yml` |
| Login Panels | `login_panels.txt` | `login`, `admin`, `panel` |
| Backup Files | `backup_files.txt` | `.bak`, `.old`, `.backup` |
| Sensitive Directories | `sensitive_dirs.txt` | `index of`, `directory listing` |

---

## How to Use

### Basic Vulnerability Filtering

```bash
atdork -q "inurl:wp-content" -r 30 --filter-vuln wordpress
```

### Link-Only Filtering (Matches URLs Only)

```bash
atdork -q "site:example.com" --filter-vuln wordpress-link
```

### Combining with Other Flags

```bash
atdork -q "inurl:wp-content site:example.com" -r 40 \
  --filter-vuln wordpress --verbose
```

### Multiple Vulnerability Filters

AtDork supports one filter at a time, but you can chain them using different wordlists. For multiple platform detection, use templates:

```bash
atdork --template wordpress,joomla,sqli --target example.com -r 30
```

### Using Custom Wordlists

Create your own wordlist file in `wordlists/` folder:

```bash
# wordlists/myplatform.txt
wp-content
wp-admin
wp-includes
wp-json
xmlrpc.php
```

Then use it:

```bash
atdork -q "site:example.com" --filter-vuln myplatform
```

### With Post-Processing (Run Commands on Vulnerable Results)

```bash
atdork -q "inurl:wp-content" -r 40 \
  --filter-vuln wordpress \
  --exec-on-vuln "wpscan --url {} --enumerate p" \
  --exec-parallel 2 --exec-timeout 60
```

### Batch Processing with Vulnerability Filter

```bash
atdork --batch-file dorks.txt --filter-vuln wordpress \
  --resilient --format json -o vuln_results.json
```

### With Resilience and Proxy

```bash
atdork --template wordpress --target example.com -r 30 \
  --filter-vuln wordpress \
  --proxy-file proxies.txt --strict --resilient
```

### With Strict Validation

```bash
atdork -q "inurl:wp-content" -r 40 \
  --filter-vuln wordpress \
  --strict-filter --validate-title 10 --validate-desc 20
```

---

## How It Works

### 1. Wordlist Loading System

AtDork loads wordlists from the `wordlists/` directory. Each wordlist is a simple text file with one pattern per line:

```bash
# wordlists/wordpress.txt
# WordPress-specific signatures
wp-content
wp-admin
wp-includes
wp-json
xmlrpc.php
wp-login.php
wp-config.php
```

**Pattern Rules:**
- Each line is a **regex pattern** (case-insensitive)
- Lines starting with `#` are ignored
- Empty lines are ignored

**Loading Process:**
```
1. User provides --filter-vuln wordpress
   ↓
2. AtDork looks for wordlists/wordpress.txt
   ├─ From package resources (installed version)
   └─ From file system (source version)
   ↓
3. Each line is compiled into a regex pattern
   ↓
4. Patterns are cached for performance
   ↓
5. If wordlist is missing → ERROR (fail closed)
```

### 2. Filter Types

AtDork supports two types of filters:

| Type | Suffix | Searches In | When to Use |
|------|--------|-------------|-------------|
| **Path** (default) | none | `title`, `href`, `body` | General purpose detection |
| **Link** | `-link` | **Only** `href` (URL) | When you only care about URL patterns |

**Example:**
- `--filter-vuln wordpress` → searches `title`, `href`, and `body`
- `--filter-vuln wordpress-link` → searches **only** `href`

### 3. Detection Logic

```
1. User provides --filter-vuln wordpress
   ↓
2. AtDork loads wordlists/wordpress.txt
   ↓
3. Each line is compiled into a regex pattern
   ↓
4. For each result:
   ├─ If path mode:
   │  ├─ Get title, href, body
   │  └─ Combine into one string
   ├─ If link mode:
   │  └─ Use href only
   ├─ Test against all regex patterns
   └─ If any pattern matches → mark as "vulnerable"
   ↓
5. Results are split into:
   ├─ vulnerable list (matching patterns)
   └─ safe list (no matches)
   ↓
6. CLI displays counts: "🔴 Rentan: 12 | 🟢 Aman: 8"
   ↓
7. Only vulnerable results are kept for output
```

### 4. Example: WordPress Detection

**Input Result:**
```json
{
  "title": "WordPress Login",
  "href": "https://example.com/wp-admin/",
  "body": "Please enter your credentials to access the admin area"
}
```

**Wordlist (`wordlists/wordpress.txt`):**
```
wp-content
wp-admin
wp-includes
wp-json
xmlrpc.php
```

**Detection:**
- `title` contains "WordPress" → no match (not in wordlist)
- `href` contains `wp-admin` → **MATCH!**
- `body` contains "admin" → no match (not in wordlist)
- Result is classified as **"vulnerable"**

**Why this matters:** The URL `/wp-admin/` is a strong indicator of a WordPress installation, which is a common target for vulnerability scanning.

### 5. Fail Closed Design

Starting from v1.3.8, AtDork uses **Fail Closed** behavior:

```
If wordlist is missing:
  ❌ Exit with error
  📝 Show clear error message
  💡 Suggest fix
```

**Error Example:**
```
Error: Wordlist file 'does-not-exist.txt' tidak ditemukan.
   Sumber yang dicek: paket resource 'wordlists'
```

**Why this is important:**
- Prevents **false confidence** (thinking there are no vulnerabilities when the filter isn't working)
- Makes issues **immediately visible**
- Ensures **reliable results** every time

### 6. Package Resource Loading

Since v1.3.8, wordlists are included in the installed package:

| Installation Method | Wordlist Source |
|---------------------|-----------------|
| **From PyPI** (`pip install atdork`) | Packaged resources (built-in) |
| **From Source** (`git clone` + `pip install -e .`) | `wordlists/` directory |
| **Custom Wordlist** | `wordlists/` directory (overrides packaged) |

**Benefits:**
- No extra files needed after `pip install`
- Consistent behavior across installations
- Easy to override with custom wordlists

---

## Full Flag Reference

| Flag | Description | Default |
|------|-------------|---------|
| `--filter-vuln` | Platform filter (e.g., `wordpress`, `joomla-link`) | None |
| `--exec-on-vuln` | Execute command only on vulnerable results | None |
| `--exec-parallel` | Parallel processes for `--exec` | 1 |
| `--exec-timeout` | Timeout per command (seconds) | 30 |
| `--verbose`, `-v` | Show results with vulnerability counts | Disabled |
| `--strict-filter` | Strict validation with length checks | Disabled |
| `--no-validate` | Disable all filtering (keep raw results) | Disabled |

---

## Real-World Use Cases

### 1. WordPress Vulnerability Hunting

```bash
atdork -q "inurl:wp-content site:example.com" -r 40 \
  --filter-vuln wordpress -v \
  --exec-on-vuln "wpscan --url {} --enumerate p" \
  --exec-parallel 2 --exec-timeout 60
```

**What it does:**
- Finds WordPress sites
- Filters only those with WordPress signatures
- Runs WPScan on each vulnerable result

### 2. SQL Injection Discovery

```bash
atdork -q "inurl:product.php?id=" -r 50 \
  --filter-vuln sqli \
  --format json -o sqli_results.json
```

**What it does:**
- Finds pages with potential SQL injection parameters
- Filters results with SQLi signatures
- Exports to JSON for further analysis

### 3. Exposed Configuration Files

```bash
atdork -q 'filetype:env "DB_PASSWORD"' -r 50 \
  --filter-vuln exposed_config \
  --no-validate -v
```

**What it does:**
- Finds exposed `.env` files with database credentials
- Filters only config file signatures
- Shows results in terminal for quick review

### 4. Joomla Vulnerability Scanning (Link-Only)

```bash
atdork -q "site:example.com" -r 30 \
  --filter-vuln joomla-link \
  --resilient --proxy-file proxies.txt
```

**What it does:**
- Scans for Joomla installations
- Link-only mode focuses on URLs
- Resilience mode handles rate limits

### 5. Rapid WordPress Scan with Multiple Wordlists

```bash
atdork --template sqli,wordpress,exposed_config \
  --target example.com -r 30 \
  --filter-vuln wordpress \
  --format json -o comprehensive_scan.json
```

### 6. Automated Vulnerability Assessment Pipeline

```bash
# Step 1: Discover potential targets
atdork -q "inurl:wp-content" -r 100 \
  --filter-vuln wordpress \
  --format csv -o potential_targets.csv

# Step 2: Scan each target with WPScan
while IFS=, read -r title url body; do
  wpscan --url "$url" --enumerate p --output "scan_$(basename "$url").json"
done < potential_targets.csv
```

---

## Creating Custom Wordlists

### Step 1: Create a Wordlist File

Create a text file in the `wordlists/` directory:

```bash
# wordlists/custom.txt
# One pattern per line
# Lines starting with # are ignored

# Admin panels
admin
login
panel
dashboard

# Sensitive paths
config
backup
.old
.bak

# Parameter patterns
id=
page=
file=
path=
```

### Step 2: Use the Custom Wordlist

```bash
atdork -q "site:example.com" --filter-vuln custom
```

### Step 3: Test Your Wordlist

```bash
# Test with a small query first
atdork -q "test" -r 5 --filter-vuln custom --verbose

# Preview what will be matched
atdork -q "site:example.com" -r 10 --filter-vuln custom --no-validate
```

### Wordlist Development Tips

1. **Start with common patterns** for each platform
2. **Use regex** for complex patterns (e.g., `wordpress.*wp-admin`)
3. **Test with `--verbose`** to see which patterns are matching
4. **Keep it focused** – one platform per wordlist
5. **Update regularly** – new vulnerabilities are discovered daily

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| **"Wordlist file not found" error** | Update to latest version (`pip install --upgrade atdork`) |
| **Filter returns 0 vulnerable results** | Try `-link` variant (e.g., `wordpress-link`) or check your wordlist content |
| **Custom wordlist not working** | Place file in `wordlists/` with `.txt` extension |
| **False positives (too many matches)** | Create a more specific wordlist with unique signatures |
| **False negatives (missed vulnerabilities)** | Add more patterns to the wordlist file |
| **Results showing "unknown" filter type** | Check wordlist file format and path |
| **Filter not working after pip install** | Ensure you're using v1.3.8 or later |

---

## Best Practices

1. **Use `-link` for URL-only matching** – Reduces false positives
2. **Combine with `--resilient`** – Handles rate limits during large scans
3. **Use `--exec-on-vuln`** – Automate vulnerability scanning
4. **Create custom wordlists** – For specific technologies or patterns
5. **Test with `--verbose`** – Verify patterns are matching correctly
6. **Validate results** – Use `--strict-filter` to ensure quality
7. **Document your wordlists** – Add comments describing each pattern