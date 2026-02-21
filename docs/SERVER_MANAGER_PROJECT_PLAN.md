# Server Manager - Comprehensive Project Plan

**Version:** 1.0
**Date:** 2025-12-31
**Status:** Planning Phase

## Executive Summary

This document outlines the complete plan for building a unified, TUI-based server management application in Python. The application will replace the current collection of bash scripts with a cohesive system for managing VPS server installations, backups, and disaster recovery - specifically focused on Nginx Proxy Manager and Mailcow email server.

### Primary Goals

1. **Unified Management Interface**: Single TUI application (raspi-config style) for all server management tasks
2. **Automated Backups**: Integrated backup system using Borg + rsync for both Nginx and Mailcow
3. **Disaster Recovery**: Complete VPS rebuild capability with automated restoration from backups
4. **System Configuration**: Managed system configuration (IPv6 disabling, firewall, etc.)
5. **Self-Contained**: Application itself can be backed up and restored for bootstrapping new installations

## Technology Stack

### Core Technologies

- **Language**: Python 3.9+ (available on most modern Linux distributions)
- **TUI Framework**: `pythondialog` (Python wrapper for dialog/whiptail)
- **Configuration**: YAML files + environment variables
- **Secrets Management**: `age` encryption for sensitive data
- **Backup System**: Borg Backup + rsync over SSH
- **Logging**: Python `logging` module with file and syslog handlers
- **Process Management**: `subprocess` for system commands, `docker` Python SDK for Docker operations

### Python Dependencies

```
pythondialog>=3.5.3
PyYAML>=6.0
paramiko>=3.0.0
docker>=6.0.0
python-crontab>=2.7.0
cryptography>=41.0.0
```

### System Dependencies

- `dialog` (for TUI)
- `borg` (backup system)
- `rsync` (remote sync)
- `docker` and `docker-compose`
- SSH client with key-based authentication

## Application Architecture

### Directory Structure

```
/opt/server-manager/                    # Main application directory
├── server_manager.py                   # Main entry point
├── requirements.txt                    # Python dependencies
├── config/
│   ├── settings.yaml                   # Application configuration
│   ├── credentials.age                 # Encrypted secrets (borg passphrase, etc.)
│   └── templates/                      # Configuration templates
│       ├── mailcow.conf.j2
│       └── grub.j2
├── lib/                                # Core application modules
│   ├── __init__.py
│   ├── ui.py                          # TUI interface management
│   ├── config.py                      # Configuration handling
│   ├── backup.py                      # Backup operations
│   ├── restore.py                     # Restore operations
│   ├── install.py                     # Installation automation
│   ├── system.py                      # System configuration
│   ├── maintenance.py                 # Update and maintenance
│   ├── monitoring.py                  # Status and monitoring
│   ├── scheduler.py                   # Cron job management
│   └── utils.py                       # Shared utilities
├── logs/
│   └── server-manager.log             # Application logs
├── state/
│   └── state.json                     # Application state tracking
└── README.md                          # User documentation

/var/backups/local/                     # Local staging for backups
├── nginx/
├── mailcow/
└── server-manager/
```

### Module Breakdown

#### 1. `ui.py` - User Interface Module

**Responsibilities:**
- Display main menu and submenus using dialog
- Handle user input and navigation
- Show progress bars for long-running operations
- Display informational messages, warnings, and errors
- Confirmation dialogs for destructive operations

**Key Functions:**
```python
def show_main_menu() -> str
def show_backup_menu() -> str
def show_restore_menu() -> str
def show_installation_menu() -> str
def show_system_menu() -> str
def confirm_action(message: str) -> bool
def show_progress(title: str, text: str, percent: int)
def show_message(title: str, text: str, msg_type: str)
def select_backup(backups: list) -> str
```

#### 2. `config.py` - Configuration Management

**Responsibilities:**
- Load and parse YAML configuration
- Decrypt and access secrets
- Validate configuration values
- Provide configuration to other modules
- Update configuration programmatically

**Key Functions:**
```python
def load_config() -> dict
def get_secret(key: str) -> str
def set_secret(key: str, value: str)
def validate_config() -> bool
def get_borg_config() -> dict
def get_rsync_config() -> dict
```

