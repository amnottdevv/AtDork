# GitHub Secret-Exposure Dorks (`database/github-dorks/`)

This category is fundamentally different from the SQLi/LFI/RFI/XSS
categories elsewhere in this database. Those find a *potentially*
vulnerable parameter that still requires authorization and further work to
confirm. GitHub dorks find **already-exposed, live credentials** — the
moment a query hits, you're looking at a real API key, password, or
private key that someone actually committed.

Because of that, the primary intended use of this page is **auditing your
own organization's repositories** (and their commit history — secrets
often survive in old commits even after being "removed") for accidental
credential leaks, not searching the wider internet for other people's keys.

```
database/github-dorks/
└── ghdorks.txt   # filename:/extension:/language: searches for common secret file patterns
```

## What this category looks for

| Aspect | Description |
|--------|--------------|
| **Purpose** | Finds files, filenames, and code patterns known to contain live credentials that were accidentally committed to a public repo. |
| **Common patterns** | `filename:.env`, `filename:id_rsa`, `filename:.npmrc _auth`, `extension:pem private`, `filename:credentials aws_access_key_id`, `filename:wp-config.php`. |
| **Certificate/key patterns** | `"-----BEGIN RSA PRIVATE KEY-----"`, `"-----BEGIN PRIVATE KEY-----"`, `"-----BEGIN CERTIFICATE-----" extension:pem`. |
| **Service-specific tokens** | `HEROKU_API_KEY`, `shodan_api_key`, `DATADOG_API_KEY`, `xoxp OR xoxb` (Slack tokens), `SF_USERNAME salesforce`. |
| **User/org discovery** | `user:`, `org:`, `in:login`, `in:email`, `created:` date-range filters — used to scope a search to a specific account or org rather than the whole platform. |

## Sample entries

```text
filename:.env DB_USERNAME NOT homestead
filename:id_rsa or filename:id_dsa
filename:credentials aws_access_key_id
extension:pem private
extension:sql mysql dump password
filename:.npmrc _auth
filename:.dockercfg auth
filename:settings.py SECRET_KEY
filename:secrets.yml password
HEROKU_API_KEY language:shell
"https://hooks.slack.com/services/"
```

## Usage — auditing your own org

```bash
# Scope every search to your own GitHub org/account before running anything
atdork --database-dork github-dorks/ghdorks --backend google -r 20
```

Since these are GitHub-specific search operators, run them **scoped to your
own org**, e.g. by appending `org:your-org-name` or `user:your-username` to
each query (edit the dork file, or use `--exec` to append a scope suffix
per line) rather than running them unscoped.

```bash
# Preview what's in the file before running anything
atdork --database-dork github-dorks/ghdorks --database-preview
```

## If you find a live secret

This is the part that matters more than the dorks themselves:

1. **If it's yours/your org's** — rotate the credential immediately, then scrub it from git history (it's not enough to delete it in a new commit; use `git filter-repo` or GitHub's secret-removal tooling, since old commits remain accessible).
2. **If it belongs to someone else** — do not use it, log into anything with it, or explore what it grants access to. Using a credential you weren't authorized to have, even one you "just found," is unauthorized access in most jurisdictions regardless of how it was obtained.
3. **Report it responsibly** — GitHub has a process for reporting exposed secrets, and most cloud providers (AWS, Heroku, etc.) have abuse-reporting channels that will revoke a leaked key once notified. If the repo belongs to a company with a bug bounty program, report it through that program instead of any other channel.
4. GitHub's own [secret scanning](https://docs.github.com/en/code-security/secret-scanning) and [push protection](https://docs.github.com/en/code-security/secret-scanning/push-protection-for-repositories-and-organizations) features exist precisely to catch this class of leak automatically — enabling them on your own repos is a better long-term fix than periodic manual dorking.

---

## ⚠️ Disclaimer & Legal Notice

This category is intended **only** for:

1. Auditing repositories you own or are authorized to audit (your own org, or as part of an authorized security assessment).
2. Official Bug Bounty / responsible disclosure programs, where finding exposed secrets in a company's public repos is explicitly in scope.
3. Academic/educational research into secret-scanning techniques, without acting on any secret discovered.

**Strictly prohibited:** using a credential you find to access an account, system, or data you aren't authorized to access; this applies even if the credential was trivial to find. Accessing a system with someone else's leaked password or key is unauthorized access, not "finding an unlocked door."

### Legal basis in Indonesia (UU ITE No. 19 of 2016)

| Article | Offense | Penalty |
|---------|---------|---------|
| Article 30 | Unauthorized access to another party's system | 6–12 years imprisonment |
| Article 32 | Altering/deleting/transferring another party's data | Up to 8 years imprisonment, fine up to Rp 2 billion |
| Article 35 | Distributing exploit results/misleading information | Up to 12 years imprisonment, fine up to Rp 12 billion |

The developers and this documentation are not responsible for any use of a discovered credential beyond responsible disclosure.

---

*See also: [Bug Bounty Program Discovery Dorks](bug-bounty-dorks.md) for finding the right channel to report anything you find, and the [Database Dorks overview](index.md) for the full `database/` folder structure.*
