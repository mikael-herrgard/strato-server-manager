# Server Manager

Unified TUI + CLI application for managing a VPS running Mailcow, Nginx Proxy Manager, and a Grafana/InfluxDB monitoring stack — with automated Borg backups to a remote repository and one-script disaster recovery.

## Overview

Server Manager provides two entry points:

- **`server_manager.py`** — interactive TUI (raspi-config style) for day-to-day management
- **`cli.py`** — non-interactive CLI used by cron and disaster recovery

Capabilities:

- **Backup**: Automated nightly Borg backups of 6 services to a remote repository over SSH
- **Restore**: Per-service or full-server restore, safe extract-then-swap ordering with pre-restore safety copies
- **Integrity**: Monthly `borg check` of all repositories with email alerts on failure
- **Installation**: Automated installation of Docker, Mailcow, and Nginx Proxy Manager
- **Scheduling**: Managed crontab (queue-based night window, preserves foreign cron entries)
- **Maintenance**: Updates with rollback, cleanup of aged backup artifacts
- **Monitoring**: Service status, disk usage, backup history, email notifications
- **Login status screen**: Compact health summary as motd on SSH login (also via the `status` command)

## The 6 Backup Services

| Service | Contents |
|---------|----------|
| `credentials` | `/root/.credentials.env`, `/root/.dns-config` (API tokens, DNS config) |
| `nginx` | `/root/nginx` — NPM data, certificates, proxy host database |
| `mailcow` | Full mail data via mailcow's official backup script: **vmail (all emails)**, crypt keys, Redis, Rspamd, Postfix queue, `mailcow.conf`, **plus a MySQL dump** (`backup_mysql.gz`) created by Server Manager |
| `mailcow-directory` | `/opt/mailcow-dockerized` installation dir (compose files, config overrides) — no mail data |
| `server-manager` | This application's config (`settings.yaml`, `notifications.yaml`) |
| `monitoring-stack` | Grafana + InfluxDB data/config (services stopped during backup for consistency) |

> **Why the extra MySQL dump?** Mailcow's official backup script runs its DB backup in a `docker run` with `--sysctl net.ipv6.conf.all.disable_ipv6=1`, which fails silently on hosts with IPv6 disabled at kernel level (as this server has). Server Manager therefore dumps the database itself via `docker exec` + `mysqldump` into the backup directory as `backup_mysql.gz` — the exact filename mailcow's official **restore** script consumes natively. The backup fails loudly if the dump fails.

## CLI Usage

```bash
cd /opt/server-manager

# Backups (what cron runs nightly)
venv/bin/python3 cli.py backup <service> --verify

# List available archives for a service
venv/bin/python3 cli.py restore <service> --list

# Restore one service (interactive confirmation unless --yes)
venv/bin/python3 cli.py restore <service> [--archive NAME] [--yes]

# Full disaster recovery — all services in dependency order
venv/bin/python3 cli.py restore-all --yes

# Borg repository integrity check (what cron runs monthly)
venv/bin/python3 cli.py check [service|all] [--timeout SECONDS]

# Clean up aged pre-update/pre-restore/rollback artifacts
venv/bin/python3 cli.py cleanup [--retention-days N]
```

`<service>` is one of: `nginx`, `mailcow`, `mailcow-directory`, `server-manager`, `monitoring-stack`, `credentials`.

Failure notifications include the real error (`last_error`) plus a tail of the application log — never just "operation returned false". A broken `settings.yaml` raises `ConfigError` and exits with code 2 instead of silently using defaults.

## Scheduling

All cron entries are managed by `lib/scheduling.py` (TUI: Scheduling & Automation). The crontab writer:

- Backs up the previous crontab to `schedules/crontab.backup.<timestamp>` (last 5 kept)
- **Preserves** unrecognized lines (`@reboot`, env vars, comments, foreign jobs) instead of dropping them
- Validates cron schedule expressions before writing

Standard schedule:

| Job | Schedule |
|-----|----------|
| Backup queue (6 services, spaced) | Nightly window 01:55–05:30 |
| Backup cleanup | Weekly |
| Borg integrity check (all repos) | `0 6 1 * *` (1st of month, 06:00) |
| Gandi token renewal check | Daily 12:00 |
| Certificate sync + TLSA update | Daily 04:00 |
| Weekly summary email | Sunday 08:00 |