**Configuration Schema:**
```yaml
# settings.yaml
rsync:
  host: "rsync-backup"
  user: "backup"
  base_path: "/backups"
  ssh_key: "/root/.ssh/backup_key"

borg:
  remote_path: "borg14"
  compression: "zstd,3"
  retention:
    daily: 7
    weekly: 4
    monthly: 6

mailcow:
  install_path: "/opt/mailcow-dockerized"
  backup_types: ["all"]  # all, config, mail, db
  domain: "mail.example.com"

nginx:
  install_path: "/root/nginx"
  domain: "nginx.example.com"

system:
  ipv6_enabled: false
  auto_updates: true
  notification_email: "admin@example.com"

backup:
  local_staging: "/var/backups/local"
  schedule:
    nginx: "0 2 * * *"      # 2 AM daily
    mailcow: "0 3 * * *"    # 3 AM daily
    scripts: "0 4 * * 0"    # 4 AM weekly
```

#### 3. `backup.py` - Backup Operations

**Responsibilities:**
- Create Borg backups of nginx, Mailcow, and application
- Stage backups locally then sync to rsync server
- Verify backup integrity
- Prune old backups based on retention policy
- Generate backup reports

**Key Functions:**
```python
def backup_nginx(verify: bool = True) -> bool
def backup_mailcow(backup_type: str = "all", verify: bool = True) -> bool
def backup_application() -> bool
def verify_backup(repo: str, archive_name: str) -> bool
def prune_old_backups(repo: str) -> bool
def list_backups(repo: str) -> list
def get_backup_info(repo: str, archive_name: str) -> dict
```

**Backup Workflow:**
```
1. Pre-backup checks (disk space, SSH connectivity)
2. Stop services if needed (optional for Mailcow)
3. Create Borg backup to local staging
4. Verify backup integrity (borg verify)
5. Rsync to remote server
6. Verify remote copy
7. Restart services
8. Prune old backups (both local and remote)
9. Log results and send notification
```

#### 4. `restore.py` - Restore Operations

**Responsibilities:**
- List available backups from rsync server
- Download backups from remote to local staging
- Extract and verify backups
- Restore to target locations
- Handle pre-restore backups of existing installations
- Restart services after restoration

**Key Functions:**
```python
def list_remote_backups(service: str) -> list
def restore_nginx(backup_name: str = "latest") -> bool
def restore_mailcow(backup_name: str = "latest") -> bool
def restore_application(backup_name: str = "latest") -> bool
def download_backup(service: str, backup_name: str) -> str
def extract_backup(backup_path: str, target: str) -> bool
```

**Restore Workflow:**
```
1. List available backups from rsync server
2. User selects backup (or use latest)
3. Download backup to local staging
4. Verify backup integrity
5. Backup existing installation (if exists)
6. Stop services
7. Extract backup to target location
8. Restore configuration files
9. Set proper permissions
10. Start services
11. Verify services are running
12. Run post-restore checks
13. Log results
```

#### 5. `install.py` - Installation Module

**Responsibilities:**
- Fresh installation of Docker
- Fresh installation of Mailcow
- Fresh installation of Nginx Proxy Manager
- Installation of Portainer
- Installation of server-manager application itself
- Dependency checking and installation

**Key Functions:**
```python
def install_docker() -> bool
def install_mailcow(domain: str, restore_from_backup: bool = False) -> bool
def install_nginx_proxy_manager() -> bool
def install_portainer() -> bool
def install_dependencies() -> bool
def check_prerequisites() -> dict
```

**Mailcow Installation Workflow:**
```
1. Check prerequisites (RAM, disk, ports available)
2. Install Docker if not present
3. Clone Mailcow repository
4. Run Mailcow generate_config.sh
5. Configure mailcow.conf from template
6. Pull Docker images
7. Start Mailcow containers
8. Wait for services to be ready
9. Optional: Restore from backup
10. Display access information
11. Remind about DNS configuration
```

#### 6. `system.py` - System Configuration

**Responsibilities:**
- Disable/enable IPv6 via GRUB configuration
- Configure firewall (ufw)
- Manage SSH configuration
- System updates
- Hostname configuration
- Network settings

**Key Functions:**
```python
def disable_ipv6() -> bool
def enable_ipv6() -> bool
def configure_firewall(ports: list) -> bool
def update_system() -> bool
def set_hostname(hostname: str) -> bool
def get_system_info() -> dict
```

**IPv6 Disable Workflow:**
```
1. Check current IPv6 status
2. If already disabled, inform and exit
3. Backup /etc/default/grub
4. Modify GRUB_CMDLINE_LINUX parameter
5. Validate GRUB configuration syntax
6. Run update-grub
7. Check for errors
8. Inform user about required reboot
9. Optional: Schedule reboot or reboot immediately with confirmation
```

#### 7. `maintenance.py` - Maintenance Operations

