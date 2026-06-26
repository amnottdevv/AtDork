# Template System

## Introduction

AtDork's template system allows you to load pre-defined dork collections from YAML files. Instead of typing dorks manually or maintaining a text file, you can use curated templates for specific use cases like SQL injection discovery, WordPress vulnerability scanning, or exposed configuration file hunting.

Templates are YAML-based, support domain substitution with `{target}`, and can be combined with custom queries for maximum flexibility.

---

## What It Does

| Feature | Description |
|---------|-------------|
| **Curated Templates** | Pre-built dork collections for SQLi, XSS, LFI, WordPress, Joomla, and more |
| **Target Substitution** | Use `{target}` in dorks and replace with `--target` at runtime |
| **Selective Execution** | Run specific dorks from a template using `--select` (e.g., `1,3,5`) |
| **Preview Mode** | See what dorks a template contains without executing them |
| **Custom Templates** | Create your own YAML templates and store them anywhere |
| **Template Listing** | List all available templates with descriptions |

### Built-in Templates

| Template Name | Description | Example Dork |
|---------------|-------------|--------------|
| `sqli` | SQL injection discovery | `inurl:product.php?id=` |
| `xss` | Cross-site scripting discovery | `inurl:search?q=` |
| `lfi` | Local file inclusion discovery | `inurl:page=../../` |
| `wordpress` | WordPress vulnerability scanning | `inurl:wp-content` |
| `joomla` | Joomla vulnerability scanning | `inurl:components/com_` |
| `exposed_config` | Exposed config files | `filetype:env` |
| `login_panels` | Admin login panels | `intitle:"admin panel"` |
| `backup_files` | Backup and temporary files | `filetype:bak` |
| `sensitive_dirs` | Sensitive directory listings | `intitle:"index of"` |

---

## How to Use

### List Available Templates
```bash
atdork --list-templates
```

**Output:**
```
Template Dorks Tersedia:
  sqli - SQL injection discovery dorks
  xss - Cross-site scripting discovery dorks
  lfi - Local file inclusion discovery dorks
  wordpress - WordPress vulnerability scanning
  joomla - Joomla vulnerability scanning
  exposed_config - Exposed config files
  login_panels - Admin login panels
  backup_files - Backup and temporary files
  sensitive_dirs - Sensitive directory listings
```

### Basic Template Usage
```bash
atdork --template sqli --target example.com -r 30
```

### Combine Multiple Templates
```bash
atdork --template sqli,wordpress,exposed_config --target example.com -r 25
```

### Select Specific Dorks from a Template
```bash
atdork --template sqli --select 1,3,5 -r 20
```

### Preview Template Dorks (No Execution)
```bash
atdork --template sqli --preview
```

**Output:**
```
Preview template 'sqli':
  1. inurl:product.php?id=
  2. inurl:category.php?id=
  3. inurl:news.php?id=
  4. inurl:page.php?id=
  5. inurl:detail.php?id=
```

### Use Template with Custom Query
```bash
atdork --template sqli,wordpress -q "site:gov filetype:pdf" -r 25
```

### Use Template with Proxy and Resilience
```bash
atdork --template sqli,xss,lfi --target target.com \
  --proxy-file proxies.txt --strict --resilient \
  --concurrency 3 --format json -o recon.json
```

### Custom Template Path
```bash
atdork --template my_custom --template-path /path/to/my/templates/
```

---

## How It Works

### 1. Template File Structure

Templates are YAML files with the following structure:

```yaml
# wordlists/templates/sqli.yaml
name: sqli
description: SQL injection discovery dorks
category: vulnerability

# Dorks that require a target domain
targeted:
  - "site:{target} inurl:product.php?id="
  - "site:{target} inurl:category.php?id="
  - "site:{target} inurl:news.php?id="

# Generic dorks (no target needed)
generic:
  - "inurl:product.php?id="
  - "inurl:category.php?id="
  - "inurl:news.php?id="
```

### 2. Template Types

| Type | Description | When to Use |
|------|-------------|-------------|
| **targeted** | Contains `{target}` placeholder | When you want to focus on a specific domain |
| **generic** | No placeholder, works everywhere | For broad discovery across all domains |

### 3. Detection Logic

