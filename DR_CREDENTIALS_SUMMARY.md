# Disaster Recovery Credentials Documentation - Complete ✅

**Date:** 2026-01-01
**Status:** Documentation complete
**File:** `/opt/server-manager/DISASTER_RECOVERY_CREDENTIALS.md`

## What Was Created

A comprehensive 841-line (21KB) disaster recovery credentials reference document.

## Document Structure

### 1. Quick Reference Checklist
- Printable checklist of all credential files
- Checkbox format for tracking during recovery
- Clear priority: Critical vs Optional files

### 2. Detailed File Documentation

**For each of 8 credential files:**
- Current server path
- Fresh VPS destination path
- Required file permissions
- File contents/format
- Purpose and usage
- Backup commands
- Restore commands
- Verification commands

**Files Documented:**
1. `/root/.ssh/rsync.key` - Backup server SSH key (CRITICAL)
2. `/root/.ssh/github.key` - GitHub SSH key
3. `/root/.ssh/config` - SSH client configuration
4. `/opt/server-manager/config/settings.yaml` - Application config (CRITICAL)
5. `/opt/mailcow-dockerized/mailcow.conf` - Mailcow configuration (CRITICAL)
6. `/root/.env` - BORG_PASSPHRASE (CRITICAL - doesn't exist yet!)
7. `/opt/server-manager/config/notifications.yaml` - Email notifications (optional)
8. `/root/.ssh/known_hosts` - SSH known hosts (optional)

### 3. Step-by-Step Recovery Procedures

**Phase 1: Before Disaster (Preparation)**
- Complete backup script with all commands
- Instructions for creating credentials archive
- GPG/OpenSSL encryption commands
- Cloud storage upload guidance
- Inventory file creation

**Phase 2: During Disaster (Recovery)**
- Fresh VPS deployment
- Download and decrypt credentials
- Place files in correct locations
- Set proper permissions
- Verify each credential works
- Run bootstrap from GitHub
- Restore all services
- DNS update steps

### 4. Security Best Practices
- DO/DON'T lists for credential storage
- Encryption recommendations
- File permission requirements (600 vs 644)
- Multiple backup location strategy
- Password manager integration

### 5. Troubleshooting Guide
- 6 common issues with detailed solutions:
  - SSH permission denied
  - Borg decryption failures
  - GitHub clone failures
  - Mailcow startup issues
  - Settings.yaml not loading
  - Wrong file permissions

### 6. Verification Commands
- Test backup server access
- Test GitHub authentication
- Test Borg passphrase
- Check file permissions
- Verify Server Manager installation

## Key Features

✅ **Print-friendly** - Can be printed for offline reference
✅ **Copy-paste ready** - All commands ready to run
✅ **Comprehensive** - Covers every credential file
✅ **Security-focused** - Encryption and permission guidance
✅ **Troubleshooting** - Solutions for common issues
✅ **Checklist format** - Easy to track progress
✅ **Cloud storage ready** - Designed for Dropbox/Google Drive storage

## Critical Warnings Included

⚠️ **BORG_PASSPHRASE is single point of failure**
- Without it, ALL backups are permanently unrecoverable
- Must be EXACTLY the same (case-sensitive)
- Store in multiple secure locations

⚠️ **Encrypt before cloud upload**
- GPG or OpenSSL encryption required
- Never upload unencrypted credentials
- Store encryption password separately

⚠️ **File permissions are critical**
- SSH will refuse 644 private keys
- Borg will refuse 644 .env files
- Document specifies correct permissions for each file

## Usage

**For user:**
1. Read the document now
2. Follow "Phase 1: Before Disaster" to create backup
3. Store encrypted backup in cloud storage (Dropbox/Google Drive)
4. Store this document with the backup
5. Test the recovery process on test VPS

**During disaster:**
1. Open document
2. Follow "Phase 2: During Disaster" step-by-step
3. Use troubleshooting section if issues arise
4. Complete recovery in 45-80 minutes

## File Information

**Location:** `/opt/server-manager/DISASTER_RECOVERY_CREDENTIALS.md`
**Size:** 21 KB (841 lines)
**Permissions:** 600 (read/write by root only)
**Format:** Markdown (GitHub-flavored)

## Integration

This document:
- Complements `BOOTSTRAP_PREREQUISITES.md` (automated config copy)
- Provides manual alternative to automated bootstrap config
- References bootstrap installer for post-credential setup
- Should be stored with credential backups in cloud storage

## Next Steps for User

1. **Review the document:**
   ```bash
   less /opt/server-manager/DISASTER_RECOVERY_CREDENTIALS.md
   ```

2. **Create credentials backup NOW:**
   ```bash
   # Follow "Phase 1: Before Disaster" section
   mkdir -p ~/credentials-backup
   # ... follow instructions in document
   ```

3. **Encrypt and upload to cloud storage**

4. **Store this document with the backup**

5. **Test recovery on test VPS** (recommended!)

## Important Notes

**Missing but Critical:**
- `/root/.env` with BORG_PASSPHRASE doesn't exist on current server
- User needs to create it or document the passphrase
- Without this, backups CANNOT be decrypted

**Recommendation:** Create `/root/.env` now:
```bash
echo "BORG_PASSPHRASE='your-secure-passphrase-here'" > /root/.env
chmod 600 /root/.env
```

## Success Criteria Met

✅ Lists all credential files needed
✅ Provides backup commands for each file
✅ Provides restore commands for each file
✅ Shows proper file permissions
✅ Includes encryption guidance
✅ Includes troubleshooting
✅ Includes verification steps
✅ Ready for cloud storage
✅ Manual process (no scripts needed)
✅ Comprehensive and detailed

---

**Created:** 2026-01-01
**Status:** ✅ COMPLETE
**Ready for:** Cloud storage backup