**Responsibilities:**
- Update Nginx Proxy Manager
- Update Mailcow (via official update script)
- System package updates
- Cleanup old Docker images
- Disk space management
- Log rotation

**Key Functions:**
```python
def update_nginx() -> bool
def update_mailcow() -> bool
def update_system_packages() -> bool
def cleanup_docker() -> bool
def cleanup_old_backups() -> bool
def rotate_logs() -> bool
```

#### 8. `monitoring.py` - Status and Monitoring

**Responsibilities:**
- Check service status (Docker containers)
- Monitor disk usage
- View backup history
- System resource monitoring
- Log viewing and filtering
- Generate status reports

**Key Functions:**
```python
def get_service_status() -> dict
def get_disk_usage() -> dict
def get_backup_history() -> list
def get_container_stats() -> dict
def view_logs(service: str, lines: int = 100) -> str
def generate_status_report() -> str
```

#### 9. `scheduler.py` - Scheduled Tasks

**Responsibilities:**
- Manage cron jobs for automated backups
- Schedule system updates
- Schedule cleanup tasks
- View scheduled tasks
- Enable/disable schedules

**Key Functions:**
```python
def setup_backup_schedules() -> bool
def remove_backup_schedules() -> bool
def list_scheduled_tasks() -> list
def enable_schedule(task: str) -> bool
def disable_schedule(task: str) -> bool
```

#### 10. `utils.py` - Utility Functions

**Responsibilities:**
- Logging helpers
- Command execution wrappers
- SSH connection management
- File operations (copy, move, delete with safety checks)
- Disk space checking
- Network connectivity tests

**Key Functions:**
```python
def run_command(cmd: list, check: bool = True) -> tuple
def ssh_execute(host: str, command: str) -> tuple
def check_disk_space(path: str, required_gb: int) -> bool
def test_ssh_connection(host: str) -> bool
def safe_delete(path: str, backup: bool = True) -> bool
def send_notification(subject: str, message: str) -> bool
```

## Security Considerations

### 1. Credential Management

**Current State:**
- `.env` file with plaintext BORG_PASSPHRASE

**Improved State:**
```python
# Use age encryption for secrets
# /opt/server-manager/config/credentials.age (encrypted)
# Only decrypt when needed, never store in memory longer than necessary

# Generate age key (one-time setup)
age-keygen -o /root/.age/key.txt
chmod 600 /root/.age/key.txt

# Encrypt credentials
age -r $(age-keygen -y /root/.age/key.txt) -o config/credentials.age

# In code:
def get_borg_passphrase():
    """Decrypt and return passphrase, use context manager"""
    with open('/root/.age/key.txt') as f:
        age_key = f.read()
    decrypted = decrypt_with_age(age_key, 'config/credentials.age')
    return decrypted['borg_passphrase']
```

### 2. SSH Key Security

**Best Practices:**
- Dedicated SSH key for backups: `/root/.ssh/backup_key`
- Restrict key on remote server:
  ```
  # In rsync server's ~/.ssh/authorized_keys
  command="borg serve --restrict-to-path /backups",restrict ssh-ed25519 AAAA...
  ```
- Use SSH key passphrase + ssh-agent for interactive use
- For automated tasks, use restricted key without passphrase (acceptable for this use case)

### 3. Input Validation

**Critical Areas:**
- Validate all user input before passing to shell commands
- Use parameterized commands, avoid string concatenation
- Sanitize file paths to prevent directory traversal
- Validate backup names match expected patterns

```python
import re

def validate_backup_name(name: str) -> bool:
    """Ensure backup name is safe"""
    pattern = r'^[a-zA-Z0-9_-]+$'
    return bool(re.match(pattern, name))

def safe_command_exec(cmd: list):
    """Use list form to prevent shell injection"""
    subprocess.run(cmd, check=True)  # Good
    # subprocess.run(f"command {user_input}", shell=True)  # BAD!
```

### 4. Privilege Management

- Application runs as root (required for Docker, system config)
- Drop privileges where possible for non-privileged operations
- Use sudo for specific commands rather than running everything as root
- Log all privileged operations

### 5. Backup Verification

**Critical:** Always verify backups before relying on them

```python
def verify_backup_integrity(repo: str, archive: str) -> bool:
    """Verify backup can be read and extracted"""
    try:
        # Check archive exists and is readable
        subprocess.run(['borg', 'list', f'{repo}::{archive}'],
                      check=True, capture_output=True)

        # Extract single file to test
        subprocess.run(['borg', 'extract', '--dry-run', f'{repo}::{archive}'],
                      check=True, capture_output=True)

        return True
    except subprocess.CalledProcessError:
        return False
```

