# Bootstrap Prerequisites - Fresh VPS Setup

## Overview

Before running the bootstrap installer on a fresh VPS, you need to set up SSH access so the installer can copy your configuration from your existing server.

## Two Installation Scenarios

### Scenario A: Copy Configuration from Existing Server (Recommended)

**What This Does:**
- Bootstrap installer copies your settings.yaml, SSH keys, and .env from existing server
- Fastest and most reliable method
- No manual configuration needed

**Prerequisites:**

#### 1. SSH Key on Fresh VPS
Generate a temporary SSH key on the **fresh VPS**:

```bash
# On fresh VPS (as root)
ssh-keygen -t ed25519 -f /root/.ssh/id_ed25519 -N ""
```

#### 2. Add Key to Existing Server
Copy the public key to your **existing server**:

```bash
# Display public key on fresh VPS
cat /root/.ssh/id_ed25519.pub

# Then on your EXISTING server, add it to authorized_keys:
echo "ssh-ed25519 AAAA... root@fresh-vps" >> /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
```

Or use ssh-copy-id:
```bash
# From fresh VPS:
ssh-copy-id -i /root/.ssh/id_ed25519 root@your-existing-server.com
```

#### 3. Test SSH Connection
```bash
# From fresh VPS:
ssh root@your-existing-server.com "echo 'Connection successful'"
```

#### 4. Run Bootstrap
```bash
curl -fsSL https://raw.githubusercontent.com/USER/server-manager/main/bootstrap/install.sh | bash
```

When prompted:
- ✅ "Copy configuration from existing server?" → **Yes**
- Enter your existing server hostname/IP
- Enter SSH user (usually `root`)
- ✅ "Copy SSH backup key?" → **Yes**
- Enter key filename (default: `rsync.key`)
- ✅ "Copy .env file?" → **Yes**

**What Gets Copied:**
- `/opt/server-manager/config/settings.yaml` → Contains rsync server details
- `/opt/server-manager/config/notifications.yaml` → Email settings (optional)
- `/root/.ssh/rsync.key` → SSH key for backup server access
- `/root/.env` → Contains `BORG_PASSPHRASE`

**Result:**
Fresh VPS now has everything needed to access your backup server and restore from Borg backups.

---

### Scenario B: Manual Configuration (Alternative)

**What This Does:**
- Bootstrap creates fresh config from template
- You manually configure everything
- More work but useful if existing server is unavailable

**Prerequisites:**

You need to have these details saved somewhere safe **before** your server fails:

#### 1. Borg Passphrase
The passphrase used to encrypt your backups. You'll need to manually create `/root/.env`:

```bash
echo "BORG_PASSPHRASE='your-actual-passphrase-here'" > /root/.env
chmod 600 /root/.env
```

**Critical:** This must be the **exact same passphrase** used to create the backups on your original server.

#### 2. SSH Key for Backup Server
You need the private key that accesses your rsync/backup server:

```bash
# Copy your backup SSH key to fresh VPS
# (Get it from your existing server or backup location)
nano /root/.ssh/rsync.key
# Paste the private key
chmod 600 /root/.ssh/rsync.key

# Generate public key from private key:
ssh-keygen -y -f /root/.ssh/rsync.key > /root/.ssh/rsync.key.pub
```

#### 3. Configuration File
Copy `settings.yaml` content from your existing server or saved backup:

```bash
nano /opt/server-manager/config/settings.yaml
```

Must include:
- `backup.rsync_server.host` - Backup server hostname/IP
- `backup.rsync_server.user` - SSH user on backup server
- `backup.rsync_server.ssh_key` - Path to SSH key (`/root/.ssh/rsync.key`)
- `backup.rsync_server.base_path` - Remote path to backups
- `borg.remote_path` - Borg binary path on backup server

#### 4. Run Bootstrap
```bash
curl -fsSL https://raw.githubusercontent.com/USER/server-manager/main/bootstrap/install.sh | bash
```

When prompted:
- ❌ "Copy configuration from existing server?" → **No**
- Bootstrap creates template config
- Manually edit files as shown above

---

## What Each Component Does

### 1. BORG_PASSPHRASE (in /root/.env)

**Purpose:** Decrypts your Borg backups

**Format:**
```bash
BORG_PASSPHRASE='your-secure-passphrase'
```

**Requirements:**
- Must match the passphrase used when creating backups
- Case-sensitive
- Should be strong and unique
- File permissions: 600 (read/write by root only)

