# Server Infrastructure Report

**Server:** VPS at 194.164.197.33
**Hostname:** mail.villaherrgard.com
**OS:** Ubuntu with IPv6 disabled at kernel level
**Report Date:** 2026-02-21
**Timezone:** Europe/Stockholm

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Architecture Overview](#2-architecture-overview)
3. [Domain Strategy](#3-domain-strategy)
4. [Component: Nginx Proxy Manager](#4-nginx-proxy-manager)
5. [Component: Mailcow Email Server](#5-mailcow-email-server)
6. [Component: Monitoring Stack](#6-monitoring-stack)
7. [Component: Server Manager](#7-server-manager)
8. [DNS Records Reference](#8-dns-records-reference)
9. [Certificate Management](#9-certificate-management)
10. [Backup & Disaster Recovery](#10-backup--disaster-recovery)
11. [Credential & Secret Inventory](#11-credential--secret-inventory)
12. [Checklists](#12-checklists)
13. [Known Issues & Action Items](#13-known-issues--action-items)
14. [Future Work](#14-future-work)

---

## 1. Executive Summary

This VPS hosts a self-managed email and infrastructure platform built on Docker. The core services are:

- **Mailcow** -- A full email server stack (Postfix, Dovecot, SOGo webmail, Rspamd spam filtering, ClamAV antivirus) handling mail for multiple domains, all pointed at `mail.villaherrgard.com` as the MX host.
- **Nginx Proxy Manager (NPM)** -- Reverse proxy providing SSL termination for all web-facing services. Manages Let's Encrypt wildcard certificates via DNS challenge.
- **Grafana + InfluxDB** -- Monitoring stack collecting water level sensor data from PressureSuite Cloud, visualized in Grafana dashboards.
- **Server Manager** -- Custom Python application providing automated Borg backups to rsync.net, scheduled via cron, with a full disaster recovery capability that can restore the entire server from a fresh VPS in ~12-15 minutes.
- **Portainer** -- Docker management UI.

The infrastructure domain is `villaherrgard.com` (Cloudflare DNS). Production mail domains (`nysattra.se`, `villaherrgard.se`, `sono-vagnala.se`) are being migrated from one.com to Gandi for DNS, with email hosted on this Mailcow instance. A test domain (`keken.nu`) on Gandi was used to validate the migration workflow and will be retired.

All services are backed up daily to rsync.net using Borg deduplication. A two-phase disaster recovery script (`/root/init.sh`) can rebuild the entire server from scratch with minimal manual intervention.

---

## 2. Architecture Overview

### 2.1 Network & Traffic Flow

```
                        Internet
                           |
                    194.164.197.33
                           |
              +------------+------------+
              |                         |
         Ports 80/443              Mail Ports (direct)
              |                    25, 465, 587
         NPM (Docker)             110, 143, 993, 995, 4190
         SSL termination                |
              |                    Mailcow Postfix/Dovecot
    +---------+---------+          (Docker containers)
    |         |         |
  :4433     :3000     :81
  Mailcow   Grafana   NPM Admin
  Web UI    (host)    (internal)
```

**Key points:**
- HTTP/HTTPS traffic goes through NPM, which terminates SSL and proxies to backend services
- Mail ports (SMTP/IMAP/POP3) go directly to Mailcow containers, bypassing NPM
- Grafana and InfluxDB run as host systemd services, not in Docker
- Portainer runs in Docker with host networking (port 9443)

### 2.2 Docker Networks

| Network | Subnet | Services |
|---|---|---|
| `nginx_default` | 172.18.0.0/16 | NPM app + MariaDB |
| `mailcowdockerized_mailcow-network` | 172.22.1.0/24 | All 18 Mailcow containers |
| `bridge` (default) | 172.17.0.0/16 | Portainer |

The Docker networks are isolated. NPM reaches Mailcow via the host IP (194.164.197.33:4433), not through Docker networking.

### 2.3 Port Map

| Port | Service | Exposure |
|---|---|---|
| 80 | NPM (HTTP redirect to HTTPS) | Public |
| 443 | NPM (HTTPS reverse proxy) | Public |
| 81 | NPM Admin UI | Internal only |
| 25 | Postfix SMTP | Public |
| 465 | Postfix SMTPS | Public |
| 587 | Postfix Submission | Public |
| 110 | Dovecot POP3 | Public |
| 143 | Dovecot IMAP | Public |
| 993 | Dovecot IMAPS | Public |
| 995 | Dovecot POP3S | Public |
| 4190 | Dovecot ManageSieve | Public |
| 3000 | Grafana | Localhost (proxied by NPM) |
| 3022 | NPM SSH tunnel (Grafana) | Public |
| 4080 | Mailcow HTTP | Internal (NPM proxies) |
| 4433 | Mailcow HTTPS | Internal (NPM proxies) |
| 8086 | InfluxDB | Localhost |
| 8000 | Portainer agent tunnel | Public |
| 9443 | Portainer UI | Public |
| 13306 | MariaDB (Mailcow) | Localhost |
| 7654 | Redis (Mailcow) | Localhost |

### 2.4 Running Services Summary

**Docker containers (21):**
- 2 NPM (app + MariaDB)
- 18 Mailcow (postfix, dovecot, nginx, php-fpm, sogo, rspamd, clamd, olefy, redis, mysql, unbound, acme, watchdog, netfilter, dockerapi, ofelia, memcached, postfix-tlspol)
- 1 Portainer

**Systemd services (3):**
- `grafana-server.service` -- Grafana dashboard server
- `influxdb.service` -- InfluxDB time series database
- `pressuresuite-influx-bridge.timer` -- Data collection (runs daily at 02:30 and 12:30)

### 2.5 IPv6

IPv6 is **disabled at the kernel level** via GRUB parameter `ipv6.disable=1`. This affects the entire system and all services are configured for IPv4-only operation:

- `mailcow.conf`: `ENABLE_IPV6=false`
- Postfix: `inet_protocols = ipv4`
- Dovecot: `listen = *` (IPv4 only)
- Unbound: `do-ip6: no`

### 2.6 Firewall

UFW is **inactive**. Firewall rules are managed by:
- **Docker iptables** -- Automatically manages container port exposure
- **Mailcow netfilter** -- The `netfilter-mailcow` container manages fail2ban-style blocking for mail services
- **Tailscale** -- `ts-input` and `ts-forward` chains for Tailscale VPN traffic

The INPUT policy is ACCEPT and the FORWARD policy is DROP (with Docker/Mailcow/Tailscale exceptions).

---

## 3. Domain Strategy

### 3.1 Domain Overview

| Domain | DNS Provider | Status | Purpose |
|---|---|---|---|
| **villaherrgard.com** | Cloudflare | Active | Infrastructure domain, reverse DNS, mail server hostname (`mail.villaherrgard.com`), all `*.villaherrgard.com` subdomains |
| **keken.nu** | Gandi LiveDNS | Active (retiring) | Test domain used to validate Gandi migration workflow. Will be retired once DR confidence is established. |
| **nysattra.se** | one.com (transferring to Gandi) | Next migration | First production mail domain |
| **villaherrgard.se** | one.com (transferring to Gandi) | Future | Second production mail domain |
| **sono-vagnala.se** | one.com (transferring to Gandi) | Future | Third production mail domain |

### 3.2 Domain Roles

**villaherrgard.com** is the infrastructure domain. It hosts:
- `mail.villaherrgard.com` -- The MX host for ALL domains. Reverse DNS (PTR) points here.
- `nginx.villaherrgard.com` -- NPM admin interface
- `portainer.villaherrgard.com` -- Portainer UI
- `grafana.villaherrgard.com` -- Grafana dashboards
- `mta-sts.villaherrgard.com` -- MTA-STS policy endpoint
- `autoconfig.villaherrgard.com` -- Mail client autoconfiguration
- `autodiscover.villaherrgard.com` -- Outlook autodiscovery
- `plex.villaherrgard.com` -- Plex (via Tailscale)
- `flow.villaherrgard.com` -- pfSense (via Tailscale)
- `valheim.villaherrgard.com` -- Gaming server (via Tailscale)

**All other domains** (keken.nu, nysattra.se, villaherrgard.se, sono-vagnala.se) are mail domains only. They point their MX record to `mail.villaherrgard.com` and need their own SPF/DKIM/DMARC/MTA-STS records, but do not host any subdomains or services.

### 3.3 Migration Strategy

For each domain being migrated from one.com to this mail server:

1. **Transfer domain registration** from one.com to Gandi
2. **Activate Gandi LiveDNS + DNSSEC** via API (fully automated -- see Section 12.5)
3. **Create DNS records** via Gandi API (MX, SPF, DKIM, DMARC, MTA-STS, autoconfig, autodiscover, SRV, CAA)
4. **Add domain to Mailcow** admin panel
5. **Generate DKIM key** in Mailcow and add to DNS
6. **Create wildcard SSL certificate** in NPM using Gandi DNS challenge
7. **Create NPM proxy hosts** for the domain's web endpoints (root, mta-sts)
8. **Create mailboxes** and migrate email from one.com
9. **Verify** using internet.nl, mail-tester.com, and MXToolbox

---

## 4. Nginx Proxy Manager

### 4.1 Installation

**Location:** `/root/nginx/`
**Docker Compose:** `/root/nginx/docker-compose.yml`
**Containers:** `nginx-app-1` (NPM), `nginx-db-1` (MariaDB)

**Ports:**
- 80 (HTTP, public)
- 443 (HTTPS, public)
- 81 (Admin UI, internal -- not exposed to SSL)
- 3022 (SSH tunnel for Grafana)

### 4.2 Proxy Hosts (13 active)

| Config | Domain | Backend |
|---|---|---|
| 2.conf | nginx.villaherrgard.com | NPM admin (:81) |
| 3.conf | portainer.villaherrgard.com | Portainer (:9443) |
| 4.conf | grafana.villaherrgard.com | Grafana (:3000) |
| 5.conf | plex.villaherrgard.com | Plex (via Tailscale) |
| 8.conf | mail.villaherrgard.com | Mailcow (:4433) |
| 9.conf | autodiscover.villaherrgard.com | Mailcow (:4433) |
| 10.conf | autoconfig.villaherrgard.com | Mailcow (:4433) |
| 11.conf | villaherrgard.com | Mailcow (:4433) |
| 12.conf | flow.villaherrgard.com | pfSense (via Tailscale) |
| 13.conf | valheim.villaherrgard.com | pfSense (via Tailscale) |
| 14.conf | mta-sts.villaherrgard.com | Localhost (HTTPS) |
| 15.conf | mta-sts.keken.nu | Localhost (HTTPS) |
| 16.conf | keken.nu | Mailcow (:4433) |

### 4.3 SSL Certificates

| Certificate | Domains | DNS Challenge | Credential File | Status |
|---|---|---|---|---|
| npm-2 | `*.villaherrgard.com`, `villaherrgard.com` | `dns-cloudflare` | `credentials-2` | Working |
| npm-6 | `*.keken.nu`, `keken.nu` | `dns-gandi` | `credentials-6` | Working (issued 2026-02-21, expires 2026-05-22) |

**Certificate settings:**
- Key type: ECDSA (secp384r1)
- Preferred chain: ISRG Root X1
- Certbot version: 5.1.0

**When adding new domains:** Create a new npm-N certificate using `dns-gandi` authenticator with Gandi credentials (see Section 9). NPM creates a numbered credential file (`credentials-N`) for each certificate. The Gandi token sync scripts dynamically scan all `credentials-*` files for `dns_gandi_token=` lines, so new files are picked up automatically.

### 4.4 Key Files

```
/root/nginx/
  docker-compose.yml                              # NPM + MariaDB container definitions
  data/nginx/proxy_host/*.conf                    # Individual proxy host configs
  letsencrypt/
    live/npm-2/                                   # villaherrgard.com cert (active)
    live/npm-6/                                   # keken.nu cert (active, Gandi DNS challenge)
    renewal/npm-2.conf                            # Certbot renewal config (Cloudflare)
    renewal/npm-6.conf                            # Certbot renewal config (Gandi)
    credentials/credentials-2                     # Cloudflare API token
    credentials/credentials-6                     # Gandi API token (synced from .credentials.env)
    renewal-hooks/deploy/sync-mailcow-certs.sh    # Post-renewal: sync cert to Mailcow + TLSA update
```

---

## 5. Mailcow Email Server

### 5.1 Installation

**Location:** `/opt/mailcow-dockerized/`
**Hostname:** `mail.villaherrgard.com`
**Web UI:** `https://mail.villaherrgard.com` (via NPM on :4433)
**Containers:** 18 total

### 5.2 Container Stack

| Container | Function | Ports |
|---|---|---|
| postfix-mailcow | SMTP server | 25, 465, 587 (public) |
| dovecot-mailcow | IMAP/POP3 server | 110, 143, 993, 995, 4190 (public) |
| nginx-mailcow | Web frontend | 4080, 4433 (internal) |
| php-fpm-mailcow | PHP processing | 9000 (internal) |
| sogo-mailcow | Webmail/calendar/contacts | (internal) |
| rspamd-mailcow | Spam/DKIM/ARC | (internal) |
| clamd-mailcow | Antivirus | (internal) |
| olefy-mailcow | Office doc scanning | (internal) |
| mysql-mailcow | MariaDB database | 13306 (localhost) |
| redis-mailcow | Key-value store (DKIM keys) | 7654 (localhost) |
| unbound-mailcow | Internal DNS resolver | 53 (internal) |
| acme-mailcow | Let's Encrypt (disabled, NPM handles) | (internal) |
| watchdog-mailcow | Health monitoring | (internal) |
| netfilter-mailcow | Fail2ban-style blocking | (internal) |
| dockerapi-mailcow | Docker API wrapper | (internal) |
| ofelia-mailcow | Job scheduler | (internal) |
| memcached-mailcow | Caching | (internal) |
| postfix-tlspol-mailcow | TLS policy | (internal) |

### 5.3 Key Configuration

**File:** `/opt/mailcow-dockerized/mailcow.conf`

Critical settings:
```
MAILCOW_HOSTNAME=mail.villaherrgard.com
ENABLE_IPV6=false
SKIP_LETS_ENCRYPT=y          # NPM handles certificates
SKIP_HTTP_VERIFICATION=y
HTTP_PORT=4080               # Behind NPM
HTTPS_PORT=4433              # Behind NPM
HTTP_BIND=0.0.0.0
HTTPS_BIND=0.0.0.0
```

### 5.4 Mail Flow

**Inbound mail:**
```
Internet → MX lookup (mail.villaherrgard.com) → Port 25 → Postfix
  → Rspamd (spam check, DKIM verify) → ClamAV (virus scan)
  → Dovecot (local delivery to mailbox)
```

**Outbound mail:**
```
Mail client → Port 587 (STARTTLS) or 465 (SSL) → Postfix (authenticated)
  → Rspamd (DKIM sign) → Internet
```

**Webmail:**
```
Browser → NPM (:443) → Mailcow nginx (:4433) → SOGo
```

### 5.5 Email Security Stack

| Protocol | Purpose | Configuration |
|---|---|---|
| **SPF** | Declares which IPs can send mail for the domain | TXT record on domain |
| **DKIM** | Cryptographically signs outgoing mail | Key in Rspamd/Redis, public key in DNS |
| **DMARC** | Policy for handling SPF/DKIM failures | TXT record `_dmarc.domain` |
| **DANE/TLSA** | Pins the mail server's TLS certificate in DNS | TLSA records, auto-updated via Cloudflare API |
| **MTA-STS** | Enforces TLS for incoming SMTP connections | Policy served at `mta-sts.domain/.well-known/mta-sts.txt` |
| **TLS-RPT** | Receives reports about TLS failures | TXT record `_smtp._tls.domain` |
| **CAA** | Restricts which CAs can issue certificates | CAA records on domain |
| **rDNS/PTR** | Reverse DNS matching forward DNS | Configured with ISP, points to `mail.villaherrgard.com` |

### 5.6 Adding a Domain to Mailcow

In the Mailcow admin UI (`https://mail.villaherrgard.com/admin/`):

1. **Configuration** --> **Mail Setup** --> **Domains** --> **Add domain**
2. Enter the domain name, set max mailboxes/aliases
3. Go to **Configuration** --> **ARC/DKIM keys** --> Generate DKIM key for the new domain
4. Copy the DKIM public key and add it to the domain's DNS as a TXT record

### 5.7 Key Files

```
/opt/mailcow-dockerized/
  mailcow.conf                                    # Main configuration (passwords, ports, hostname)
  docker-compose.yml                              # Container definitions
  update-tlsa-cloudflare.sh                       # TLSA record automation for Cloudflare
  data/
    conf/dovecot/dovecot.conf                     # Dovecot config (IPv4-only)
    conf/postfix/main.cf                          # Postfix config (IPv4-only)
    conf/unbound/unbound.conf                     # Internal DNS (IPv4-only)
    conf/mysql/my.cnf                             # MariaDB config
    assets/ssl/cert.pem                           # Active SSL certificate (synced from NPM)
    assets/ssl/key.pem                            # Active SSL private key
```

---

## 6. Monitoring Stack

### 6.1 Components

**InfluxDB 2.x** -- Time series database
- Service: `influxdb.service` (systemd)
- Port: 8086 (localhost)
- Organization: Textilia
- Data: `/var/lib/influxdb/`
- Config: systemd service at `/etc/systemd/system/influxdb.service`

**Grafana** -- Visualization dashboards
- Service: `grafana-server.service` (systemd)
- Port: 3000 (localhost, proxied by NPM at `grafana.villaherrgard.com`)
- Data: `/var/lib/grafana/`
- Config: `/etc/grafana/grafana.ini`
- Provisioning: `/etc/grafana/provisioning/`

**PressureSuite InfluxDB Bridge** -- Data collector
- Location: `/root/python/pressuresuite-influx-bridge/`
- Service: `pressuresuite-influx-bridge.service` (oneshot)
- Timer: `pressuresuite-influx-bridge.timer` (daily at 02:30 and 12:30 CET)
- Purpose: Fetches water level data from PressureSuite Cloud API and stores in InfluxDB
- Bucket: `waterlevels`

### 6.2 Monitored Devices

| Device ID | Location |
|---|---|
| 31929 | Gavel-Langsjon |
| 3403 | Skedviken |
| 3402 | Syningen |
| 3399 | Vallbyan |
| 3400 | Vallbyandamm |

Measurement channels: P1 (Pressure), PBaro (Barometric Pressure), TBaro (Barometric Temperature).

### 6.3 Key Files

```
/root/python/pressuresuite-influx-bridge/
  main.py                                         # Bridge application
  .env                                            # API tokens, InfluxDB credentials
  config.yaml                                     # Device configuration
  requirements.txt                                # Python dependencies
/etc/grafana/grafana.ini                          # Grafana configuration
/var/lib/grafana/                                 # Grafana data (dashboards, users)
/var/lib/influxdb/                                # InfluxDB data (measurements)
```

---

## 7. Server Manager

### 7.1 Overview

**Location:** `/opt/server-manager/`
**Source:** `git@github.com:mikael-herrgard/strato-server-manager.git` (main branch)
**Version:** 1.2
**Status:** Production ready (Phases 1-7 complete)
**Code:** ~8,300 lines Python across 20 files

The server manager provides:
- Automated Borg backups to rsync.net for 6 services
- Complete disaster recovery from fresh VPS
- Interactive TUI (pythondialog) for manual operations
- CLI (`cli.py`) for automated/cron operations
- Service monitoring, maintenance, and updates

### 7.2 Entry Points

**Interactive TUI:**
```bash
/opt/server-manager/server_manager.py
```

**CLI (for automation/cron):**
```bash
/opt/server-manager/cli.py backup <service> [--verify]
/opt/server-manager/cli.py restore <service> [--archive NAME] [--list] [--yes]
/opt/server-manager/cli.py restore-all [--yes]
/opt/server-manager/cli.py cleanup [--retention-days 30]
```

### 7.3 Backup System

**Backend:** Borg Backup with deduplication
**Remote storage:** `ssh://zh5554@zh5554.rsync.net/./backups/{service}-backup`
**Borg version:** borg14 (on rsync.net)
**Compression:** zstd,3
**Encryption:** repokey
**Retention:** 7 daily, 4 weekly, 6 monthly

**Services backed up:**

| Service | What's included | Cron |
|---|---|---|
| credentials | API tokens (.credentials.env), DNS config (.dns-config) | Daily 01:55 |
| nginx | NPM data, docker-compose, letsencrypt | Daily 02:00 |
| mailcow-directory | Config, certs, docker-compose (not mail data) | Daily 02:30 |
| mailcow | Full mail data via official backup script | Daily 03:00 |
| server-manager | settings.yaml, notifications.yaml | Daily 05:00 |
| monitoring-stack | Grafana data/config, InfluxDB data/config, bridge app | Daily 05:30 |

All cron jobs use `flock` to prevent concurrent runs. Logs go to `/opt/server-manager/logs/backup-{service}-cron.log`.

### 7.4 Key Files

```
/opt/server-manager/
  server_manager.py                               # TUI entry point
  cli.py                                          # CLI entry point (cron, automation)
  config/
    settings.yaml                                 # Main configuration
    notifications.yaml                            # Email notification config (disabled)
  lib/
    backup.py                                     # Backup operations (772 lines)
    restore.py                                    # Restore operations (998 lines)
    installation.py                               # Docker/service installation (399 lines)
    scheduling.py                                 # Cron management (513 lines)
    maintenance.py                                # Updates, cleanup (635 lines)
    monitoring.py                                 # Status/stats (532 lines)
    notifications.py                              # SMTP notifications (461 lines)
    config.py                                     # Config management (320 lines)
    ui.py                                         # TUI framework (682 lines)
    utils.py                                      # Utilities (486 lines)
    handlers/                                     # TUI menu handlers (6 files, ~2,055 lines)
  scripts/
    automated-backup.sh                           # Cron wrapper for cli.py backup
    cleanup-backups.sh                            # Cron wrapper for cli.py cleanup
    gandi-token-renew.sh                          # Gandi PAT auto-renewal (daily check + renewal)
    update-dns-ip.sh                              # DNS A record + SPF updater (IP migration)
  logs/                                           # Application and cron logs
```

---

## 8. DNS Records Reference

### 8.1 Complete DNS Record Set for villaherrgard.com (Cloudflare)

This is the infrastructure domain. These records are already configured and working.

```dns
# Core records
villaherrgard.com              A       194.164.197.33
mail.villaherrgard.com         A       194.164.197.33
mta-sts.villaherrgard.com      A       194.164.197.33

# MX
villaherrgard.com              MX      10 mail.villaherrgard.com

# Reverse DNS (configured with ISP)
194.164.197.33                 PTR     mail.villaherrgard.com

# SPF
villaherrgard.com              TXT     "v=spf1 ip4:194.164.197.33 -all"

# DKIM (key generated by Mailcow)
dkim._domainkey.villaherrgard.com  TXT  "v=DKIM1;k=rsa;t=s;s=email;p=MIIBIjAN..."

# DMARC
_dmarc.villaherrgard.com       TXT     "v=DMARC1; p=quarantine; adkim=s; aspf=s"

# DANE/TLSA (auto-updated by update-tlsa-cloudflare.sh)
_25._tcp.mail.villaherrgard.com   TLSA  3 1 1 [fingerprint]
_465._tcp.mail.villaherrgard.com  TLSA  3 1 1 [fingerprint]
_587._tcp.mail.villaherrgard.com  TLSA  3 1 1 [fingerprint]

# MTA-STS
_mta-sts.villaherrgard.com     TXT     "v=STSv1; id=202601070001;"
_smtp._tls.villaherrgard.com   TXT     "v=TLSRPTv1; rua=mailto:postmaster@villaherrgard.com"

# Autoconfiguration
autoconfig.villaherrgard.com   CNAME   mail.villaherrgard.com
autodiscover.villaherrgard.com CNAME   mail.villaherrgard.com

# SRV records
_autodiscover._tcp.villaherrgard.com  SRV  0 5 443 mail.villaherrgard.com
_imap._tcp.villaherrgard.com          SRV  0 1 993 mail.villaherrgard.com
_imaps._tcp.villaherrgard.com         SRV  0 1 993 mail.villaherrgard.com
_pop3._tcp.villaherrgard.com          SRV  0 1 995 mail.villaherrgard.com
_pop3s._tcp.villaherrgard.com         SRV  0 1 995 mail.villaherrgard.com
_submission._tcp.villaherrgard.com    SRV  0 1 587 mail.villaherrgard.com

# CAA
villaherrgard.com              CAA     0 issue "letsencrypt.org"
villaherrgard.com              CAA     0 issuewild "letsencrypt.org"
villaherrgard.com              CAA     0 issuemail ";"
villaherrgard.com              CAA     0 iodef "mailto:postmaster@villaherrgard.com"

# Service subdomains (A records, NOT proxied through Cloudflare)
nginx.villaherrgard.com        A       194.164.197.33
portainer.villaherrgard.com    A       194.164.197.33
grafana.villaherrgard.com      A       194.164.197.33
```

### 8.2 DNS Record Template for New Mail Domains (Gandi)

When adding `nysattra.se`, `villaherrgard.se`, or `sono-vagnala.se` to the mail server, create these records at Gandi:

```dns
# Replace DOMAIN with the actual domain name (e.g., nysattra.se)

# A record (for web/MTA-STS access)
DOMAIN                         A       194.164.197.33

# MX (all domains point to the shared mail server)
DOMAIN                         MX      10 mail.villaherrgard.com.

# SPF (authorize the mail server IP and hostname)
DOMAIN                         TXT     "v=spf1 mx a:mail.villaherrgard.com ip4:194.164.197.33 -all"

# DKIM (get the public key from Mailcow admin after generating)
dkim._domainkey.DOMAIN         TXT     "v=DKIM1;k=rsa;t=s;s=email;p=<KEY_FROM_MAILCOW>"

# DMARC
_dmarc.DOMAIN                 TXT     "v=DMARC1; p=quarantine; adkim=s; aspf=s"

# MTA-STS (increment the id on each policy change)
mta-sts.DOMAIN                A       194.164.197.33
_mta-sts.DOMAIN               TXT     "v=STSv1; id=202602200001;"
_smtp._tls.DOMAIN             TXT     "v=TLSRPTv1; rua=mailto:postmaster@DOMAIN"

# Autoconfiguration
autoconfig.DOMAIN             CNAME   mail.villaherrgard.com.
autodiscover.DOMAIN           CNAME   mail.villaherrgard.com.

# SRV records for client autoconfiguration
_autodiscover._tcp.DOMAIN     SRV     0 5 443 mail.villaherrgard.com.
_imap._tcp.DOMAIN             SRV     0 1 993 mail.villaherrgard.com.
_imaps._tcp.DOMAIN            SRV     0 1 993 mail.villaherrgard.com.
_pop3._tcp.DOMAIN             SRV     0 1 995 mail.villaherrgard.com.
_pop3s._tcp.DOMAIN            SRV     0 1 995 mail.villaherrgard.com.
_submission._tcp.DOMAIN       SRV     0 1 587 mail.villaherrgard.com.

# CAA (restrict certificate issuance to Let's Encrypt)
DOMAIN                        CAA     0 issue "letsencrypt.org"
DOMAIN                        CAA     0 issuewild "letsencrypt.org"
DOMAIN                        CAA     0 issuemail ";"
DOMAIN                        CAA     0 iodef "mailto:postmaster@DOMAIN"
```

**Important notes for Gandi DNS records:**
- Use trailing dots on FQDNs in CNAME, MX, and SRV records (e.g., `mail.villaherrgard.com.`)
- LiveDNS activation and DNSSEC are fully automated via API (see Section 12.5)
- TLSA/DANE records are not currently automated for Gandi domains (only Cloudflare has the automation script)

### 8.3 What Makes Mail "Not Flagged as Insecure"

For a domain's email to be considered fully secure and trustworthy by receiving mail servers:

| Check | What it proves | Consequence if missing |
|---|---|---|
| **PTR/rDNS** | Server identity matches IP | Rejected by many servers |
| **SPF** | IP is authorized to send for domain | Fails SPF check, may be marked spam |
| **DKIM** | Message integrity, domain authentication | Fails DKIM check, may be marked spam |
| **DMARC** | Policy for SPF/DKIM failures | No enforcement, less trustworthy |
| **Valid TLS cert** | Encrypted connection | Warnings, downgraded connections |
| **DANE/TLSA** | Certificate pinning in DNS | Missing DANE, slightly less secure |
| **MTA-STS** | Enforced TLS for SMTP | Opportunistic TLS only |
| **DNSSEC** | DNS responses are authenticated | DANE won't validate |
| **Not blacklisted** | IP has good reputation | Mail rejected or spam-filtered |

---

## 9. Certificate Management

### 9.1 Certificate Chain (How It All Connects)

```
NPM certbot renews *.villaherrgard.com
         |
         v
renewal-hooks/deploy/sync-mailcow-certs.sh
         |
    +----+----+
    |         |
    v         v
  Copies    Restarts
  cert to   Mailcow
  Mailcow   containers
  SSL dir   (dovecot, postfix, nginx)
              |
              v (after 5s wait)
  update-tlsa-cloudflare.sh
              |
              v
  Updates TLSA records
  in Cloudflare DNS
  (ports 25, 465, 587)
```

### 9.2 Current Certificates

**npm-2: `*.villaherrgard.com`** (working)
- Renewal config: `/root/nginx/letsencrypt/renewal/npm-2.conf`
- DNS challenge: `dns-cloudflare` via `/root/nginx/letsencrypt/credentials/credentials-2`
- Live cert: `/root/nginx/letsencrypt/live/npm-2/`
- Synced to Mailcow at: `/opt/mailcow-dockerized/data/assets/ssl/cert.pem` and `key.pem`
- Used by: All `*.villaherrgard.com` proxy hosts, Mailcow mail services

**npm-6: `*.keken.nu`, `keken.nu`** (working)
- Renewal config: `/root/nginx/letsencrypt/renewal/npm-6.conf`
- DNS challenge: `dns-gandi` via `/root/nginx/letsencrypt/credentials/credentials-6`
- Issued 2026-02-21, expires 2026-05-22
- Used by: keken.nu and mta-sts.keken.nu proxy hosts

### 9.3 Creating Certificates for New Domains

When adding nysattra.se (or other Gandi-hosted domains):

**Prerequisites:**
1. Gandi API token stored in `/root/.credentials.env` (GANDI_TOKEN variable)
2. NPM will create a numbered credential file (`credentials-N`) when issuing the cert via the UI. The Gandi token sync scripts (`gandi-token-renew.sh`, `update-dns-ip.sh`, `init.sh`) dynamically scan all `credentials-*` files for `dns_gandi_token=` lines and update every match, so new credential files are picked up automatically after token renewal or DR.

**Create certificate via NPM UI:**
1. NPM Admin --> SSL Certificates --> Add SSL Certificate
2. Select "Let's Encrypt"
3. Domain names: `*.nysattra.se`, `nysattra.se`
4. DNS Challenge: Gandi LiveDNS
5. Credentials: Gandi API token
6. Propagation: 120 seconds
7. Save

**Or via certbot CLI inside NPM container:**
```bash
# First create a credential file with the Gandi token
echo "dns_gandi_token=<TOKEN>" > /root/nginx/letsencrypt/credentials/credentials-gandi
chmod 600 /root/nginx/letsencrypt/credentials/credentials-gandi

docker exec nginx-app-1 certbot certonly \
  --authenticator dns-gandi \
  --dns-gandi-credentials /etc/letsencrypt/credentials/credentials-gandi \
  -d "*.nysattra.se" -d "nysattra.se" \
  --key-type ecdsa --elliptic-curve secp384r1 \
  --preferred-chain "ISRG Root X1"
```
**Note:** The NPM UI method is preferred -- it creates a numbered credential file (`credentials-N`) that the token sync scripts will discover automatically.

### 9.4 TLSA/DANE Records

TLSA records are only needed for `villaherrgard.com` (the domain of the MX host `mail.villaherrgard.com`). Other mail domains point their MX to this host, so they rely on the TLSA records of `mail.villaherrgard.com`.

**Automation script:** `/opt/mailcow-dockerized/update-tlsa-cloudflare.sh`
- Extracts certificate fingerprint from `mail.villaherrgard.com:25` via STARTTLS
- Updates TLSA records for ports 25, 465, 587 via Cloudflare API
- Automatically triggered after certificate renewal by the sync hook

**TLSA record format:** `3 1 1 <SHA-256 fingerprint of public key>`
- 3 = DANE-EE (domain-issued certificate)
- 1 = SPKI (subject public key info)
- 1 = SHA-256 hash

### 9.5 What Does NOT Need Certificate Changes

When adding a new mail domain (e.g., nysattra.se):
- The **Mailcow SSL certificate** does NOT change -- it's `*.villaherrgard.com` and covers `mail.villaherrgard.com`
- The **TLSA records** do NOT change -- they're for `_25._tcp.mail.villaherrgard.com`
- The **sync hook** does NOT change -- it syncs npm-2 to Mailcow

What DOES change:
- A **new NPM certificate** (npm-N) is created for `*.nysattra.se` (for web access to the domain)
- New **NPM proxy hosts** are created for the domain and mta-sts subdomain
- The new cert is only used by NPM for HTTPS proxying, NOT by Mailcow's mail services

---

## 10. Backup & Disaster Recovery

### 10.1 Backup Schedule

Current crontab (generated by SchedulingManager, last updated 2026-02-21):

```
# Nighttime window with flock mutex
55 1 * * *  flock -n /tmp/backup-credentials.lock       automated-backup.sh credentials --verify
0 2 * * *   flock -n /tmp/backup-nginx.lock             automated-backup.sh nginx --verify
30 2 * * *  flock -n /tmp/backup-mailcow-directory.lock  automated-backup.sh mailcow-directory --verify
0 3 * * *   flock -n /tmp/backup-mailcow.lock            automated-backup.sh mailcow --verify
0 5 * * *   flock -n /tmp/backup-server-manager.lock     automated-backup.sh server-manager --verify
30 5 * * *  flock -n /tmp/backup-monitoring-stack.lock    automated-backup.sh monitoring-stack --verify

# Gandi token auto-renewal (daily check, renews when <=30 days remaining)
0 12 * * *  flock -n /tmp/gandi-token-renew.lock  gandi-token-renew.sh >> /var/log/gandi-token-renew.log 2>&1
```

Logs at `/opt/server-manager/logs/backup-{service}-cron.log`, rotated weekly (4 retained, compressed) via logrotate at `/etc/logrotate.d/server-manager`.
Gandi token renewal log at `/var/log/gandi-token-renew.log`.

### 10.2 Remote Storage

**Provider:** rsync.net
**Host:** zh5554.rsync.net (SSH alias: `rsync-backup`)
**User:** zh5554
**SSH key:** `/root/.ssh/rsync.key` (Ed25519)
**Borg repos:** `ssh://rsync-backup/./backups/{service}-backup`
**Borg binary:** borg14

### 10.3 Disaster Recovery Workflow

**Script:** `/root/init.sh`

The DR process is fully automated in two phases:

**Phase 1 (interactive, ~2 min):**
1. Prompts for hostname
2. Sets timezone to Europe/Stockholm
3. Installs SSH keys (rsync + GitHub, base64-encoded in script)
4. Tests SSH connections
5. Creates Borg passphrase environment file
6. Installs system packages (dialog, borgbackup, rsync, git, python3, jq)
7. **Asks DR mode:** "Production migration" or "DR test"
8. **Recovers credentials from Borg backup** (CF + Gandi tokens)
9. **Validates tokens** via API endpoints
10. **Prompts for missing/invalid tokens** (production mode) or warns (test mode)
11. Clones server-manager from GitHub
12. Creates Python venv and installs dependencies
13. Configures settings.yaml with hostname
14. Disables IPv6 via GRUB
15. Creates systemd oneshot service for Phase 2
16. **Reboots**

**Phase 2 (automatic via systemd, ~10-13 min):**
1. Verifies IPv6 disabled at kernel level
2. Waits for network
3. Installs Docker
4. Schedules backup cron jobs (night window for DR: 02:00-05:30)
5. Restores services in order:
   - server-manager (~2.5s)
   - nginx (~29s)
   - mailcow-directory (~84s)
   - mailcow (~190s)
   - monitoring-stack (~5-7 min, includes package installation)
6. **IP reconciliation** (if IP changed):
   - Updates all NPM proxy host configs (old IP -> new IP)
   - Restarts NPM
   - **Production mode:** Runs `update-dns-ip.sh` to update DNS A records and SPF
   - **Production mode:** Waits for DNS propagation, then updates TLSA records
   - **Test mode:** Skips DNS changes
7. Displays completion summary with IP change details
8. Self-cleans (removes systemd service and phase marker)

**Total time from fresh VPS to fully operational: ~12-15 minutes**

**Manual step after DR (production mode):** Request PTR/rDNS update from hosting provider (set new IP -> mail.villaherrgard.com). DNS A records and SPF are updated automatically.

### 10.4 Manual DR Commands

If the automated Phase 2 fails or you need to restore selectively:

```bash
# Restore a single service
/opt/server-manager/cli.py restore nginx --yes
/opt/server-manager/cli.py restore mailcow --yes
/opt/server-manager/cli.py restore monitoring-stack --yes

# Restore all services in correct order
/opt/server-manager/cli.py restore-all --yes

# List available backups for a service
/opt/server-manager/cli.py restore nginx --list
```

### 10.5 What Gets Backed Up (and What Doesn't)

**Backed up:**
- API credentials and DNS config (`/root/.credentials.env`, `/root/.dns-config`)
- All NPM configuration, proxy hosts, certificates, database
- All Mailcow data (mail, database, config, certs, DKIM keys)
- Server-manager configuration files
- Grafana data and configuration
- InfluxDB data and configuration
- PressureSuite bridge application

**NOT backed up (reconstructed from source/config):**
- Server-manager code (cloned from GitHub)
- Docker images (pulled on restore)
- System packages (installed by init.sh / restore scripts)
- Cron jobs (re-created by scheduling manager)
- SSH keys and Borg passphrase (embedded in init.sh)

---

## 11. Credential & Secret Inventory

This section lists WHERE credentials are stored, not the values themselves.

| Credential | Location | Purpose |
|---|---|---|
| **Centralized credentials** | `/root/.credentials.env` | **Single source of truth** for CF + Gandi API tokens |
| Cloudflare API token | `/root/.credentials.env` (CF_API_TOKEN) | DNS management, TLSA updates |
| Cloudflare Zone ID | `/root/.credentials.env` (CF_ZONE_ID) | Cloudflare API targeting |
| Gandi API PAT | `/root/.credentials.env` (GANDI_TOKEN) | DNS management, cert renewal |
| DNS domain mapping | `/root/.dns-config` | Domain-to-provider mapping for IP update automation |
| Cloudflare certbot creds | `/root/nginx/letsencrypt/credentials/credentials-2` | DNS challenge for `*.villaherrgard.com` cert (synced from .credentials.env) |
| Gandi certbot creds | `/root/nginx/letsencrypt/credentials/credentials-6` | DNS challenge for `*.keken.nu` cert (synced from .credentials.env). Future Gandi certs will create additional numbered files; all are synced dynamically. |
| Mailcow DB passwords | `/opt/mailcow-dockerized/mailcow.conf` | MariaDB root, user, Redis passwords |
| Mailcow SOGo encryption key | `/opt/mailcow-dockerized/mailcow.conf` | SOGo session encryption |
| NPM MariaDB password | `/root/nginx/docker-compose.yml` | NPM database |
| Borg passphrase | `/root/.env` and hardcoded in `/root/init.sh` | Borg backup encryption |
| rsync.net SSH key | `/root/.ssh/rsync.key` | Backup server authentication |
| GitHub SSH key | `/root/.ssh/github.key` | Server-manager repo access |
| SSH keys (base64) | `/root/init.sh` (embedded) | DR bootstrap |
| InfluxDB API token | `/root/python/pressuresuite-influx-bridge/.env` | InfluxDB write access |
| PressureSuite API creds | `/root/python/pressuresuite-influx-bridge/.env` | PressureSuite Cloud API |

---

## 12. Checklists

### 12.1 Checklist: Adding a New Mail Domain

This is the end-to-end process for adding a new domain (e.g., `nysattra.se`) to the mail server.

**Prerequisites:**
- [ ] Domain registration transferred to Gandi
- [ ] Gandi API token stored and credential file created (see Section 9.3)
- [ ] Gandi LiveDNS + DNSSEC activated via API (see Section 12.5)

**DNS Records at Gandi:**
- [ ] A record: `nysattra.se` --> `194.164.197.33`
- [ ] MX record: `nysattra.se` --> `mail.villaherrgard.com.` (priority 10)
- [ ] SPF TXT: `v=spf1 mx a:mail.villaherrgard.com ip4:194.164.197.33 -all`
- [ ] DMARC TXT: `_dmarc.nysattra.se` --> `v=DMARC1; p=quarantine; adkim=s; aspf=s`
- [ ] Autoconfig CNAME: `autoconfig.nysattra.se` --> `mail.villaherrgard.com.`
- [ ] Autodiscover CNAME: `autodiscover.nysattra.se` --> `mail.villaherrgard.com.`
- [ ] MTA-STS A record: `mta-sts.nysattra.se` --> `194.164.197.33`
- [ ] MTA-STS TXT: `_mta-sts.nysattra.se` --> `v=STSv1; id=YYYYMMDDNNNN;`
- [ ] TLS-RPT TXT: `_smtp._tls.nysattra.se` --> `v=TLSRPTv1; rua=mailto:postmaster@nysattra.se`
- [ ] SRV records (autodiscover, imap, imaps, pop3, pop3s, submission)
- [ ] CAA records (issue, issuewild for letsencrypt.org)

**Mailcow Configuration:**
- [ ] Add domain in Mailcow admin (Configuration --> Mail Setup --> Domains)
- [ ] Generate DKIM key (Configuration --> ARC/DKIM keys)
- [ ] Add DKIM public key to DNS: `dkim._domainkey.nysattra.se` TXT record
- [ ] Enable MTA-STS for domain in Mailcow admin
- [ ] Create mailboxes and aliases as needed

**SSL Certificate:**
- [ ] Create wildcard cert in NPM: `*.nysattra.se`, `nysattra.se` via Gandi DNS challenge
- [ ] Verify certificate issued successfully

**NPM Proxy Hosts:**
- [ ] Create proxy host for `nysattra.se` --> Mailcow (:4433), assign new cert
- [ ] Create proxy host for `mta-sts.nysattra.se` --> Mailcow (:4433), assign new cert

**Verification:**
- [ ] `dig MX nysattra.se` returns `mail.villaherrgard.com`
- [ ] `dig TXT nysattra.se` shows SPF record
- [ ] `dig TXT _dmarc.nysattra.se` shows DMARC record
- [ ] `dig TXT dkim._domainkey.nysattra.se` shows DKIM key
- [ ] `dig +dnssec nysattra.se` shows `ad` flag (DNSSEC validated)
- [ ] `curl https://mta-sts.nysattra.se/.well-known/mta-sts.txt` returns policy
- [ ] Send test email from new domain, check at mail-tester.com (aim for 10/10)
- [ ] Send test email TO new domain, verify delivery
- [ ] Test at https://internet.nl/mail/nysattra.se (expect pass except IPv6)
- [ ] Check blacklists at https://mxtoolbox.com/blacklists.aspx

### 12.2 Checklist: Disaster Recovery on Fresh VPS

- [ ] Deploy fresh Ubuntu 24.04 VPS
- [ ] Copy `init.sh` to the server (or download from known location)
- [ ] Run `bash /root/init.sh`
- [ ] Enter hostname when prompted
- [ ] Select DR mode: "Production migration" (1) or "DR test" (2)
- [ ] Verify/enter API tokens when prompted (Cloudflare required for production)
- [ ] Optionally configure email notifications
- [ ] Wait for Phase 1 to complete and server to reboot (~2 min)
- [ ] Wait for Phase 2 to complete automatically (~10-13 min)
  - Phase 2 automatically: restores all services, updates NPM proxy configs, updates DNS records (production mode)
- [ ] Verify all 20 Docker containers running: `docker ps`
- [ ] Verify 3 systemd services running: `systemctl status grafana-server influxdb pressuresuite-influx-bridge.timer`
- [ ] **Request PTR/rDNS** from hosting provider: set new IP -> `mail.villaherrgard.com`
- [ ] Wait for DNS propagation (check summary output for status)
- [ ] Verify mail flow: send test email to/from the server
- [ ] Verify TLSA records match certificate (auto-updated, or check `/var/log/tlsa-update.log`)
- [ ] Verify webmail access at `https://mail.villaherrgard.com`
- [ ] Verify Grafana at `https://grafana.villaherrgard.com`
- [ ] Verify backup cron jobs: `crontab -l` (should show 6 jobs including credentials)

### 12.3 Checklist: Certificate Renewal Verification

Certificates auto-renew, but to verify the chain works:

- [ ] Check cert expiry: `openssl x509 -in /opt/mailcow-dockerized/data/assets/ssl/cert.pem -noout -dates`
- [ ] Dry-run renewal: `docker exec nginx-app-1 certbot renew --dry-run`
- [ ] If renewal happened, check sync log: `tail -20 /var/log/mailcow-cert-sync.log`
- [ ] Check TLSA update log: `tail -20 /var/log/tlsa-update.log`
- [ ] Verify TLSA matches cert:
  ```bash
  # Get live cert fingerprint
  echo | openssl s_client -connect mail.villaherrgard.com:25 -starttls smtp 2>/dev/null | \
    openssl x509 -noout -pubkey | openssl pkey -pubin -outform DER | \
    openssl dgst -sha256 -binary | xxd -p -c 64
  # Compare with TLSA record
  dig +short TLSA _25._tcp.mail.villaherrgard.com
  ```
- [ ] Online DANE validation: https://dane.sys4.de/ (enter `mail.villaherrgard.com`)

### 12.4 Checklist: Domain Transfer from one.com to Gandi

- [ ] Unlock domain at one.com (disable transfer lock)
- [ ] Get EPP/authorization code from one.com
- [ ] Initiate transfer at Gandi with EPP code
- [ ] Approve transfer via email confirmation (both registrars)
- [ ] Wait for transfer to complete (can take up to 5 days for .se domains)
- [ ] Once at Gandi, proceed with Gandi DNS migration checklist below

### 12.5 Checklist: Gandi DNS Migration (Activate LiveDNS + DNSSEC)

Fully automated via API. Validated on keken.nu (2026-02-21).

**Step 1: Create LiveDNS zone and DNS records (API):**
- [ ] Create all DNS records in Gandi LiveDNS zone via API
  ```bash
  curl -X POST "https://api.gandi.net/v5/livedns/domains/DOMAIN/records" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"rrset_name": "@", "rrset_type": "MX", "rrset_ttl": 3600, "rrset_values": ["10 mail.villaherrgard.com."]}'
  ```

**Step 2: Activate LiveDNS (API):**
- [ ] Set nameservers to Gandi LiveDNS -- this activates the `gandilivedns` service
  ```bash
  curl -X PUT "https://api.gandi.net/v5/domain/domains/DOMAIN/nameservers" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"nameservers": ["ns-64-a.gandi.net", "ns-90-b.gandi.net", "ns-58-c.gandi.net"]}'
  ```
- [ ] Verify: `services` includes `gandilivedns`
- [ ] Verify: DNS records are preserved (not wiped, unlike the admin panel method)

**Step 3: Enable DNSSEC (API):**
- [ ] Create DNSSEC key at LiveDNS level
  ```bash
  curl -X POST "https://api.gandi.net/v5/livedns/domains/DOMAIN/keys" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"flags": 257}'
  ```
- [ ] Query public key from Gandi authoritative nameserver (available immediately)
  ```bash
  PUBKEY=$(dig @ns-64-a.gandi.net DNSKEY DOMAIN +short | grep "^257" | awk '{print $4$5}')
  ```
- [ ] Publish DS record to TLD registry
  ```bash
  curl -X POST "https://api.gandi.net/v5/domain/domains/DOMAIN/dnskeys" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"algorithm\": 13, \"type\": \"ksk\", \"public_key\": \"$PUBKEY\"}"
  ```
- [ ] Verify: `services` includes `dnssec`

**Step 4: Verify:**
- [ ] `dig +dnssec DOMAIN @8.8.8.8 | grep "ad"` -- DNSSEC validates
- [ ] `dig DS DOMAIN +short` -- DS record present in parent zone
- [ ] DNS records intact: `curl ... /v5/livedns/domains/DOMAIN/records | jq 'length'`

### 12.6 Checklist: Quick DNS Verification for Any Domain

```bash
DOMAIN="nysattra.se"

echo "=== MX ===" && dig +short MX $DOMAIN
echo "=== SPF ===" && dig +short TXT $DOMAIN | grep spf
echo "=== DKIM ===" && dig +short TXT dkim._domainkey.$DOMAIN
echo "=== DMARC ===" && dig +short TXT _dmarc.$DOMAIN
echo "=== MTA-STS ===" && dig +short TXT _mta-sts.$DOMAIN
echo "=== TLS-RPT ===" && dig +short TXT _smtp._tls.$DOMAIN
echo "=== DNSSEC ===" && dig +dnssec $DOMAIN @8.8.8.8 | grep -c "ad"
echo "=== Autoconfig ===" && dig +short CNAME autoconfig.$DOMAIN
echo "=== Autodiscover ===" && dig +short CNAME autodiscover.$DOMAIN
echo "=== MTA-STS Policy ===" && curl -s https://mta-sts.$DOMAIN/.well-known/mta-sts.txt
```

---

## 13. Known Issues & Action Items

### P0 -- Critical

**13.1 ~~keken.nu SSL certificate renewal is broken~~ RESOLVED**

A new certificate (npm-6) was issued on 2026-02-21 using the correct `dns-gandi` authenticator. Both keken.nu proxy hosts (15, 16) now use npm-6. The old npm-3 certificate and an orphaned npm-1 DB entry have been cleaned up (DB rows deleted, files removed).

---

**13.2 UFW firewall is inactive (informational)**

UFW is **inactive by design**. Firewall rules are managed at the hosting provider's admin panel (Strato VPS firewall). Docker iptables and Mailcow's netfilter container handle port management for containerized services. Most host-level services (InfluxDB, Grafana, MariaDB, Redis) are bound to localhost.

**Current state:** `ufw status` returns "Status: inactive"

**Note:** This is intentional. The hosting provider's firewall handles external filtering. UFW is not needed and can conflict with Docker's iptables management.

---

### P1 -- High

**13.3 ~~Gandi API token not yet stored or automated~~ RESOLVED**

Gandi API token is now stored in the centralized credentials file at `/root/.credentials.env` along with the Cloudflare token and zone ID. The credentials file is:
- Backed up daily as a dedicated Borg archive (`credentials-backup`)
- Recovered automatically during DR by init.sh Phase 1
- Synced to certbot credential files by `update-dns-ip.sh` and restore process

---

**13.4 ~~Cloudflare API token hardcoded in scripts~~ RESOLVED**

Cloudflare API token and Zone ID are now centralized in `/root/.credentials.env`. The TLSA update script (`update-tlsa-cloudflare.sh`) sources from this file instead of hardcoding values. Certbot credential files are synced from the central file during DR and after credential changes.

---

### P2 -- Medium

**13.5 Borg passphrase in plaintext**

The Borg encryption passphrase appears in plaintext in:
- `/root/.env` (BORG_PASSPHRASE variable)
- `/root/init.sh` (embedded for DR bootstrap)

The init.sh embedding is intentional (needed for DR from scratch), but `/root/.env` should be properly protected.

**Mitigation:** Ensure `/root/.env` is `chmod 600` and `/root/` is not accessible to other users. The init.sh file should also be `chmod 700`.

---

**13.6 No TLSA/DANE automation for Gandi-hosted domains**

The TLSA update script only works with Cloudflare API. Domains hosted on Gandi (keken.nu, and future domains) do not have automated TLSA record management.

However, TLSA records are only needed for the MX host (`mail.villaherrgard.com`), which is on Cloudflare. Mail-only domains (nysattra.se, etc.) that point their MX to `mail.villaherrgard.com` do NOT need their own TLSA records. So this is a non-issue for the current architecture.

**If you ever want per-domain TLSA:** You would need a Gandi-compatible TLSA update script using Gandi's LiveDNS API.

---

### P3 -- Low

**13.7 ~~Email notifications disabled in server-manager~~ RESOLVED**

Notifications are enabled and operational. Configured in `/opt/server-manager/config/notifications.yaml` with `alerts@villaherrgard.com` sending to `micke@nysattra.se` via SMTP/TLS. Backup failures and Gandi token renewal events trigger email alerts. Success notifications are disabled by default (`notify_on_success: false`).

---

## 14. Future Work

### 14.1 Domain Migration Roadmap

| Step | Domain | Action | Dependencies |
|---|---|---|---|
| ~~1~~ | ~~--~~ | ~~Set up Gandi token storage and automation~~ | ~~None~~ DONE |
| ~~2~~ | ~~keken.nu~~ | ~~Fix certificate renewal (switch to dns-gandi)~~ | ~~Step 1~~ DONE (npm-6 issued, npm-3 orphaned) |
| 3 | nysattra.se | Transfer domain from one.com to Gandi | None |
| 4 | nysattra.se | Activate LiveDNS + DNSSEC (2 manual steps) | Step 3 |
| 5 | nysattra.se | Create DNS records via Gandi API | Step 4 |
| 6 | nysattra.se | Add domain to Mailcow + DKIM | Step 5 |
| 7 | nysattra.se | Create wildcard SSL cert in NPM (dns-gandi) | Steps 1, 5 |
| 8 | nysattra.se | Create NPM proxy hosts | Step 7 |
| 9 | nysattra.se | Create mailboxes, migrate email from one.com | Step 6 |
| 10 | nysattra.se | Full verification | Steps 5-9 |
| 11 | villaherrgard.se | Repeat steps 3-10 | Step 10 (confidence) |
| 12 | sono-vagnala.se | Repeat steps 3-10 | Step 10 (confidence) |
| 13 | keken.nu | Retire (remove from Mailcow, NPM, DNS) | DR confidence established |

### 14.2 Estimated Time Per Domain

Based on keken.nu experience:
- Domain transfer: 1-5 days (waiting period)
- API automation (LiveDNS + DNSSEC + DNS records): 30-45 minutes
- Mailcow + SSL + NPM setup: 30 minutes
- Email migration: varies (depends on mailbox count/size)
- Verification: 15-30 minutes

### 14.3 Other Recommended Improvements

1. ~~Enable UFW firewall~~ -- Firewall managed at hosting provider (informational)
2. ~~Implement Gandi token automation~~ -- RESOLVED: Token in `.credentials.env`, backed up daily
3. ~~Move hardcoded credentials to files~~ -- RESOLVED: Centralized in `.credentials.env`
4. ~~**Enable email notifications** for backup success/failure~~ DONE
5. **Complete Phase 8** of server-manager (unit tests, documentation)
6. **Set up monitoring alerts** in Grafana for service health
7. **Consider secondary backup destination** (rsync.net is single point)

---

## Appendix A: Quick Reference Commands

### Service Management

```bash
# Mailcow
cd /opt/mailcow-dockerized && docker compose up -d
cd /opt/mailcow-dockerized && docker compose down
cd /opt/mailcow-dockerized && docker compose restart
cd /opt/mailcow-dockerized && docker compose logs -f --tail=50

# NPM
cd /root/nginx && docker compose up -d
cd /root/nginx && docker compose down
cd /root/nginx && docker compose restart

# Monitoring
systemctl restart grafana-server influxdb
systemctl status grafana-server influxdb pressuresuite-influx-bridge.timer
```

### Certificate Operations

```bash
# Check expiry
openssl x509 -in /opt/mailcow-dockerized/data/assets/ssl/cert.pem -noout -dates

# Get TLSA fingerprint
echo | openssl s_client -connect mail.villaherrgard.com:25 -starttls smtp 2>/dev/null | \
  openssl x509 -noout -pubkey | openssl pkey -pubin -outform DER | \
  openssl dgst -sha256 -binary | xxd -p -c 64

# Manual cert sync + TLSA update
/root/nginx/letsencrypt/renewal-hooks/deploy/sync-mailcow-certs.sh

# Dry-run cert renewal
docker exec nginx-app-1 certbot renew --dry-run
```

### Backup & Restore

```bash
# Manual backup
/opt/server-manager/cli.py backup nginx --verify
/opt/server-manager/cli.py backup mailcow --verify

# List backups
/opt/server-manager/cli.py restore nginx --list

# Restore single service
/opt/server-manager/cli.py restore nginx --yes

# Full DR restore
/opt/server-manager/cli.py restore-all --yes

# Interactive TUI
/opt/server-manager/server_manager.py
```

### DNS Checks

```bash
# Full mail DNS check for any domain
DOMAIN="villaherrgard.com"
dig +short MX $DOMAIN
dig +short TXT $DOMAIN | grep spf
dig +short TXT dkim._domainkey.$DOMAIN
dig +short TXT _dmarc.$DOMAIN
dig +short TLSA _25._tcp.mail.$DOMAIN
dig +dnssec $DOMAIN @8.8.8.8 | grep "ad"
curl -s https://mta-sts.$DOMAIN/.well-known/mta-sts.txt
```

### Testing & Validation

```bash
# Test SMTP ports
echo | openssl s_client -connect mail.villaherrgard.com:25 -starttls smtp
echo | openssl s_client -connect mail.villaherrgard.com:465
echo | openssl s_client -connect mail.villaherrgard.com:587 -starttls smtp

# Check mail queue
docker exec mailcowdockerized-postfix-mailcow-1 postqueue -p

# Check blacklists
host 33.197.164.194.zen.spamhaus.org
```

**Online tools:**
- https://internet.nl/mail/ -- Comprehensive mail security test
- https://www.mail-tester.com/ -- Spam score test
- https://mxtoolbox.com/ -- MX, blacklist, DNS checks
- https://dane.sys4.de/ -- DANE/TLSA validation
- https://aykevl.nl/apps/mta-sts/ -- MTA-STS validation

---

## Appendix B: Documentation Index

All project documentation is consolidated in `/opt/server-manager/docs/`:

| Document | File | Content |
|---|---|---|
| Server Infrastructure Report | `SERVER-INFRASTRUCTURE-REPORT.md` | This document -- master reference for the entire server |
| Mailcow Setup Guide | `SETUP-DOCUMENTATION.md` | Detailed setup instructions, IPv4 config, DNS records, troubleshooting |
| Gandi Migration Report | `GANDI-DNS-MIGRATION-REPORT.md` | Full report on keken.nu migration to Gandi |
| Gandi Quick Reference | `GANDI-MIGRATION-QUICK-REFERENCE.md` | Validated automated workflow (100% API, zero manual steps) |
| Gandi DNSSEC Solution | `GANDI-DNSSEC-API-COMPLETE-SOLUTION.md` | DNSSEC two-level architecture and validated automation |
| Server Manager Status | `PROJECT_STATUS.md` | Development status, phase completion, metrics |
| Server Manager Plan | `SERVER_MANAGER_PROJECT_PLAN.md` | Comprehensive project plan |
| Bootstrap Implementation | `BOOTSTRAP_IMPLEMENTATION.md` | Bootstrap system details |
| Bootstrap Prerequisites | `BOOTSTRAP_PREREQUISITES.md` | Fresh VPS setup prerequisites |

---

**End of Report**

**Last Updated:** 2026-02-21
**Generated from:** Live server inspection and existing documentation synthesis