### 6. Audit Logging

- Log all operations with timestamps
- Include user (if multi-user in future), operation, result
- Tamper-evident logs (append-only, optionally remote syslog)

```python
import logging
import logging.handlers

def setup_logging():
    logger = logging.getLogger('server_manager')
    logger.setLevel(logging.INFO)

    # File handler
    fh = logging.handlers.RotatingFileHandler(
        '/opt/server-manager/logs/server-manager.log',
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )

    # Syslog handler
    sh = logging.handlers.SysLogHandler(address='/dev/log')

    # Format
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    fh.setFormatter(formatter)
    sh.setFormatter(formatter)

    logger.addHandler(fh)
    logger.addHandler(sh)

    return logger
```

## Disaster Recovery Workflow

### Scenario: Complete VPS Rebuild

This is the primary use case for the application.

**Prerequisites:**
- Remote rsync server accessible
- SSH key for rsync server available
- DNS records documented
- Domain names documented

**Step-by-Step Recovery:**

```
1. FRESH VPS INSTALL
   - Deploy fresh Ubuntu/Debian VPS
   - Login as root
   - Update system: apt update && apt upgrade -y

2. BOOTSTRAP PREREQUISITES
   - Install git, python3, python3-pip, dialog
   - Install SSH key for rsync access
   - Test rsync server connectivity

3. INSTALL SERVER-MANAGER
   Option A: From backup
   - Download server-manager backup from rsync
   - Extract to /opt/server-manager
   - Install Python dependencies

   Option B: From git (if available)
   - Clone server-manager repository
   - Install dependencies
   - Configure from scratch

4. CONFIGURE SYSTEM
   - Run server-manager
   - Navigate: System Configuration > Disable IPv6
   - Confirm reboot
   - Wait for reboot and reconnect

5. INSTALL DOCKER
   - Run server-manager
   - Navigate: Installation > Install Docker
   - Verify Docker installation

6. RESTORE NGINX PROXY MANAGER
   - Navigate: Restore Management > Restore Nginx
   - Select latest backup (or specific date)
   - Wait for download and extraction
   - Verify nginx containers running
   - Test admin interface access

7. RESTORE MAILCOW
   - Navigate: Restore Management > Restore Mailcow
   - This will:
     a. Download Mailcow backup from rsync
     b. Install Mailcow (fresh)
     c. Restore configuration
     d. Restore mail data
     e. Restore databases
     f. Start containers
   - Wait for restoration (may take 30-60 minutes)
   - Verify Mailcow containers running

8. POST-RESTORE VERIFICATION
   - Verify DNS records still point to new VPS IP
   - Test email sending (SMTP)
   - Test email receiving (IMAP)
   - Verify webmail access
   - Check DKIM, SPF, DMARC records
   - Test nginx proxy manager proxies

9. RECONFIGURE BACKUPS
   - Navigate: Backup Management > Configure Backup Schedule
   - Enable automated backups
   - Test manual backup to ensure working

10. FINALIZE
    - Document new VPS IP address
    - Update any external monitoring
    - Send test emails to verify full functionality
    - Mark recovery as complete in documentation
```

**Estimated Timeline:**
- Steps 1-3: 15 minutes
- Step 4: 5 minutes + reboot
- Step 5: 5 minutes
- Step 6: 10 minutes
- Step 7: 45-90 minutes (depends on backup size)
- Step 8: 15 minutes
- Steps 9-10: 10 minutes

**Total: ~2-2.5 hours**

### Automated Recovery Script

For future enhancement, create a single-command recovery:

```bash
#!/bin/bash
# /root/disaster-recovery.sh
# Run this on fresh VPS to fully restore everything

set -e

echo "=== VPS Disaster Recovery Script ==="
echo "This will restore your complete server from backups"
read -p "Continue? (yes/no): " confirm
[[ "$confirm" != "yes" ]] && exit 1

# Install prerequisites
apt update && apt install -y git python3 python3-pip dialog age

# Restore SSH key (from secure location or manual paste)
echo "Please provide the rsync backup SSH key"
read -p "Path to SSH key file: " ssh_key_path
mkdir -p /root/.ssh
cp "$ssh_key_path" /root/.ssh/backup_key
chmod 600 /root/.ssh/backup_key

# Download and install server-manager
cd /tmp
rsync -avz -e "ssh -i /root/.ssh/backup_key" \
  rsync-backup:./server-manager-backup/latest/ /opt/server-manager/
cd /opt/server-manager
pip3 install -r requirements.txt

# Run automated recovery
python3 server_manager.py --auto-recover

echo "=== Recovery Complete ==="
echo "Please verify all services and update DNS if needed"
```