```
1. User provides --template sqli --target example.com
   ↓
2. AtDork loads wordlists/templates/sqli.yaml
   ↓
3. Parses YAML:
   ├─ targeted: [dorks with {target}]
   └─ generic: [dorks without {target}]
   ↓
4. Renders dorks:
   ├─ targeted: replaces {target} with example.com
   └─ generic: kept as-is
   ↓
5. If --select provided:
   └─ Filters to specific indices (1,3,5)
   ↓
6. Executes all dorks as a batch
   └─ Same as --batch-file but generated dynamically
```

### 4. Example

**Input Template (`sqli.yaml`):**
```yaml
targeted:
  - "site:{target} inurl:product.php?id="
  - "site:{target} inurl:category.php?id="
generic:
  - "inurl:product.php?id="
```

**Command:**
```bash
atdork --template sqli --target example.com --select 1
```

**Generated Dorks:**
```
site:example.com inurl:product.php?id=
```

### 5. Package Resource Loading (v1.3.8+)

Starting from v1.3.8, templates are included in the installed package. This means:

- **From PyPI:** Templates work out of the box (no extra files needed)
- **From Source:** Templates are loaded from `wordlists/templates/`
- **Custom Templates:** Use `--template-path` to load templates from any directory
- **Fail Closed:** If a template is missing, AtDork exits with an error

**Error Example:**
```
Template 'unknown' tidak ditemukan di 'wordlists/templates/'.
Gunakan --list-templates untuk melihat daftar yang tersedia.
```

---

## Full Flag Reference

| Flag | Description | Default |
|------|-------------|---------|
| `--template` | Template name(s), comma-separated | None |
| `--target` | Domain for `{target}` substitution | None |
| `--select` | Run specific dorks from template (e.g., `1,3,5`) | None |
| `--list-templates` | Show all available templates | Disabled |
| `--preview` | Show dorks without executing | Disabled |
| `--template-path` | Custom template directory | `wordlists/templates/` |

---

## Real-World Use Cases

### 1. Bug Bounty Recon with Multiple Templates
```bash
atdork --template sqli,xss,lfi,wordpress,exposed_config \
  --target target.com --proxy-file proxies.txt --strict \
  --resilient --concurrency 5 --format json -o full_recon.json
```

### 2. Quick WordPress Vulnerability Scan
```bash
atdork --template wordpress --target example.com -r 40 \
  --filter-vuln wordpress --verbose
```

### 3. Preview Before Running (Validate Templates)
```bash
atdork --template sqli --preview
atdork --template sqli --target example.com --preview
```

### 4. Automated Weekly Monitoring with Template
```bash
atdork --template login_panels,exposed_config,sensitive_dirs \
  --target corp.com --proxy-file proxies.txt \
  --resilient --format csv --output-dir /reports/$(date +\%Y-\%W)/
```

### 5. Combining Template with Custom Query
```bash
atdork --template sqli,wordpress -q "site:gov filetype:pdf" -r 25
```

---

## Creating Custom Templates

### Step 1: Create a YAML file

```yaml
# wordlists/templates/my_template.yaml
name: my_template
description: My custom dork collection
category: custom

targeted:
  - "site:{target} filetype:log"
  - "site:{target} intitle:error"

generic:
  - "filetype:log"
  - "intitle:error"
```

### Step 2: Use the template
```bash
atdork --template my_template --target example.com -r 20
```

### Step 3: Preview your template
```bash
atdork --template my_template --preview
```

### Step 4: Store templates anywhere
```bash
atdork --template my_template --template-path /path/to/custom/templates/
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| **"Template not found" error** | Use `--list-templates` to see available templates |
| **Targeted dorks not running** | Provide `--target` (e.g., `--target example.com`) |
| **Wrong dorks selected** | Use `--preview` to check before running |
| **Custom template not loading** | Check YAML syntax and file extension (`.yaml` or `.yml`) |
| **Template returns no results** | Try different backends or add more relevant dorks to the template |
| **Template not found after install** | Update to latest version (`pip install --upgrade atdork`) |

---

## Template Development Tips

1. **Test with `--preview` first** – Always preview before running
2. **Use `--select` for debugging** – Test individual dorks
3. **Group related dorks** – Keep templates focused on one topic
4. **Add descriptions** – Help users understand each template
5. **Test with `--target`** – Ensure substitution works correctly
6. **Keep generic dorks** – For broad discovery without a target