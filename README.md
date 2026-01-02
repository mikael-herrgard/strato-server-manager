# Server Manager

Unified TUI application for managing VPS server installations, backups, and disaster recovery.

## Overview

Server Manager provides a unified interface (similar to raspi-config) for managing:
- **Backup Management**: Automated backups of nginx, Mailcow, and application files to remote rsync server
- **Restore Management**: Quick restoration from backups for disaster recovery
- **Installation**: Automated installation of Docker, Mailcow, nginx Proxy Manager, and Portainer
- **System Configuration**: IPv6 management, firewall, network settings
- **Maintenance**: Updates and cleanup operations
- **Monitoring**: Service status, disk usage, backup history

## Installation

### Quick Install (Recommended)

The easiest way to install Server Manager on a fresh VPS:

```bash
curl -fsSL https://raw.githubusercontent.com/mikael-herrgard/strato-server-manager/main/bootstrap/install.sh | bash
```

This automated installer will:
- Install all system dependencies
- Set up Python virtual environment
- Download the latest Server Manager code
- Configure the application
- Create the `server-manager` command

For detailed bootstrap documentation, see: [bootstrap/README.md](bootstrap/README.md)

### Manual Installation

If you prefer manual installation:

#### Prerequisites

- Root access
- Python 3.9 or higher
- Ubuntu/Debian-based system

#### Install System Dependencies

```bash
# Install dialog for TUI
apt-get install -y dialog

# Install Borg Backup
apt-get install -y borgbackup

# Install rsync
apt-get install -y rsync

# Install Docker
apt-get install -y docker.io docker-compose

# Install other tools
apt-get install -y git python3 python3-venv python3-pip
```

#### Install Python Dependencies

```bash
cd /opt/server-manager
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

## Configuration

1. Copy the example configuration:
```bash
cd /opt/server-manager/config
cp settings.yaml.example settings.yaml
```

2. Edit `settings.yaml` with your specific values:
```bash
nano settings.yaml
```

3. Set up the Borg passphrase in `/root/.env`:
```bash
echo "BORG_PASSPHRASE='your-secure-passphrase'" > /root/.env
chmod 600 /root/.env
```

4. Set up SSH key for rsync server:
```bash
ssh-keygen -t ed25519 -f /root/.ssh/backup_key -N ""
ssh-copy-id -i /root/.ssh/backup_key root@rsync-backup
```

## Usage

### Run the Application

```bash
/opt/server-manager/server_manager.py
```

Or create a symlink for easier access:
```bash
ln -s /opt/server-manager/server_manager.py /usr/local/bin/server-manager
server-manager
```

### Navigation

- Use arrow keys to navigate menus
- Press Enter to select
- Press Esc or select "Back" to return to previous menu
- Select "Exit" from main menu to quit

## Features

### Completed Features (Phases 1-6) ✅

**Phase 1: Foundation**
- ✅ Professional TUI interface with pythondialog
- ✅ Configuration management (YAML)
- ✅ Comprehensive logging system
- ✅ System information display
- ✅ Prerequisites checking

**Phase 2: Backup System**
- ✅ Backup nginx with Borg deduplication
- ✅ Backup Mailcow (full/config/mail/db types)
- ✅ Backup application files
- ✅ Backup verification and status
- ✅ Rsync to remote server

**Phase 3: Restore System**
- ✅ Restore nginx from backup
- ✅ Restore Mailcow with type selection
- ✅ Restore application files
- ✅ List and select from available backups
- ✅ Automatic service restart after restore

**Phase 4: Installation & System Configuration**
- ✅ Automated Docker installation
- ✅ Automated Mailcow installation
- ✅ Automated nginx Proxy Manager installation
- ✅ IPv6 disable/enable via GRUB
- ✅ UFW firewall configuration

**Phase 5: Maintenance & Monitoring**
- ✅ Update nginx with rollback capability
- ✅ Update Mailcow via official script
- ✅ System package updates
- ✅ Docker cleanup operations
- ✅ Service status monitoring
- ✅ Container statistics
- ✅ Disk usage tracking

**Phase 6: Scheduling & Automation**
- ✅ Cron job management (no manual editing)
- ✅ Automated backup scheduling
- ✅ Automated cleanup scheduling
- ✅ Email notifications (SMTP)
- ✅ Test notifications
- ✅ Schedule viewing and management

### In Progress

**Phase 7: Disaster Recovery**
- ✅ Bootstrap installation system
- ⏳ Automated recovery mode
- ⏳ Complete DR testing on test VPS
- ⏳ Recovery runbook documentation

**Phase 8: Testing & Documentation**
- ⏳ Unit tests for critical functions
- ⏳ Integration tests
- ⏳ Security audit
- ⏳ Performance testing
- ⏳ Complete user documentation

## Directory Structure

```
/opt/server-manager/
├── server_manager.py          # Main application entry point
├── requirements.txt           # Python dependencies
├── config/
│   ├── settings.yaml         # Configuration (create from .example)
│   └── settings.yaml.example # Configuration template
├── lib/                      # Core application modules
│   ├── __init__.py
│   ├── config.py            # Configuration management
│   ├── ui.py                # TUI interface
│   └── utils.py             # Utility functions
├── logs/
│   └── server-manager.log   # Application logs
└── state/
    └── first_run            # First run marker