## Implementation Phases

### Phase 1: Foundation (Week 1)
**Goal:** Basic TUI and configuration framework

**Tasks:**
- [ ] Set up Python project structure
- [ ] Implement `config.py` with YAML parsing
- [ ] Implement `ui.py` with basic menu system
- [ ] Implement `utils.py` with logging and command execution
- [ ] Create basic settings.yaml template
- [ ] Test menu navigation and configuration loading

**Deliverable:** Working TUI that can display menus and load configuration

### Phase 2: Backup System (Week 2)
**Goal:** Complete backup functionality for all services

**Tasks:**
- [ ] Implement `backup.py` module
- [ ] Port nginx backup logic from bash to Python
- [ ] Implement Mailcow backup integration
- [ ] Add application self-backup
- [ ] Implement backup verification
- [ ] Add backup to rsync sync functionality
- [ ] Implement pruning based on retention policy
- [ ] Add backup menu to TUI

**Deliverable:** Full backup capability via TUI

**Testing Checklist:**
- [ ] Backup nginx successfully
- [ ] Backup Mailcow successfully
- [ ] Verify backups are on rsync server
- [ ] Verify old backups are pruned
- [ ] Test backup with insufficient disk space (should fail gracefully)
- [ ] Test backup with rsync server unavailable (should fail gracefully)

### Phase 3: Restore System (Week 3)
**Goal:** Complete restore functionality

**Tasks:**
- [ ] Implement `restore.py` module
- [ ] Implement nginx restore from backup
- [ ] Implement Mailcow restore from backup
- [ ] Add backup selection from rsync server
- [ ] Implement pre-restore existing installation backup
- [ ] Add service verification after restore
- [ ] Add restore menu to TUI

**Deliverable:** Full restore capability via TUI

**Testing Checklist:**
- [ ] List backups from rsync server
- [ ] Restore nginx from latest backup
- [ ] Restore nginx from specific backup
- [ ] Restore Mailcow from latest backup
- [ ] Verify existing installations are backed up before restore
- [ ] Verify services start correctly after restore
- [ ] Test restore on clean system (no existing installation)

### Phase 4: Installation & System Config (Week 4)
**Goal:** Fresh installation and system configuration

**Tasks:**
- [ ] Implement `install.py` module
- [ ] Add Docker installation
- [ ] Add Mailcow fresh installation
- [ ] Add nginx installation
- [ ] Implement `system.py` module
- [ ] Add IPv6 disable functionality with GRUB
- [ ] Add firewall configuration
- [ ] Add installation and system menus to TUI

**Deliverable:** Complete installation automation

**Testing Checklist:**
- [ ] Install Docker on clean system
- [ ] Install Mailcow fresh (without restore)
- [ ] Install Mailcow with restore from backup
- [ ] Disable IPv6 and verify after reboot
- [ ] Configure firewall and verify rules applied

### Phase 5: Maintenance & Monitoring (Week 5)
**Goal:** Updates and status monitoring

**Tasks:**
- [ ] Implement `maintenance.py` module
- [ ] Add nginx update functionality
- [ ] Add Mailcow update functionality
- [ ] Implement `monitoring.py` module
- [ ] Add service status checking
- [ ] Add disk usage monitoring
- [ ] Add backup history viewing
- [ ] Add log viewing
- [ ] Add maintenance and monitoring menus to TUI

**Deliverable:** Complete maintenance and monitoring

### Phase 6: Scheduling & Automation (Week 6)
**Goal:** Automated backup scheduling

**Tasks:**
- [ ] Implement `scheduler.py` module
- [ ] Add cron job management for backups
- [ ] Add schedule configuration to TUI
- [ ] Implement automated cleanup scheduling
- [ ] Add notification system (email alerts)
- [ ] Test scheduled backups

**Deliverable:** Fully automated backup system

### Phase 7: Disaster Recovery (Week 7)
**Goal:** Complete disaster recovery capability

**Tasks:**
- [ ] Create disaster recovery documentation
- [ ] Implement automated recovery mode
- [ ] Create bootstrap script for fresh VPS
- [ ] Test complete disaster recovery on test VPS
- [ ] Document DNS requirements
- [ ] Create recovery runbook

**Deliverable:** Tested disaster recovery procedure

