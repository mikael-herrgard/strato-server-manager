# Server Manager - Bootstrap Installation

Automated installation system for deploying Server Manager to fresh VPS instances.

## Quick Start

**For Ubuntu 20.04+ / Debian 11+ servers:**

```bash
curl -fsSL https://raw.githubusercontent.com/mikael-herrgard/strato-server-manager/main/bootstrap/install.sh | bash
```

This single command will download and execute the complete installation process.

## What The Installer Does

The bootstrap system performs a complete automated installation:

### 1. **Pre-flight Checks**
- Verifies running as root
- Checks OS compatibility (Ubuntu/Debian)
- Validates disk space (10GB minimum)
- Tests internet connectivity
- Verifies Python version (3.9+)

### 2. **System Package Installation**
Installs all required system packages:
- `dialog` - TUI interface
- `borgbackup` - Backup system
- `rsync` - Remote sync
- `docker.io` and `docker-compose` - Container management
- `ufw` - Firewall
- `git` - Version control
- `python3`, `python3-venv`, `python3-pip` - Python environment
- `openssh-client` - SSH connectivity

### 3. **Application Download**
- Clones the latest Server Manager code from GitHub
- Creates installation directory at `/opt/server-manager`
- Downloads all application files

### 4. **Python Environment Setup**
- Creates virtual environment in `/opt/server-manager/venv`
- Installs all Python dependencies
- Verifies critical modules (dialog, yaml, paramiko, docker)

### 5. **Configuration Setup**
- Creates `settings.yaml` from template (`settings.yaml.example`)
- User edits configuration with their specific values
- Credentials should be set up manually before running bootstrap (see CREDENTIALS_SETUP.md)

### 6. **Directory Structure**
Creates all required directories:
- `/opt/server-manager/logs` - Application logs
- `/opt/server-manager/state` - State files
- `/var/backups/local` - Backup staging area

### 7. **Symlink Creation**
- Creates `/usr/local/bin/server-manager` symlink
- Makes all scripts executable
- Sets proper permissions

### 8. **Installation Verification**
- Verifies all components installed correctly
- Tests Python module imports
- Validates directory structure
- Confirms symlink creation

## Requirements

### Server Requirements
- **Operating System:** Ubuntu 20.04+ or Debian 11+
- **Architecture:** x86_64 (amd64)
- **Disk Space:** 10GB minimum free
- **Memory:** 2GB minimum recommended
- **Network:** Internet connectivity required

### Access Requirements
- **Root access** or sudo privileges
- **SSH key authentication** configured (for config copy)
- **GitHub access** (HTTPS, port 443)

### For Configuration Copy
If copying configuration from an existing server:
- SSH access to source server
- SSH key authentication configured
- Source server must have Server Manager installed

## Usage Examples

### Standard Installation
```bash
curl -fsSL https://raw.githubusercontent.com/mikael-herrgard/strato-server-manager/main/bootstrap/install.sh | bash
```

### Install from Development Branch
```bash
BRANCH=development curl -fsSL https://raw.githubusercontent.com/mikael-herrgard/strato-server-manager/main/bootstrap/install.sh | bash
```

### Install from Custom Repository
```bash
GITHUB_REPO=https://github.com/youruser/server-manager.git \
curl -fsSL https://raw.githubusercontent.com/mikael-herrgard/strato-server-manager/main/bootstrap/install.sh | bash
```

### Non-Interactive Installation
```bash
SKIP_CONFIRM=true curl -fsSL https://raw.githubusercontent.com/mikael-herrgard/strato-server-manager/main/bootstrap/install.sh | bash
```

### Download and Inspect Before Running
```bash
# Download initiator
curl -fsSL https://raw.githubusercontent.com/mikael-herrgard/strato-server-manager/main/bootstrap/install.sh -o install.sh

# Review the script
cat install.sh

# Download main bootstrap
curl -fsSL https://raw.githubusercontent.com/mikael-herrgard/strato-server-manager/main/bootstrap/bootstrap.sh -o bootstrap.sh

# Review the bootstrap
less bootstrap.sh

# Run when ready
chmod +x bootstrap.sh
sudo ./bootstrap.sh
```

## Post-Installation Configuration

After the bootstrap installer completes, you'll need to configure Server Manager:

### 1. Edit Configuration File
```bash
nano /opt/server-manager/config/settings.yaml
```

Update the following sections:
- `backup.rsync_server` - Your backup server details
- `backup.retention` - Backup retention policy
- `services` - Service paths and configurations

