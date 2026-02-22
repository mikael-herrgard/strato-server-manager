# Gandi Domain Setup - Quick Reference

## Automated Setup Script

**Script:** `/opt/server-manager/scripts/setup-gandi-domain.sh`
**TUI:** Server Manager → Maintenance → Setup Gandi Domain
**Validated:** 2026-02-22 (tested on keken.nu — full delete + recreate cycle)

The script performs the complete domain setup in one run: prerequisite checks,
18 DNS records, LiveDNS activation, DNSSEC enablement, and verification.

### Usage

```bash
# From command line
bash /opt/server-manager/scripts/setup-gandi-domain.sh <domain>

# From TUI
server_manager.py → Maintenance → Setup Gandi Domain
```

### What It Does

1. **Prerequisite checks** (all must pass before any changes):
   - `/root/.credentials.env` exists with valid `GANDI_TOKEN`
   - Gandi API token validates (tokeninfo endpoint, falls back to domain list)
   - Domain exists at Gandi (transfer must be complete)
   - Domain exists in Mailcow (MySQL check)
   - DKIM public key exists in Mailcow Redis
   - `mail.villaherrgard.com` resolves to an IP
   - Required tools: `jq`, `dig`, `curl`, `docker`

2. **Creates 18 DNS records** via Gandi LiveDNS PUT API:
   - `@` A → server IP
   - `mail` A → server IP (per-domain webmail)
   - `@` MX → `mail.villaherrgard.com.` priority 10
   - `@` TXT (SPF) → `v=spf1 mx a:mail.villaherrgard.com ip4:{IP} -all`
   - `dkim._domainkey` TXT (DKIM) → public key from Mailcow Redis
   - `_dmarc` TXT (DMARC) → `v=DMARC1; p=quarantine; ...`
   - `mta-sts` A → server IP
   - `_mta-sts` TXT → `v=STSv1; id={YYYYMMDD}0001`
   - `_smtp._tls` TXT (TLS-RPT) → `v=TLSRPTv1; rua=mailto:postmaster@{domain}`
   - `autoconfig` CNAME → `mail.villaherrgard.com.`
   - `autodiscover` CNAME → `mail.villaherrgard.com.`
   - 6 SRV records (autodiscover, imap, imaps, pop3, pop3s, submission)
   - `@` CAA (issue, issuewild, iodef for letsencrypt.org)

3. **Activates Gandi LiveDNS** nameservers (ns-64-a, ns-90-b, ns-58-c)

4. **Enables DNSSEC**: creates signing key, waits for propagation, publishes DS record

5. **Verifies** MX, SPF, DKIM, DMARC via dig against Gandi nameservers

---

## Manual Steps After Script

### NPM SSL Certificate

Request a single certificate covering all three hostnames:
- `{domain}`
- `mta-sts.{domain}`
- `mail.{domain}`

Use **DNS challenge** with Gandi credentials.

### NPM Proxy Hosts

Create 3 proxy hosts, all forwarding to `https://194.164.197.33:4433` (Mailcow):

| Proxy Host | Purpose |
|-----------|---------|
| `{domain}` | Domain root (Mailcow UI) |
| `mta-sts.{domain}` | MTA-STS policy serving |
| `mail.{domain}` | Per-domain webmail access |

**Settings for all three:**
- Scheme: `https`
- Forward IP: `194.164.197.33`
- Forward Port: `4433`
- Force SSL: ✅
- HTTP/2: ✅
- HSTS: ✅
- Block Exploits: ✅

### NPM Advanced Tab (Required for internet.nl compliance)

Paste this into the **Advanced** tab of each Mailcow proxy host:

```nginx
# Strip Mailcow's headers and set correct ones
proxy_hide_header Strict-Transport-Security;
proxy_hide_header Referrer-Policy;

add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
more_set_headers "Referrer-Policy: same-origin";
more_set_headers "Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'self'; form-action 'self'; base-uri 'self';";
```

**Why this is needed:**
- Mailcow's internal nginx sends `Strict-Transport-Security: max-age=15768000` (6 months)
  which fails internet.nl's 1-year minimum requirement
- Mailcow sends `Referrer-Policy: strict-origin` which internet.nl flags
- `proxy_hide_header` strips Mailcow's headers before NPM adds the correct ones
- `more_set_headers` is used for CSP and Referrer-Policy because nginx's `add_header`
  in the server context gets overridden by `add_header` in NPM's location block

### security.txt

Already deployed at `/opt/mailcow-dockerized/data/web/.well-known/security.txt`.
Shared by all domains served through Mailcow — no per-domain setup needed.

---

## Verification

```bash
# Check all records via Gandi API
source /root/.credentials.env
curl -s "https://api.gandi.net/v5/livedns/domains/$DOMAIN/records" \
  -H "Authorization: Bearer $GANDI_TOKEN" | jq -c '.[] | {rrset_name, rrset_type}'

# Check DNSSEC
dig DS $DOMAIN +short
dig @8.8.8.8 +dnssec $DOMAIN A | grep "flags.*ad"

# Check mail records
dig MX $DOMAIN +short
dig TXT $DOMAIN +short | grep spf
dig TXT dkim._domainkey.$DOMAIN +short | grep DKIM
dig TXT _dmarc.$DOMAIN +short | grep DMARC

# internet.nl tests
# Website: https://internet.nl/site/$DOMAIN/
# Mail:    https://internet.nl/mail/$DOMAIN/
```

---

## Domains Status

| Domain | Gandi | Script Run | NPM | Status |
|--------|-------|-----------|-----|--------|
| keken.nu | ✅ Transferred | ✅ 2026-02-22 | ✅ Configured | Production |
| nysattra.se | ⏳ Transferring | — | — | Waiting for transfer |
| villaherrgard.se | ⏳ Transferring | — | — | Waiting for transfer |
| sono-vagnala.se | ⏳ Transferring | — | — | Waiting for transfer |

---

## internet.nl Scores (2026-02-22)

**Website test:** 86% for both keken.nu and villaherrgard.com

| Test | Status | Notes |
|------|--------|-------|
| DNSSEC | ✅ Passed | |
| HTTPS/HSTS | ✅ Passed | 2-year max-age + preload |
| RPKI | ✅ Passed | |
| X-Frame-Options | ✅ Passed | |
| X-Content-Type-Options | ✅ Passed | |
| Referrer-Policy | ✅ Passed | same-origin |
| security.txt | ℹ️ Info | Present and valid |
| CSP | ⚠️ Warning | `unsafe-inline`/`unsafe-eval` required by Mailcow |
| IPv6 | ❌ Failed | Disabled by design (no AAAA records) |

**Score ceiling is 86%** — the remaining deductions are IPv6 (disabled by design)
and CSP (Mailcow requires `unsafe-inline`/`unsafe-eval`).

---

**Last Updated:** 2026-02-22
**Domains Tested:** keken.nu (full delete + recreate), villaherrgard.com (headers)
**Automation Level:** 100% for DNS setup (zero manual steps), NPM config is manual