### Phase 8: Testing & Documentation (Week 8)
**Goal:** Production ready

**Tasks:**
- [ ] Write unit tests for critical functions
- [ ] Integration testing of full workflows
- [ ] Security audit
- [ ] Performance testing
- [ ] Write user documentation
- [ ] Create troubleshooting guide
- [ ] Final disaster recovery test

**Deliverable:** Production-ready application with documentation

## Testing Strategy

### Unit Tests

Test individual functions in isolation:

```python
# tests/test_backup.py
import unittest
from lib.backup import validate_backup_name, check_disk_space

class TestBackup(unittest.TestCase):
    def test_validate_backup_name(self):
        self.assertTrue(validate_backup_name("nginx-2025-01-01"))
        self.assertFalse(validate_backup_name("nginx-2025-01-01; rm -rf /"))
        self.assertFalse(validate_backup_name("../../../etc/passwd"))

    def test_check_disk_space(self):
        self.assertTrue(check_disk_space("/tmp", 1))  # 1GB should be available
        self.assertFalse(check_disk_space("/tmp", 999999))  # Not enough
```

### Integration Tests

Test complete workflows:

```python
# tests/test_integration.py
import unittest
from lib.backup import backup_nginx
from lib.restore import restore_nginx

class TestIntegration(unittest.TestCase):
    def test_backup_and_restore_nginx(self):
        # Create test nginx installation
        setup_test_nginx()

        # Backup
        result = backup_nginx(verify=True)
        self.assertTrue(result)

        # Restore
        result = restore_nginx("latest")
        self.assertTrue(result)

        # Verify nginx is running
        self.assertTrue(verify_nginx_running())
```

### Disaster Recovery Test

**Monthly Test Procedure:**
1. Spin up test VPS
2. Run disaster recovery script
3. Verify all services operational
4. Send/receive test emails
5. Document any issues
6. Destroy test VPS

### Test Matrix

| Test Scenario | nginx | Mailcow | System | Priority |
|---------------|-------|---------|--------|----------|
| Fresh Install | ✓ | ✓ | ✓ | HIGH |
| Backup | ✓ | ✓ | ✓ | HIGH |
| Restore | ✓ | ✓ | ✓ | HIGH |
| Update | ✓ | ✓ | ✓ | MEDIUM |
| Disaster Recovery | ✓ | ✓ | ✓ | HIGH |
| IPv6 Disable | - | - | ✓ | MEDIUM |
| Scheduled Backup | ✓ | ✓ | - | MEDIUM |
| Insufficient Disk | ✓ | ✓ | - | HIGH |
| Network Failure | ✓ | ✓ | - | HIGH |
| Corrupted Backup | ✓ | ✓ | - | MEDIUM |

## Deployment Plan

### Initial Deployment (on current VPS)

```bash
# 1. Create directory structure
mkdir -p /opt/server-manager/{config,lib,logs,state}

# 2. Clone or copy application files
# (During development, work in /root/sh-scripts then deploy)

# 3. Install dependencies
cd /opt/server-manager
pip3 install -r requirements.txt

# 4. Create initial configuration
cp config/settings.yaml.example config/settings.yaml
# Edit settings.yaml with your specific values

# 5. Encrypt secrets
age -r $(age-keygen -y /root/.age/key.txt) -o config/credentials.age <<EOF
borg_passphrase: "your-passphrase-here"
EOF

# 6. Make executable
chmod +x server_manager.py

# 7. Create symlink for easy access
ln -s /opt/server-manager/server_manager.py /usr/local/bin/server-manager

# 8. Test
server-manager
```

### Backup Current Scripts

Before deploying new Python application:

```bash
# Backup existing bash scripts
cd /root/sh-scripts
tar -czf /tmp/bash-scripts-backup-$(date +%Y%m%d).tar.gz .
# Upload to rsync server for safekeeping
```

### Migration Strategy

**Phased migration:**

1. **Phase 1:** Deploy Python app alongside bash scripts
2. **Phase 2:** Test Python backup/restore in parallel with bash
3. **Phase 3:** Switch to Python for daily operations
4. **Phase 4:** Keep bash scripts as backup for 1 month
5. **Phase 5:** Archive bash scripts

## Maintenance & Monitoring

### Regular Maintenance Tasks

**Daily (Automated):**
- Backup nginx (2 AM)
- Backup Mailcow (3 AM)
- Backup server-manager (4 AM)
- Prune old backups (5 AM)

**Weekly (Manual):**
- Review backup logs
- Check disk usage
- Verify backup integrity
- Review system logs

