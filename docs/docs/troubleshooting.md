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
    * Update your active local build layout directly to AtDork version `>= 1.3.8`.
    * New distribution builds incorporate a parsing pass (`lib/storage.py`) that strips or prefixes symbols (`+`, `=`, `-`, `@`) to block Formula Injection attacks.
