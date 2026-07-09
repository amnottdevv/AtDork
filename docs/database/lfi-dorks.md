# LFI / RFI & Path Disclosure Dorks (`database/lfi/`)

This category targets parameters that pull in a file, template, or path
fragment on the server side. When the value isn't validated, it can be
abused for **Local File Inclusion** (reading files like `/etc/passwd` or
app config) or **Remote File Inclusion** (executing a file hosted on an
external server).

```
database/lfi/
└── lfi1.txt   # Path-inclusion parameters across common CMS/forum/gallery software
```

## What this category looks for

| Aspect | Description |
|--------|--------------|
| **Purpose** | Finds parameters that build a file path from user input — old CMS/forum/gallery/calendar packages are especially prone to this because they often pass a "base path" or "template" variable straight into an `include()`/`require()` call. |
| **Common parameter names** | `?path=`, `?file=`, `?page=`, `?include=`, `?dir=`, `?root_dir=`, `?basepath=`, `?systempath=`, `?configFile=`, `?template=`, `?lang=`. |
| **Typical vulnerable software** | Older PHP-based gallery, calendar, forum, and CMS add-ons (Coppermine, phpBB add-ons, Joomla/Mambo components, agendax, dotProject, and similar) — the pattern is well documented precisely because these packages were common LFI targets in the mid-2000s and the parameter names haven't changed much since. |

## Sample entries

```text
includes/header.php?systempath=
index.inc.php?PATH_Includes=
modules/mod_mainmenu.php?mosConfig_absolute_path=
pivot/modules/module_db.php?pivot_path=
zentrack/index.php?configFile=
inc/pipe.php?HCL_path=
include/new-visitor.inc.php?lvc_include_dir=
myPHPCalendar/admin.php?cal_dir=
dotproject/modules/projects/addedit.php?root_dir=
modules/coppermine/themes/default/theme.php?THEME_DIR=
index.php?page=
index.php?file=
index.php?include=
index.php?basepath=
```

**Usage:**

```bash
# Load and run the LFI category
atdork --database-dork lfi/lfi1 -r 25

# Combine with the general LFI category from the common set
atdork --database-dork lfi/lfi1,common/common2 --database-r 30 --filter-vuln lfi

# Preview before running
atdork --database-dork lfi/lfi1 --database-preview
```

## Confirming a real LFI, not just a matching URL

A dork match only tells you the *parameter name* exists — not that it's
exploitable. Use `--filter-vuln lfi` (or manually check for the classic
error strings below) before treating anything as a confirmed finding:

```text
"failed to open stream: No such file"
"include_once(): Failed opening"
"require_once(): Failed opening"
```

---

## ⚠️ Disclaimer & Legal Notice

This category is intended **only** for:

1. Security testing on websites/servers you own.
2. Official Bug Bounty programs with explicit written authorization from the target owner.
3. Academic/educational security research in a controlled environment (university labs, legal CTF platforms like HackTheBox, TryHackMe).

**Strictly prohibited:** breaking into systems without authorization, reading or exfiltrating another party's files/data, planting backdoors, or defacing websites.

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
3. Stop at confirming the vulnerability exists (e.g. via a harmless path like `/etc/hostname` or a known-safe test file) — don't pull sensitive files as "proof."
4. Add delay between requests (`--delay`) so you aren't mistaken for abuse.
5. Report findings professionally through an official bug bounty program.

---

*See also: [Common Dorks](common-dorks.md) for the general LFI/SQLi/XSS/RCE categories, [Bing & DuckDuckGo Dorks](bing-and-ddg-dorks.md), and the [Database Dorks overview](index.md) for the full `database/` folder structure.*

> **Note on source material:** the raw list this category is drawn from also contained unrelated content — a set of default/unauthenticated IP-camera admin-interface dorks (Axis/Panasonic-style `ViewerFrame`, `axis-cgi`, `liveapplet` patterns) and a large batch of credential/secret-harvesting dorks (exposed `.pwd`/`.dat` files, saved FTP/VNC/chat credentials, etc.). Both were left out of this page — the camera dorks because using them typically means viewing live footage of people who never consented to being watched, and the credential dorks because they target already-exposed secrets belonging to someone else rather than a parameter/vulnerability class. If you want, I can document those as their own **separate, clearly-labeled pages** so contributors know what they're opting into, rather than folding them silently into "LFI."