**Monthly:**
- Test disaster recovery
- Update system packages
- Update Mailcow
- Update nginx
- Review and update documentation

**Quarterly:**
- Security audit
- Review retention policies
- Test all backup/restore procedures
- Update disaster recovery plan

### Monitoring Checklist

- [ ] All Docker containers running
- [ ] Disk usage < 80%
- [ ] Backups completing successfully
- [ ] No errors in logs
- [ ] SSH access to rsync server working
- [ ] Email sending/receiving working
- [ ] nginx proxies working
- [ ] SSL certificates valid and not expiring soon

### Alerting

**Critical Alerts (Immediate Action):**
- Backup failure
- Disk usage > 90%
- Mailcow containers down
- nginx containers down

**Warning Alerts (Check within 24h):**
- Disk usage > 80%
- Backup taking longer than usual
- SSL certificate expiring in < 30 days

**Info Alerts:**
- Backup completed successfully
- Updates available
- Disk usage report

## Known Gotchas & Edge Cases

### 1. Mailcow Version Mismatches

**Problem:** Restoring old Mailcow backup on newer Mailcow version may fail
**Solution:**
- Store Mailcow version in backup metadata
- Check version compatibility before restore
- Run Mailcow update script after restore if needed

### 2. DNS Propagation After VPS Rebuild

**Problem:** New VPS has new IP, DNS takes time to propagate
**Solution:**
- Document current DNS records before disaster
- Update DNS immediately after new VPS deployment
- Use low TTL values for critical records (300-600 seconds)
- Test email with direct IP connection while waiting for DNS

### 3. DKIM Keys

**Problem:** DKIM keys must match DNS records
**Solution:**
- DKIM keys are in Mailcow backup (good!)
- After restore, verify DKIM DNS records still match
- If DNS records lost, re-publish from restored keys

### 4. Docker Volume Permissions

**Problem:** Restored files may have wrong ownership
**Solution:**
- Always set ownership after restore
- Mailcow containers run as specific users
- Use `docker-compose exec` to fix permissions if needed

### 5. Port Conflicts

**Problem:** Mailcow and nginx both want port 80/443
**Solution:**
- You've confirmed this isn't an issue (Mailcow uses internal nginx)
- Document port usage in configuration
- Check port availability before installation

### 6. Borg Repository Locks

**Problem:** Borg backup interrupted, leaves lock file
**Solution:**
```python
def break_borg_lock(repo):
    """Break Borg lock if backup was interrupted"""
    subprocess.run(['borg', 'break-lock', repo])
```

### 7. Rsync Server Disk Full

**Problem:** Remote backup server runs out of space
**Solution:**
- Check remote disk space before backup
- Alert if remote disk > 80%
- Aggressive pruning on remote server
- Consider multiple backup destinations

### 8. IPv6 Disable Requires Reboot

**Problem:** Can't disable IPv6 without reboot
**Solution:**
- Always inform user reboot is required
- Offer to schedule reboot or reboot immediately
- Verify IPv6 actually disabled after reboot
- Provide rollback procedure if issues

### 9. Mailcow Needs Time to Stabilize

**Problem:** After restore/restart, Mailcow containers need time to fully initialize
**Solution:**
- Wait 5-10 minutes after starting containers
- Check health status before declaring success
- Provide clear status messages during wait
- Run validation checks (connect to ports, check logs)

### 10. SSH Key Authentication

**Problem:** Automated backups need SSH access without password
**Solution:**
- Use SSH key without passphrase for automation
- Restrict key with `command=` in authorized_keys
- Use dedicated backup user on rsync server
- Store key securely with proper permissions (600)

## Future Enhancements

### Phase 9+: Advanced Features

1. **Multi-Server Support**
   - Manage multiple VPS servers from one interface
   - Centralized backup repository
   - Sync configuration across servers

2. **Web Interface**
   - Optional web UI using Flask/FastAPI
   - View backup status remotely
   - Trigger restores from web
   - RESTful API for automation

3. **Enhanced Notifications**
   - Email alerts
   - Webhook support (Discord, Slack)
   - SMS alerts for critical issues
   - Dashboard/status page

