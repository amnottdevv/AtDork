# CMS-Specific Dorks (`database/cms/`)

Where the `common/` category targets generic parameter patterns across any
PHP app, this category targets **fingerprints specific to a given
CMS/framework** — file paths, default config locations, and version
markers unique to Joomla, WordPress, Magento, and Laravel. This makes the
dorks far more precise: a hit tells you not just "a parameter exists" but
"this specific CMS is running here, at this version or plugin."

```
database/cms/
├── joomla/joomla.txt       # Joomla components, admin paths, config exposure
├── wordpress/wordpress.txt # WP core paths, plugins, themes, wp-config exposure
├── magento/                # Magento admin, API, and config endpoints
└── laravel/                # Laravel .env exposure, debug mode, artisan routes
```

## 1. Joomla (`joomla/joomla.txt`)

| Aspect | Description |
|--------|--------------|
| **Purpose** | Finds Joomla installations and their component/admin structure — many older third-party Joomla components (`com_*`) shipped with LFI or config-exposure bugs, so identifying the component footprint is the first step. |
| **Common patterns** | `inurl:"/component/users/"`, `inurl:administrator/index.php`, `intitle:"Joomla - Web Installer"`, `mosConfig_absolute_path=`, `inurl:com_content`. |

```text
inurl:administrator/index.php intitle:"Joomla"
intitle:"Joomla - Web Installer"
inurl:index.php?option=com_content
inurl:index.php?option=com_users&view=login
site:target.com inurl:/administrator/
inurl:configuration.php~ site:target.com
```

```bash
atdork --database-dork cms/joomla/joomla -r 20
```

## 2. WordPress (`wordpress/wordpress.txt`)

| Aspect | Description |
|--------|--------------|
| **Purpose** | Fingerprints WordPress core, active plugins/themes, and common misconfigurations (exposed `wp-config.php` backups, open registration, debug logs). |
| **Common patterns** | `inurl:wp-content/plugins/`, `inurl:wp-login.php`, `intext:"Powered by WordPress"`, `filetype:log inurl:wp-content/debug.log`, `wp-config.php.bak`. |

```text
inurl:/wp-content/plugins/ site:target.com
inurl:wp-login.php
intitle:"WordPress" intext:"Just another WordPress site"
filetype:log inurl:"wp-content/debug.log"
inurl:wp-config.php.bak OR inurl:wp-config.php.save
inurl:xmlrpc.php "Invalid method"
```

```bash
atdork --database-dork cms/wordpress/wordpress -r 20 --filter-vuln wordpress
```

## 3. Magento (`magento/`)

| Aspect | Description |
|--------|--------------|
| **Purpose** | Finds Magento admin panels, REST/SOAP API endpoints, and exposed configuration — Magento stores are high-value targets because they process payment data, so admin-path and API exposure matters more than on a typical CMS. |
| **Common patterns** | `inurl:/admin/` + `intitle:"Magento Admin"`, `inurl:/downloader/index.php`, `inurl:app/etc/local.xml`, `inurl:/index.php/admin/`, `inurl:/rest/V1/` (REST API root). |

```text
intitle:"Magento Admin" inurl:/admin
inurl:app/etc/local.xml
inurl:/downloader/index.php
inurl:/index.php/admin/dashboard
inurl:/rest/V1/products site:target.com
inurl:var/log/system.log site:target.com
```

```bash
atdork --database-dork cms/magento -r 20
```

## 4. Laravel (`laravel/`)

| Aspect | Description |
|--------|--------------|
| **Purpose** | Laravel apps are dorked differently from the others — the framework itself is fairly secure by default, so the interesting cases are almost always **misconfiguration**: `APP_DEBUG=true` left on in production (which dumps stack traces with DB credentials), or a `.env` file directly accessible. |
| **Common patterns** | `inurl:.env "APP_KEY="`, `intext:"Whoops, looks like something went wrong"` (debug page), `inurl:/storage/logs/laravel.log`, `inurl:/artisan`. |

```text
inurl:.env "APP_KEY=" "DB_PASSWORD="
intext:"Whoops, looks like something went wrong"
inurl:/storage/logs/laravel.log
inurl:"/telescope" intitle:"Telescope"
inurl:.env site:target.com filetype:env
```

```bash
atdork --database-dork cms/laravel -r 20 --filter-vuln laravel
```

> A live, readable `.env` file is the single most damaging Laravel misconfiguration you'll find this way — it typically contains the app key, DB credentials, mail credentials, and third-party API keys all in one file. Treat a hit here the same way you'd treat any other exposed-secret finding: don't use the credentials, report through the program's disclosure channel. See [GitHub Secret-Exposure Dorks](github-dorks.md) for the same guidance applied to code-hosting leaks.

## Combining across CMS categories

```bash
# Fingerprint all four CMS types against a scoped target in one batch
atdork --database-dork cms/joomla/joomla,cms/wordpress/wordpress,cms/magento,cms/laravel \
  -r 40 --format json -o cms_recon.json
```

---

## ⚠️ Disclaimer & Legal Notice

This category is intended **only** for:

1. Security testing on websites/servers you own.
2. Official Bug Bounty programs with explicit written authorization from the target owner.
3. Academic/educational security research in a controlled environment (university labs, legal CTF platforms like HackTheBox, TryHackMe).

**Strictly prohibited:** breaking into systems without authorization, accessing an admin panel with credentials you don't own, reading or exfiltrating another party's `.env`/config contents, or defacing websites.

### Legal basis in Indonesia (UU ITE No. 19 of 2016)

| Article | Offense | Penalty |
|---------|---------|---------|
| Article 30 | Unauthorized access to another party's system | 6–12 years imprisonment |
| Article 32 | Altering/deleting/transferring another party's data | Up to 8 years imprisonment, fine up to Rp 2 billion |
| Article 35 | Distributing exploit results/misleading information | Up to 12 years imprisonment, fine up to Rp 12 billion |

The developers and this documentation are not responsible for misuse. Any legal consequences are entirely the user's responsibility.

## ✅ Correct, Ethical Usage

1. Confirm **written authorization** before targeting any domain you don't own.
2. Scope every dork with `site:target.com` before running at scale.
3. Stop at confirming a fingerprint/misconfiguration exists — don't log into an admin panel or use any exposed credential.
4. Add delay between requests (`--delay`) so you aren't mistaken for abuse.
5. Report findings professionally through an official bug bounty program.

---

*See also: [Common Dorks](common-dorks.md), [LFI Dorks](lfi-dorks.md) / [RFI Dorks](rfi-dorks.md), [GitHub Secret-Exposure Dorks](github-dorks.md), and the [Database Dorks overview](index.md) for the full `database/` folder structure.*
