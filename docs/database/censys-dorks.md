# Censys Search Dorks (`database/censys-dorks/censysdork.txt`)

Unlike the Google/Bing/DuckDuckGo dorks elsewhere in this database, Censys
queries search a database of **internet-wide scan results** — banners,
TLS certificates, JARM fingerprints, and service metadata collected by
actually connecting to hosts. That makes this category fundamentally about
**asset and infrastructure discovery**, not web-app parameter fuzzing, and
it spans three very different use cases that deserve different handling:

```
database/censys-dorks/
└── censysdork.txt
```

1. **Malware/C2 threat-intelligence hunting** — finding malicious infrastructure (Cobalt Strike, Sliver, various RATs) so defenders can track, block, or report it. This is a defensive use case by nature.
2. **Industrial Control Systems (ICS/OT) discovery** — finding internet-exposed physical infrastructure (power meters, gas pump controllers, wind turbines, EV chargers). This carries real-world physical-safety implications that web app testing doesn't.
3. **Misconfigured cloud services & dashboards** — exposed Redis, Kubernetes, admin dashboards. Same authorized-testing rules as the rest of this database apply here.

---

## 1. Malware & C2 Infrastructure Hunting (threat intelligence)

These fingerprints (TLS certificate hashes, JARM fingerprints, HTTP body
hashes) identify known command-and-control frameworks and malware panels.
Security teams use these to find and report active malicious
infrastructure — this is standard threat-intel/blue-team tradecraft, the
same way antivirus vendors fingerprint malware samples.

```text
# Cobalt Strike team servers
services.tls.certificates.leaf_data.issuer.common_name: "Major Cobalt Strike"

# Metasploit servers
services.http.response.html_title: "Metasploit" and
services.tls.certificates.leaf_data.subject.organization: "Rapid7"

# Sliver C2
services.jarm.fingerprint: "3fd21b20d00000021c43d21b21b43d41226dd5dfc615dd4a96265559485910"

# Unauthenticated open directories serving known offensive-tool filenames
same_service(
    services.http.response.html_title: "Index of /"
    and services.http.response.body: /.*?(cobaltstrike|sliver|mimikatz|rclone)\.(exe|ps1|bin).*/
)
```

```bash
atdork --database-dork censys-dorks/censysdork --backend censys -r 20
```

**What to do with a hit:** report it. Censys and most JARM/certificate
fingerprints exist specifically so defenders can identify and take down
malicious infrastructure or feed it into blocklists — that's the intended
downstream action, not connecting to or interacting with the server
yourself.

---

## 2. Industrial Control Systems / OT Discovery

> **Read this section before running anything in this category.**
>
> Unlike a website with an LFI bug, the systems these queries find are
> often **physical infrastructure**: gas station fuel tank monitors,
> electric vehicle chargers, wind turbine controllers, power meters. A
> few things make this category categorically different from the rest of
> this database:
>
> - **Interacting with these devices can cause real-world physical effects** — industrial protocols (Modbus, S7, BACnet, etc.) were mostly designed assuming a trusted network and often have no authentication at all. Sending even a "read" command to a fragile or legacy OT device can crash it or trigger unintended behavior.
> - **Discovery is not authorization.** Finding that a device is reachable tells you nothing about who owns it or whether you have any right to touch it. There is no equivalent here to "it's my own test site" — you almost certainly do not know whose gas pump or turbine this is.
> - **This is the domain of ICS-CERT / CISA advisories, not casual pentesting.** If you're doing authorized OT security work, it's a specialized discipline with its own safety protocols (usually requiring coordination with the asset owner and often physical presence or a lab-replica environment before touching a live control system).
>
> The responsible use of ICS-discovery queries is **awareness and reporting** — e.g. identifying that a critical system is unexpectedly internet-facing so it can be reported to the owner or a national CERT — not connecting to or issuing commands against it.

```text
# Generic ICS protocol discovery
services.service_name: {BACNET, CODESYS, EIP, FINS, FOX, IEC60870_5_104, S7, MODBUS}

# Add this to exclude honeypots (hosts with 100+ services)
services.truncated: false
```

```bash
# Discovery only — do not follow up by connecting to anything found
atdork --database-dork censys-dorks/censysdork --backend censys --database-preview
```

If you find an exposed ICS/OT device that looks like real critical
infrastructure (utilities, transportation, medical, industrial), the
appropriate action is reporting it to [CISA's ICS reporting
channel](https://www.cisa.gov/report) (or your country's equivalent CERT),
not further probing.

---

## 3. Misconfigured Cloud Services & Dashboards

This part follows the same rules as the [CMS Dorks](cms-dorks.md) and
[Common Dorks](common-dorks.md) categories — authorized testing only,
confirm and report, don't exploit further.

```text
# Unauthenticated Redis
services.redis.ping_response: "PONG"

# Misconfigured Kubernetes
services.kubernetes.pod_names: *

# Exposed dashboards
services.http.response.html_title: "Welcome to ntopng"
same_service(services.http.request.uri: "*/dashboard/" and services.http.response.html_title: "Traefik")
```

```bash
atdork --database-dork censys-dorks/censysdork --backend censys -r 20 --filter-vuln exposed-service
```

---

## ⚠️ Disclaimer & Legal Notice

This category is intended **only** for:

1. Security testing on infrastructure you own.
2. Official Bug Bounty programs with explicit written authorization from the target owner.
3. Threat-intelligence research (identifying malicious infrastructure) intended for reporting/blocklisting, not interaction.
4. Reporting exposed critical infrastructure to the responsible owner or a national CERT.

**Strictly prohibited:** connecting to, sending commands to, or otherwise interacting with any industrial control system, OT device, or piece of critical infrastructure without explicit authorization from its owner — regardless of whether it appears unauthenticated. Also prohibited: using any malware/C2 fingerprint hit to access or interact with the malicious server for any purpose other than reporting it.

### Legal basis in Indonesia (UU ITE No. 19 of 2016)

| Article | Offense | Penalty |
|---------|---------|---------|
| Article 30 | Unauthorized access to another party's system | 6–12 years imprisonment |
| Article 32 | Altering/deleting/transferring another party's data | Up to 8 years imprisonment, fine up to Rp 2 billion |
| Article 35 | Distributing exploit results/misleading information | Up to 12 years imprisonment, fine up to Rp 12 billion |

Interfering with critical infrastructure carries separate and typically far
harsher penalties in most jurisdictions beyond standard computer-misuse
law, given the potential for physical harm.

---

*See also: [CMS Dorks](cms-dorks.md), [GitHub Secret-Exposure Dorks](github-dorks.md), and the [Database Dorks overview](index.md) for the full `database/` folder structure.*
