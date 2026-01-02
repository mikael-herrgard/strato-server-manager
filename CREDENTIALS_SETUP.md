# Fresh VPS Credentials Setup - Quick Reference

Simple checklist for setting up credentials on a fresh VPS before running bootstrap.

---

## 1. SSH Keys

Place your backed-up SSH keys:

```bash
mkdir -p /root/.ssh
chmod 700 /root/.ssh

# Rsync/backup server key
cp rsync.key /root/.ssh/rsync.key
chmod 600 /root/.ssh/rsync.key

# GitHub key
cp github.key /root/.ssh/github.key
chmod 600 /root/.ssh/github.key
```

**Verify:**
```bash
ssh -i /root/.ssh/rsync.key zh5554@zh5554.rsync.net "echo OK"
ssh -T -i /root/.ssh/github.key git@github.com
```

---

## 2. SSH Config

Create `/root/.ssh/config` with your host aliases:

```bash
cat > /root/.ssh/config <<'EOF'
Host github.com
    HostName github.com
    User git
    IdentityFile /root/.ssh/github.key

Host rsync-backup
    HostName zh5554.rsync.net
    User zh5554
    IdentityFile /root/.ssh/rsync.key
EOF

chmod 644 /root/.ssh/config
```

**Verify:**
```bash
ssh rsync-backup "echo OK"
```

---

## 3. Borg Passphrase

Create `/root/.env` with your Borg backup passphrase:

```bash
echo "BORG_PASSPHRASE='your-actual-passphrase-here'" > /root/.env
chmod 600 /root/.env
```

**Verify:**
```bash
cat /root/.env
# Should show: BORG_PASSPHRASE='your-passphrase'

# Test it works:
export BORG_PASSPHRASE=$(grep BORG_PASSPHRASE /root/.env | cut -d"'" -f2)
borg list zh5554@zh5554.rsync.net:/backups/nginx
```

---

## 4. Settings (Optional - Bootstrap Can Copy)

If you have your settings.yaml backed up:

```bash
mkdir -p /opt/server-manager/config
cp settings.yaml /opt/server-manager/config/settings.yaml
chmod 600 /opt/server-manager/config/settings.yaml
```

Otherwise, bootstrap will create a template you can edit later.

---

## 5. Run Bootstrap

Once credentials are in place:

```bash
curl -fsSL https://raw.githubusercontent.com/USER/server-manager/main/bootstrap/install.sh | bash
```

---

## Quick Checklist

- [ ] `/root/.ssh/rsync.key` (permissions: 600)
- [ ] `/root/.ssh/github.key` (permissions: 600)
- [ ] `/root/.ssh/config` (permissions: 644)
- [ ] `/root/.env` with BORG_PASSPHRASE (permissions: 600)
- [ ] Optional: `/opt/server-manager/config/settings.yaml` (permissions: 600)

**Then run bootstrap from GitHub.**