**Where It's Used:**
- When restoring nginx backups
- When restoring Mailcow backups
- When restoring application backups
- When listing available backups

**If Wrong:**
```
Error: Failed to decrypt repository - wrong passphrase
```

### 2. SSH Key for Backup Server (/root/.ssh/rsync.key)

**Purpose:** Authenticates to your rsync/backup server

**Format:** Ed25519 or RSA private key

**Requirements:**
- Private key on VPS: `/root/.ssh/rsync.key` (permissions: 600)
- Public key on backup server: `~/.ssh/authorized_keys`
- Key must allow rsync and borg commands

**Where It's Used:**
- Downloading backups from remote server
- Uploading backups to remote server
- Listing available backups
- Running borg commands on remote server

**Test It:**
```bash
ssh -i /root/.ssh/rsync.key user@backup-server.com "echo 'Success'"
```

### 3. Configuration File (settings.yaml)

**Purpose:** Tells Server Manager where and how to access backups

**Critical Settings:**
```yaml
backup:
  rsync_server:
    host: "backup.example.com"    # Backup server hostname/IP
    user: "backup-user"            # SSH user
    ssh_key: "/root/.ssh/rsync.key"  # Path to SSH key
    base_path: "/backups"          # Remote directory

borg:
  remote_path: "borg14"            # Borg binary on remote (or full path)
  compression: "zstd,3"
```

**Where It's Used:**
- All backup operations
- All restore operations
- Listing backups
- Scheduled backups

---

## GitHub Repository Access

### For Public Repositories

**No prerequisites needed!** The bootstrap script uses HTTPS:
```bash
git clone https://github.com/mikael-herrgard/strato-server-manager.git
```

This works without authentication.

### For Private Repositories

If your repository is private, you need **one of**:

#### Option 1: Personal Access Token (Recommended)
```bash
# Set before running bootstrap:
export GITHUB_REPO="https://YOUR_TOKEN@github.com/user/server-manager.git"

# Then run bootstrap:
curl -fsSL https://raw.githubusercontent.com/.../install.sh | bash
```

#### Option 2: SSH Key for GitHub
```bash
# Generate SSH key on fresh VPS:
ssh-keygen -t ed25519 -f /root/.ssh/github -N ""

# Add public key to GitHub:
cat /root/.ssh/github.pub
# Go to GitHub → Settings → SSH Keys → Add

# Configure git to use this key:
export GIT_SSH_COMMAND="ssh -i /root/.ssh/github"

# Then run bootstrap with SSH URL:
export GITHUB_REPO="git@github.com:user/server-manager.git"
curl -fsSL https://raw.githubusercontent.com/.../install.sh | bash
```

---

## Complete Setup Checklist

### Before Disaster Strikes (Do This Now!)

Save these items in a **secure location** (password manager, encrypted USB, etc.):

- [ ] **Borg passphrase** - From `/root/.env` on current server
- [ ] **Backup server SSH key** - Copy `/root/.ssh/rsync.key` (private key)
- [ ] **settings.yaml** - Copy `/opt/server-manager/config/settings.yaml`
- [ ] **Backup server details:**
  - [ ] Hostname/IP address
  - [ ] SSH user
  - [ ] SSH port (if not 22)
  - [ ] Path to backups
- [ ] **GitHub repository URL** (if private)
- [ ] **Domain names and DNS provider login**

### Fresh VPS - Day of Recovery

#### Step 1: Prepare Fresh VPS
```bash
# Generate temporary SSH key on fresh VPS
ssh-keygen -t ed25519 -f /root/.ssh/id_ed25519 -N ""

# Display public key
cat /root/.ssh/id_ed25519.pub
```

#### Step 2: Add Key to Existing Server (if still accessible)
```bash
# On existing server:
echo "ssh-ed25519 AAAA... root@new-vps" >> /root/.ssh/authorized_keys
```

**OR** if existing server is down but you have SSH key:
Skip to manual configuration mode.

#### Step 3: Test Connection (if copying config)
```bash
# From fresh VPS:
ssh root@existing-server.com "echo test"
```

#### Step 4: Run Bootstrap
```bash
curl -fsSL https://raw.githubusercontent.com/USER/server-manager/main/bootstrap/install.sh | bash
```

Follow prompts based on your scenario (A or B above).

#### Step 5: Verify Access to Backup Server
```bash
# Test SSH connection:
ssh -i /root/.ssh/rsync.key backup-user@backup-server.com "echo success"

# Test borg access:
server-manager
# Navigate to: Restore Management → List Available Backups
```