```

## Configuration Reference

### Rsync Configuration
```yaml
rsync:
  host: rsync-backup              # Hostname of rsync server
  user: root                       # SSH user
  base_path: /backups              # Remote path for backups
  ssh_key: /root/.ssh/backup_key   # SSH private key
```

### Borg Configuration
```yaml
borg:
  remote_path: borg14              # Borg binary on remote
  compression: zstd,3              # Compression algorithm
  retention:
    daily: 7                       # Keep 7 daily backups
    weekly: 4                      # Keep 4 weekly backups
    monthly: 6                     # Keep 6 monthly backups
```

### Backup Schedule
```yaml
backup:
  schedule:
    nginx: "0 2 * * *"      # 2 AM daily
    mailcow: "0 3 * * *"    # 3 AM daily
    scripts: "0 4 * * 0"    # 4 AM Sunday
```

## Logging

Logs are written to:
- `/opt/server-manager/logs/server-manager.log` (rotated, max 10MB, 5 backups)
- System syslog (warnings and errors only)

View logs from within the application:
- Main Menu → Status & Monitoring → View Logs

## Disaster Recovery

Server Manager provides a complete disaster recovery system for quickly rebuilding your VPS from backups.

### Quick Recovery Process

If your VPS fails and you need to rebuild:

#### 1. Deploy Fresh VPS
- Deploy new Ubuntu 22.04 LTS VPS
- Ensure same or similar specifications as original
- Configure DNS to point to new VPS IP

#### 2. Run Bootstrap Installer
On the fresh VPS, run:
```bash
curl -fsSL https://raw.githubusercontent.com/mikael-herrgard/strato-server-manager/main/bootstrap/install.sh | bash
```

The installer will:
- Install all required system packages
- Set up Python environment
- Download Server Manager
- Prompt to copy configuration from existing backup server

**Important:** When prompted, choose to copy configuration from your backup server. You'll need SSH access to the backup server to retrieve your configuration files.

#### 3. Restore Services
Once installed, launch Server Manager:
```bash
server-manager
```

Then restore your services in order:

**a) Restore nginx:**
- Navigate to: **Restore Management → Restore nginx**
- Select latest backup or specific date
- Wait for restoration to complete

**b) Restore Mailcow:**
- Navigate to: **Restore Management → Restore Mailcow**
- Select backup type (full recommended)
- Select latest backup or specific date
- Wait for restoration to complete

#### 4. Verify Services
- Navigate to: **Status & Monitoring → Service Status**
- Verify all Docker containers are running
- Test nginx: `curl -I http://localhost`
- Test Mailcow: Check webmail interface

#### 5. Update DNS (if needed)
If VPS IP changed:
- Update A/AAAA records for your domains
- Wait for DNS propagation (5-30 minutes)

### Expected Recovery Time

| Task | Estimated Time |
|------|----------------|
| Deploy fresh VPS | 5-10 minutes |
| Run bootstrap installer | 10-15 minutes |
| Restore nginx | 5-10 minutes |
| Restore Mailcow | 15-30 minutes |
| Verify services | 5-10 minutes |
| **Total** | **40-75 minutes** |

### Prerequisites for Recovery

