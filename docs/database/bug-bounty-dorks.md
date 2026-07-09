# Bug Bounty Program Discovery Dorks (`database/bug-bounty-dorks/`)

This category is different from the vulnerability-class dorks elsewhere in
the database. Instead of finding a *weak parameter*, these dorks find
**organizations that run a bug bounty or responsible disclosure program** —
useful when you're looking for legitimate, in-scope targets to test against
rather than testing at random.

```
database/bug-bounty-dorks/
└── bbdorks.txt   # Responsible disclosure pages, security.txt files, VDP/bounty program listings
```

## What this category looks for

| Aspect | Description |
|--------|--------------|
| **Purpose** | Surfaces a company's published security contact, responsible disclosure policy, `security.txt` file, or bounty/reward program page — the legitimate starting point for any engagement. |
| **Common patterns** | `inurl:security.txt`, `inurl:/responsible-disclosure/`, `inurl:/.well-known/security.txt`, `"vulnerability disclosure policy"`, `"powered by hackerone"`, `"powered by bugcrowd"`, `"powered by synack"`. |
| **Region filters** | Several entries use `site:*.*.nl`, `site:*.*.uk`, `site:*.*.de`, etc. to find disclosure programs in a specific country's domains. |
| **`r=h:` syntax** | The `r=h:nl` / `r=h:uk` / `r=h:eu` suffixes are DuckDuckGo's region-restriction shorthand, equivalent to filtering results by country. |

## Sample entries

```text
inurl:security.txt
inurl:/responsible-disclosure/
inurl:/.well-known/security.txt
inurl:/.well-known/security.txt intext:hackerone
"powered by hackerone" "submit vulnerability report"
"powered by bugcrowd" -site:bugcrowd.com
"powered by synack"
"vulnerability reporting policy"
intext:responsible disclosure bounty
intext:Vulnerability Disclosure site:nl
site:*.*.nl intext:responsible disclosure reward
site:*.*.uk intext:security report reward
responsible disclosure hall of fame
```

## Usage

```bash
# Extract the database first if you haven't already
atdork --extract-database

# Load and run the bug bounty discovery dorks
atdork --database-dork bug-bounty-dorks/bbdorks -r 30

# Preview what would run, without executing
atdork --database-dork bug-bounty-dorks/bbdorks --database-preview

# Random sample, reproducible with a seed
atdork --database-dork bug-bounty-dorks/bbdorks --database-r 20 --database-seed 5

# Save discovered program pages to a file for later review
atdork --database-dork bug-bounty-dorks/bbdorks -r 50 --format json -o programs.json
```

Since this category is mostly `site:`-restricted or region-restricted
plain-text/`intext:` searches rather than `inurl:` parameter probes, it
tends to work well on any backend — but DuckDuckGo (`--backend duckduckgo`)
handles the `r=h:` region shorthand entries natively:

```bash
atdork --database-dork bug-bounty-dorks/bbdorks --backend duckduckgo -r 30
```

## What to do with the results

A hit here just means the organization *has* a disclosure/bounty program —
it's not permission to test anything you find. Before touching the target:

1. Open the disclosure page and read the **scope** — many programs explicitly exclude certain subdomains, endpoints, or third-party services.
2. Check whether they run through a platform (HackerOne, Bugcrowd, Synack, Intigriti) — if so, register there and follow their intake process rather than reporting directly.
3. Confirm the **rules of engagement** (rate limits, no automated scanning, no social engineering, etc.) before running any of the other dork categories against that domain.

---

## ⚠️ Disclaimer & Legal Notice

Finding a company's disclosure page is legal and encouraged — that's the point of publishing one. The disclaimer below applies to what you do *after* finding a program, i.e. any testing against the target itself:

1. Only test within the **published scope** of the program you found.
2. Follow the program's stated **rules of engagement** and reporting process.
3. For any target without a public program, get **explicit written authorization** before testing.

### Legal basis in Indonesia (UU ITE No. 19 of 2016)

| Article | Offense | Penalty |
|---------|---------|---------|
| Article 30 | Unauthorized access to another party's system | 6–12 years imprisonment |
| Article 32 | Altering/deleting/transferring another party's data | Up to 8 years imprisonment, fine up to Rp 2 billion |
| Article 35 | Distributing exploit results/misleading information | Up to 12 years imprisonment, fine up to Rp 12 billion |

The developers and this documentation are not responsible for testing conducted outside a program's scope or without authorization.

---

*See also: [Common Dorks](common-dorks.md), [Bing & DuckDuckGo Dorks](bing-and-ddg-dorks.md), [LFI Dorks](lfi-dorks.md), and the [Database Dorks overview](index.md) for the full `database/` folder structure.*
