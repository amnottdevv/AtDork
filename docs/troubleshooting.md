# Operational Troubleshooting Manual

Resolution protocols for common failure vectors encountered during large-scale network scanning sweeps.

---

## 1. Engine Backend Returning HTTP Code 429 (Rate-Limited)

* **Symptom:** Logs emit repetitive `429 Too Many Requests` notifications, and result vectors drop to zero.
* **Mitigation Actions:**
    * Increase your standard processing delay footprint: `--delay 4`.
    * Inject dynamic spacing algorithms into the engine loop: `--adaptive-delay`.
    * Deploy an expansive distribution pool of network targets: `--proxy-file proxies.txt`.
    * Shift target focus over to alternative data indexing platforms: `--backend startpage` or `--backend yandex`.

## 2. Proxies Falling Out of Pool Sync

* **Symptom:** Runtime outputs show extensive proxy failures, or execution hangs inside connection timeouts.
* **Mitigation Actions:**
    * Verify proxy routing string schema declaration definitions. Format must strictly align to: `scheme://user:pass@host:port`.
    * Ensure that you deploy SOCKS5h variants (`socks5h://`) when leveraging Tor networks to force DNS lookups down the remote proxy pipeline rather than parsing local leak nodes.

## 3. CSV Output Rendering Corrupt or Displaying Security Warnings

* **Symptom:** Spreadsheet processors (Microsoft Excel, LibreOffice Calc) display warning flags regarding executable expressions or broken formatting blocks upon opening exported maps.
* **Mitigation Actions:**
    * Update to the latest release: `pip install --upgrade atdork` (current: `1.4.0`).
    * Distribution builds since `1.3.8` incorporate a parsing pass (`lib/storage.py`) that strips or prefixes symbols (`+`, `=`, `-`, `@`) to block Formula Injection attacks.

## 4. "Atdork-DB repository not found"

* **Symptom:** `atdork search`, `atdork install`, or `--database-dork` exits with `Atdork-DB repository not found. Looked in: ...`
* **Cause:** The dork database is a separate checkout that hasn't been cloned (or discovered) yet.
* **Mitigation Actions:**
    * Clone it once: `git clone https://github.com/amnottdevv/Atdork-DB.git ~/Atdork-DB`
    * Or point AtDork at an existing checkout: `--db-repo /path/to/Atdork-DB` or `export ATDORK_DB_REPO=/path/to/Atdork-DB`.
    * Docker users: the image bundles the database at `/opt/atdork-db` — this error should never occur; if it does, you overrode `ATDORK_DB_REPO` with a bad path.

## 5. "No package matches '<ref>'" or Ambiguous Shorthand

* **Symptom:** `install`/`uninstall` fails with `No package matches ...` (optionally with a `Did you mean:` line), or `Ambiguous shorthand`.
* **Mitigation Actions:**
    * Find the exact ref: `atdork search <keyword>` or browse the [web catalog](https://amnottdevv.github.io/Atdork-DB/).
    * Use the canonical form `@folder/file.txt` when a shorthand prefix matches several folders.
    * Stale refs after manual DB edits? Rebuild the manifest inside the checkout: `atdork index --build`.

## 6. Stale Dork Data

* **Symptom:** New folders or files (e.g. fresh GHDB sync) don't show up in `atdork search` / `atdork index`.
* **Mitigation Actions:**
    * Refresh the checkout: `atdork update` (a `git pull --ff-only` on Atdork-DB).
    * Verify you're reading the checkout you think: the discovery order is `--db-repo` → `ATDORK_DB_REPO` → config `db_repo` → `~/Atdork-DB` → sibling → `./Atdork-DB`.

## 7. Docker: Installed Packages Don't Persist

* **Symptom:** `atdork install ...` succeeds, but the next `docker run` shows an empty `atdork installed`.
* **Cause:** The container filesystem is ephemeral — each `docker run` starts fresh.
* **Mitigation Actions:**
    * Mount a volume over the store: `-v atdork-store:/home/atdork/.atdork`.
    * Or skip the store entirely and run refs straight from the bundled database: `--database-dork @cve` (works without `install`).

See [Docker](docker.md) for volumes, bind mounts, and compose examples.

## 8. Environment: "… is not an AtDork environment" or "outside the environment"

* **Symptom:** `--env`/`ATDORK_ENV` fails with `missing .atdork-env`, or a path is rejected with `resolves to '…' which is outside the environment`.
* **Mitigation Actions:**
    * Create the workspace first: `atdork env create <path>` — an environment is a plain folder with a marker, not any directory.
    * While an environment is active all writes must stay inside its root; relative paths already resolve **against the root** (`results/x.json` → `<root>/results/x.json`), so prefer those.
    * Output still appearing in `./results/`? No environment is actually active — verify with `atdork env which`.
    * Full guide: [Environment](features/environment.md).