Before disaster strikes, ensure you have:

1. **Regular Backups Running**
   - Configure automated backups: **Scheduling & Automation → Schedule Backup**
   - Verify backups are reaching remote server
   - Test backups periodically

2. **Backup Server Access**
   - SSH access to your backup/rsync server
   - Backup server must remain operational
   - Know the location of your backups

3. **Configuration Backup**
   - Keep a copy of `/opt/server-manager/config/settings.yaml`
   - Keep a copy of `/root/.env` (Borg passphrase)
   - Keep a copy of SSH keys for backup server access

4. **Documentation**
   - Note your domain names
   - Note your DNS provider and login
   - Note your backup server IP/hostname

### Testing Your DR Plan

**Before you need it**, test your disaster recovery:

1. Deploy a test VPS
2. Run the bootstrap installer
3. Restore from your latest backups
4. Verify all services work
5. Document any issues or customizations needed

This ensures your backups are valid and the process works.

### Manual Recovery (Without Bootstrap)

If you cannot use the bootstrap installer:

1. Install system packages manually (see [bootstrap/README.md](bootstrap/README.md))
2. Clone repository: `git clone https://github.com/mikael-herrgard/strato-server-manager.git /opt/server-manager`
3. Create venv: `cd /opt/server-manager && python3 -m venv venv`
4. Install dependencies: `venv/bin/pip install -r requirements.txt`
5. Copy configuration from backup server
6. Create symlink: `ln -s /opt/server-manager/server_manager.py /usr/local/bin/server-manager`
7. Run: `server-manager`

### Backup Server Configuration

Your backup server (rsync/Borg target) should:
- Have sufficient disk space (3-5x your data size)
- Be in a different physical location or provider
- Have regular monitoring
- Have its own backup strategy
- Be accessible via SSH from your VPS

### Troubleshooting Recovery

**Bootstrap fails:**
- Check log file: `/tmp/server-manager-bootstrap-*.log`
- Verify internet connectivity
- Ensure running as root
- Try manual installation instead

**Cannot connect to backup server:**
- Verify SSH key authentication works
- Check firewall rules on backup server
- Verify backup server is online
- Check settings.yaml has correct hostname

**Restore fails:**
- Verify Borg passphrase in `/root/.env` is correct
- Check backup actually exists on remote server
- Verify sufficient disk space on VPS
- Check Server Manager logs: `/opt/server-manager/logs/`

**Services won't start after restore:**
- Check Docker is running: `systemctl status docker`
- Review service logs: **Status & Monitoring → View Logs**
- Verify restored files have correct permissions
- Check for port conflicts: `netstat -tulpn`

### Advanced: Automated Recovery

For fully automated recovery (coming in Phase 7):
```bash
curl -fsSL https://raw.githubusercontent.com/mikael-herrgard/strato-server-manager/main/bootstrap/install.sh | \
  SKIP_CONFIRM=true AUTO_RESTORE=true bash
```

This will perform a complete unattended recovery using your latest backups.

For detailed bootstrap documentation, see: [bootstrap/README.md](bootstrap/README.md)

## Troubleshooting

### Dialog not found
```bash
apt-get install -y dialog
```

### Python module not found
```bash
cd /opt/server-manager
pip3 install -r requirements.txt
```

### Permission denied
Ensure you're running as root:
```bash
sudo /opt/server-manager/server_manager.py
```

### SSH connection to rsync server fails
Test SSH connection:
```bash
ssh -i /root/.ssh/backup_key root@rsync-backup
```

## Development

### Project Phases

1. **Phase 1**: Foundation ✅ COMPLETE
2. **Phase 2**: Backup System ✅ COMPLETE
3. **Phase 3**: Restore System ✅ COMPLETE
4. **Phase 4**: Installation & System Config ✅ COMPLETE
5. **Phase 5**: Maintenance & Monitoring ✅ COMPLETE
6. **Phase 6**: Scheduling & Automation ✅ COMPLETE
7. **Phase 7**: Disaster Recovery ⏳ IN PROGRESS (Bootstrap system complete)
8. **Phase 8**: Testing & Documentation ⏳ PENDING

See `PROJECT_STATUS.md` for detailed project status and remaining work.

## License

Internal use only.

## Author

Server Administrator