#### Step 6: Restore Services
```bash
server-manager
# 1. Restore nginx
# 2. Restore Mailcow
# 3. Restore Application
```

---

## Troubleshooting

### "SSH connection to existing server failed"

**During bootstrap config copy:**
```bash
# Verify key exists:
ls -la /root/.ssh/id_ed25519

# Test connection manually:
ssh -v root@existing-server.com

# Check authorized_keys on existing server:
ssh root@existing-server.com "cat ~/.ssh/authorized_keys"
```

**Solution:**
- Ensure public key is in existing server's authorized_keys
- Verify firewall allows SSH
- Try using IP instead of hostname
- Fall back to manual configuration mode

### "Cannot decrypt Borg repository"

**During restore:**
```
Error: Failed to open repository - wrong passphrase
```

**Check:**
```bash
# Verify .env file exists:
cat /root/.env

# Should show:
BORG_PASSPHRASE='your-passphrase'
```

**Solution:**
- Ensure passphrase matches original
- Check for extra spaces or quotes
- Passphrase is case-sensitive
- Verify file permissions: `chmod 600 /root/.env`

### "Cannot connect to backup server"

**During restore:**
```
Error: ssh connection failed to backup-server.com
```

**Check:**
```bash
# Test SSH key:
ssh -i /root/.ssh/rsync.key backup-user@backup-server.com "echo test"

# Check key permissions:
ls -la /root/.ssh/rsync.key
# Should be: -rw------- (600)

# Verify settings.yaml:
cat /opt/server-manager/config/settings.yaml | grep -A5 rsync_server
```

**Solution:**
- Verify backup server is online
- Check SSH key permissions: `chmod 600 /root/.ssh/rsync.key`
- Verify public key in backup server's authorized_keys
- Test with verbose SSH: `ssh -v -i /root/.ssh/rsync.key ...`

### "Borg command not found"

**During restore:**
```
Error: borg14: command not found
```

**Check:**
```bash
# Test borg on backup server:
ssh -i /root/.ssh/rsync.key backup-user@backup-server.com "which borg"
ssh -i /root/.ssh/rsync.key backup-user@backup-server.com "borg --version"
```

**Solution:**
- Update `borg.remote_path` in settings.yaml with full path
- Or create symlink on backup server: `ln -s /usr/bin/borg /usr/local/bin/borg14`

---

## Security Best Practices

### Protect Your Recovery Credentials

1. **Store offline:** Keep Borg passphrase and SSH keys in password manager
2. **Encrypt backups:** Use encrypted USB or cloud storage for credential backups
3. **Test regularly:** Verify you can access saved credentials
4. **Document everything:** Write down where each piece is stored
5. **Multiple copies:** Store in 2-3 different secure locations

### SSH Key Security

```bash
# Always set proper permissions:
chmod 600 /root/.ssh/rsync.key
chmod 600 /root/.env
chmod 600 /root/.ssh/id_ed25519

# Verify permissions:
ls -la /root/.ssh/
ls -la /root/.env
```

### Borg Passphrase Security

- **Never commit to git**
- **Never include in scripts or logs**
- **Use strong passphrase** (20+ characters)
- **Don't share via email or chat**
- **Store in password manager**

---

## Quick Reference Card

**Save this for disaster recovery:**

```
========================================
SERVER MANAGER - DISASTER RECOVERY
========================================

Backup Server:
  Host: _________________________
  User: _________________________
  SSH Key: /root/.ssh/rsync.key

Borg Passphrase:
  Stored in: /root/.env
  Value: _________________________

GitHub:
  Repo: _________________________
  Branch: _________________________

Recovery Command:
  curl -fsSL https://raw.githubusercontent.com/USER/server-manager/main/bootstrap/install.sh | bash

Recovery Time: 45-80 minutes

Restore Order:
  1. nginx
  2. Mailcow
  3. Application

DNS Provider:
  _________________________
  Login: _________________________
========================================
```

---

## Summary

**Minimum Requirements for Recovery:**

1. **Access to backup server via SSH** (with key)
2. **Borg passphrase** (to decrypt backups)
3. **Configuration file** (or ability to copy from existing server)

**Best Practice:**
- Set up config copy during bootstrap (Scenario A)
- Keep offline backup of credentials (just in case)
- Test recovery process before you need it

**Result:**
Fresh VPS can connect to backup server, decrypt Borg repositories, and restore all services.