4. **Backup Encryption at Rest**
   - Client-side encryption before upload
   - Zero-knowledge backup (rsync server can't read data)
   - Key management system

5. **Incremental Mailcow Backups**
   - Daily incremental backups
   - Weekly full backups
   - Faster backup/restore cycles

6. **Automated Testing**
   - Automated disaster recovery testing
   - Restore to isolated test environment
   - Verify backup integrity automatically
   - Report on backup quality

7. **Configuration Management**
   - Template-based configuration
   - Environment-specific configs (dev/staging/prod)
   - Configuration versioning
   - Rollback capability

8. **Monitoring Dashboard**
   - Real-time service status
   - Historical metrics
   - Backup size trends
   - Disk usage predictions

9. **Multiple Backup Destinations**
   - Primary and secondary backup locations
   - Geographic redundancy
   - Cloud storage integration (S3, Backblaze B2)

10. **Compliance & Auditing**
    - Backup compliance reports
    - Audit trail of all operations
    - Retention policy enforcement
    - GDPR-compliant data handling

## Success Criteria

### Minimum Viable Product (MVP)

✓ **Core Functionality:**
- [ ] TUI-based interface (raspi-config style)
- [ ] Backup nginx to rsync server
- [ ] Backup Mailcow to rsync server
- [ ] Restore nginx from backup
- [ ] Restore Mailcow from backup
- [ ] Disable IPv6 via GRUB
- [ ] Fresh Mailcow installation

✓ **Reliability:**
- [ ] All backups verified before deletion
- [ ] Graceful error handling
- [ ] Comprehensive logging
- [ ] Pre-flight checks for all operations

✓ **Disaster Recovery:**
- [ ] Complete VPS rebuild tested successfully
- [ ] Recovery time < 3 hours
- [ ] All services functional after recovery
- [ ] Email sending/receiving works after recovery

### Production Ready

✓ **Everything in MVP plus:**
- [ ] Automated backup scheduling
- [ ] Backup retention management
- [ ] Service monitoring
- [ ] Update management
- [ ] Comprehensive documentation
- [ ] Disaster recovery runbook tested monthly

### Long-term Goals

✓ **Everything in Production plus:**
- [ ] 99% backup success rate
- [ ] Recovery time < 1 hour
- [ ] Zero data loss in disaster scenarios
- [ ] Multi-server management
- [ ] Web interface option

## Risk Assessment

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Backup corruption | HIGH | LOW | Verify all backups, multiple generations |
| Rsync server failure | HIGH | MEDIUM | Secondary backup destination |
| Failed disaster recovery | HIGH | LOW | Monthly testing, documented procedure |
| Mailcow version incompatibility | MEDIUM | MEDIUM | Version tracking, compatibility checks |
| Insufficient disk space | MEDIUM | MEDIUM | Space checks, alerts, aggressive pruning |
| SSH key compromise | HIGH | LOW | Key rotation, restricted access |
| GRUB misconfiguration | HIGH | LOW | Config validation, backup, console access |
| DNS propagation delays | MEDIUM | HIGH | Low TTL, documentation |
| Docker volume corruption | MEDIUM | LOW | Regular backups, checksums |
| Python dependency issues | LOW | MEDIUM | Virtual environment, pinned versions |

## Budget & Resources

### Time Investment

- Development: ~8 weeks (part-time)
- Testing: ~2 weeks
- Documentation: ~1 week
- **Total: ~11 weeks**

### Server Resources

- **VPS Requirements:**
  - CPU: 4+ cores
  - RAM: 8GB+ (Mailcow requires 6GB minimum)
  - Disk: 100GB+ (depends on email volume)
  - Network: Dedicated IP, open ports

- **Rsync Backup Server:**
  - Disk: 500GB+ (depends on retention)
  - Bandwidth: Moderate
  - Reliability: High uptime important

### Cost Considerations

- VPS: $20-40/month (varies by provider)
- Backup Server: $10-20/month (or self-hosted)
- Domain: $10-15/year
- **Total: ~$30-60/month**

## Conclusion

This comprehensive plan provides a roadmap for building a production-ready server management application. The phased approach allows for incremental development and testing, while the focus on disaster recovery ensures business continuity.

### Next Steps

1. **Review this plan** - Ensure it aligns with requirements
2. **Set up development environment** - Python, dependencies
3. **Start Phase 1** - Build foundation (TUI framework, config)
4. **Iterate** - Build, test, refine
5. **Test disaster recovery** - On test VPS before relying on it

### Key Principles

- **Security First** - Proper credential management, input validation
- **Test Everything** - Especially disaster recovery
- **Document As You Go** - Future you will thank present you
- **Keep It Simple** - Don't over-engineer
- **Verify Backups** - Untested backups are not backups

---

**Document Version:** 1.0
**Last Updated:** 2025-12-31
**Author:** Server Administrator
**Status:** Ready for Implementation