All jobs run under `flock` to prevent overlap. A full `check all` takes ~18 minutes for 6 repositories.

## Installation

### Quick Install

```bash
curl -fsSL https://raw.githubusercontent.com/mikael-herrgard/strato-server-manager/main/bootstrap/install.sh | bash
```

### Manual Installation

```bash
apt-get install -y dialog borgbackup rsync git python3 python3-venv python3-pip
git clone https://github.com/mikael-herrgard/strato-server-manager.git /opt/server-manager
cd /opt/server-manager
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

## Configuration

1. Copy and edit the config templates:
   ```bash
   cd /opt/server-manager/config
   cp settings.yaml.example settings.yaml
   ```

2. Borg passphrase in `/root/.env`:
   ```bash
   echo "BORG_PASSPHRASE='your-secure-passphrase'" > /root/.env
   chmod 600 /root/.env
   ```

3. SSH access to the backup host. The backup host is addressed via the `rsync-backup` alias in `/root/.ssh/config`, using a dedicated key (`/root/.ssh/rsync.key`). **Important on IPv6-disabled hosts:** force IPv4, or SSH will hang on the backup provider's AAAA record:
   ```
   Host rsync-backup
       HostName <backup-host>
       User <backup-user>
       IdentityFile /root/.ssh/rsync.key
       AddressFamily inet
   ```

Key settings live in `config/settings.yaml` (paths, Borg retention/compression, remote path) — see `settings.yaml.example`.

## Directory Structure

```
/opt/server-manager/
├── server_manager.py          # TUI entry point
├── cli.py                     # CLI entry point (cron / DR)
├── config/
│   ├── settings.yaml          # Main config (create from .example)
│   └── notifications.yaml     # Email notification config
├── lib/
│   ├── borg.py                # BorgRepoBase — shared Borg plumbing (repos, create/verify/prune/list/check)
│   ├── backup.py              # BackupManager (per-service backup flows)
│   ├── restore.py             # RestoreManager (safe extract-then-swap restores)
│   ├── scheduling.py          # Crontab management (safe rewrite, validation)
│   ├── maintenance.py         # Updates, cleanup
│   ├── monitoring.py          # Status and stats
│   ├── notifications.py       # Email (SMTP via local relay)
│   ├── installation.py        # Docker/Mailcow/NPM installers
│   ├── config.py              # ConfigManager + ConfigError
│   ├── ui.py / utils.py       # TUI plumbing, shared helpers
│   └── handlers/              # TUI menu handlers (spec-driven dispatch)
├── scripts/                   # Cron wrappers + operational scripts
│   ├── automated-backup.sh    # Cron entry for nightly backups
│   ├── borg-check.sh          # Cron entry for monthly integrity check
│   ├── cleanup-backups.sh     # Cron entry for cleanup
│   ├── sync-mailcow-certs.sh  # Cert sync + daily TLSA verification/rotation
│   ├── weekly-summary.sh      # Sunday status email
│   ├── motd-status.sh         # Login status screen (motd + `status` alias)
│   └── ...
├── bootstrap/                 # Fresh-VPS installer
├── docs/                      # Project documentation
├── logs/                      # server-manager.log (rotated)
├── schedules/                 # Crontab backups (not in git)
└── state/                     # Runtime state (not in git)
```

## Disaster Recovery

Full DR is a **two-phase `init.sh`** flow (kept **offline**, not in this repository — it embeds secrets):

1. **Phase 1 (interactive)**: hostname, SSH keys, packages, Server Manager install, credential recovery from Borg, IPv6 disable → reboot
2. **Phase 2 (automatic, systemd oneshot)**: Docker install, backup cron scheduling (including the monthly borg check), `cli.py restore-all --yes`, IP reconciliation (NPM configs, DNS A/SPF/TLSA updates)

Measured on a fresh Ubuntu 24.04 VPS: **~12–15 minutes** from bare VPS to all containers and services running. The only manual post-DR step is requesting PTR/rDNS from the hosting provider.

Without `init.sh`, the same result can be achieved manually: install via bootstrap, restore credentials, then `cli.py restore-all --yes`. Restore order (handled automatically by `restore-all`): server-manager → nginx → mailcow-directory → mailcow → monitoring-stack.

### Restore safety

- Archives are **extracted and verified first**; the live installation is only touched afterwards
- A pre-restore safety copy is taken; if it fails, the restore **aborts** with services restarted
- Mailcow restore uses mailcow's official restore script, including native `backup_mysql.gz` DB restore

### Prerequisites for recovery (keep these OFF-server)

- `init.sh` (refresh your offline copy whenever it changes!)
- Borg passphrase
- SSH key for the backup host

## Notifications

- Per-backup success/failure emails (failures include real error + log tail)
- Monthly borg check failure alerts with per-repository errors
- Weekly HTML summary email (system health, security, mail, backups, TLS, Docker); failed checks render as red rows and escalate the subject line (`- WARN` / `- ALERT`) instead of suppressing the email
- Primary delivery is authenticated SMTP submission; if that fails, sending **falls back to local msmtp** (direct to the Postfix container — no DNS/proxy/TLS/auth dependency). If both paths fail, the message is **spooled to `state/failed-notifications/`** so it is never silently lost; the login status screen and weekly summary surface a non-empty spool.
- A corrupt `notifications.yaml` or `settings.yaml` triggers an alert instead of silently disabling alerting

## Login Status Screen

`scripts/motd-status.sh` renders a compact health summary on every SSH login
(via a `/etc/update-motd.d/50-server-manager` symlink) and on demand with the
`status` alias:

```
 Server status as of Sun Jul  5 10:49:38 CEST 2026

  System load:   0.09 0.04 0.05     Docker:      21/21 running
  Usage of /:    43% of 232G        Backups:     all 6 OK (oldest 8h)
  Memory usage:  52% used           Borg check:  OK Jul 01
  Swap usage:    0% used            TLS cert:    34 days left
  Uptime:        3d, 3h, 21 min     Mail queue:  0 messages
  Processes:     364                fail2ban:    1 banned