### 2. Create Environment File
```bash
echo "BORG_PASSPHRASE='your-secure-passphrase-here'" > /root/.env
chmod 600 /root/.env
```

**Important:** Use a strong, unique passphrase. This encrypts all your backups.

### 3. Generate SSH Key for Backups
```bash
ssh-keygen -t ed25519 -f /root/.ssh/rsync.key -N ""
chmod 600 /root/.ssh/rsync.key
```

### 4. Add Public Key to Backup Server
```bash
# Display your public key:
cat /root/.ssh/rsync.key.pub

# On your backup server, add this to:
# ~/.ssh/authorized_keys
```

### 5. Test Backup Server Connection
```bash
ssh -i /root/.ssh/rsync.key user@backup-server.com "echo 'Connection successful'"
```

## Running Server Manager

After installation completes:

```bash
server-manager
```

Or with full path:
```bash
/opt/server-manager/server_manager.py
```

## Troubleshooting

### Installation Fails During Package Install
```bash
# Update package lists manually:
apt-get update
apt-get upgrade

# Re-run bootstrap:
curl -fsSL https://raw.githubusercontent.com/mikael-herrgard/strato-server-manager/main/bootstrap/install.sh | bash
```

### Git Clone Fails
```bash
# Check GitHub access:
curl -I https://github.com

# Try with different branch:
GITHUB_BRANCH=main curl -fsSL https://raw.githubusercontent.com/.../install.sh | bash
```

### SSH Configuration Copy Fails
```bash
# Ensure SSH key authentication works:
ssh root@your-existing-server.com "echo test"

# If using non-standard port:
# Edit ~/.ssh/config first with correct port
```

### Python Module Import Fails
```bash
# Activate venv and reinstall:
cd /opt/server-manager
source venv/bin/activate
pip install --upgrade -r requirements.txt
```

### Symlink Not Found
```bash
# Recreate symlink manually:
ln -sf /opt/server-manager/server_manager.py /usr/local/bin/server-manager
chmod +x /opt/server-manager/server_manager.py
```

### Server Manager Won't Start
```bash
# Check log file:
cat /opt/server-manager/logs/server-manager.log

# Verify configuration:
cat /opt/server-manager/config/settings.yaml

# Test manually:
cd /opt/server-manager
sudo ./server_manager.py
```

## Log Files

All installation output is logged to:
```
/tmp/server-manager-bootstrap-YYYYMMDD-HHMMSS.log
```

Check this file for detailed error messages if installation fails.

## Uninstallation

To remove Server Manager completely:

```bash
# Remove installation directory
rm -rf /opt/server-manager

# Remove symlink
rm -f /usr/local/bin/server-manager

# Remove backups (optional)
rm -rf /var/backups/local

# Remove configuration files (optional)
rm -f /root/.env
rm -f /root/.ssh/rsync.key*
```

## Security Considerations

### Credentials
- `.env` file contains Borg passphrase - never share or commit to git
- SSH keys are private - protect with proper permissions (600)
- Configuration may contain sensitive information

### Network
- Bootstrap downloads scripts from GitHub over HTTPS
- Configuration copy uses SSH encryption
- All file transfers are encrypted

### Permissions
- Installation requires root access
- All files owned by root with restricted permissions
- Log files may contain sensitive information

## Advanced Usage

### Environment Variables

The bootstrap script supports several environment variables:

```bash
# Custom GitHub repository
export GITHUB_REPO="https://github.com/youruser/server-manager.git"

# Custom branch
export GITHUB_BRANCH="development"

# Skip confirmation prompts
export SKIP_CONFIRM="true"

# Run bootstrap
./bootstrap.sh
```

### Offline Installation

For servers without direct internet access:

1. Download on a connected machine:
```bash
git clone https://github.com/mikael-herrgard/strato-server-manager.git
cd server-manager
pip download -r requirements.txt -d deps/
```

2. Transfer to offline server:
```bash
rsync -avz server-manager/ root@offline-server:/opt/server-manager/
```

3. Install on offline server:
```bash
cd /opt/server-manager
python3 -m venv venv
venv/bin/pip install --no-index --find-links=deps/ -r requirements.txt
```

## Getting Help

- **Documentation:** `/opt/server-manager/README.md`
- **Project Status:** `/opt/server-manager/PROJECT_STATUS.md`
- **Log Files:** `/opt/server-manager/logs/`
- **Issues:** Check installation log in `/tmp/`

## Version

Bootstrap Version: 1.0.0
Compatible with Server Manager v1.0+