```

Values are color-coded (green/yellow/red, same thresholds as the alert
emails). Problems summarize in-grid (`Backups: 2 problem(s)!`) and expand
into detail lines below it — including undelivered notifications, a pending
reboot flag, failed systemd units, and container restart counts.

Design rules: local checks only (no network probes), every command
timeboxed so a hung Docker daemon cannot hang the login, always exits 0.
Paths are env-overridable (`MOTD_*`) for testing; respects `NO_COLOR`.
Install (done by `init.sh` during DR): symlink into `/etc/update-motd.d/`,
`status` alias in `.bashrc`, and `chmod a-x` on Ubuntu's `10-help-text`,
`50-motd-news`, and `50-landscape-sysinfo` to reduce noise.

## Troubleshooting

**SSH to backup host fails or hangs**
```bash
ssh -vvv rsync-backup echo ok
```
- If it hangs: check `AddressFamily inet` is set (IPv6-disabled hosts)
- The backup provider can be transiently flaky (slow handshakes, connection resets); the SSH pre-check retries once with generous timeouts. Treat isolated failures as transient before debugging locally.

**Backup failed email** — the email now contains the actual error and log tail. Re-run manually:
```bash
flock -n /tmp/backup-<service>.lock /opt/server-manager/scripts/automated-backup.sh <service> --verify
```

**Listing backups fails vs. empty repo** — `cli.py restore <service> --list` distinguishes "Listing failed: <error>" from "No backups found."

**Restore fails**
- Verify Borg passphrase in `/root/.env`
- Check `/opt/server-manager/logs/server-manager.log`
- Verify sufficient disk space (staging happens under `/var/backups/local`)

**Broken settings.yaml** — the CLI exits with code 2 and a `Configuration error:` message rather than running with defaults (and sends an alert, since a broken config would otherwise kill every cron job silently).

**"LOST ALERTS" on the login screen** — one or more notifications failed both delivery paths and were spooled. Read them with `cat /opt/server-manager/state/failed-notifications/*.eml`, fix the mail path (is Postfix up? `docker ps | grep postfix`), then delete the spooled files.

## Development

Single-developer project; work is committed directly to `main`. See `docs/PROJECT_STATUS.md` for detailed status and history.

## License

Internal use only.
