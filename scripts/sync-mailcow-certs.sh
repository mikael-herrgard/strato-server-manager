#!/bin/bash
# sync-mailcow-certs.sh -- Sync NPM wildcard cert to Mailcow
# Runs via cron daily at 04:00
#
# NPM manages Let's Encrypt certs inside its container, but Mailcow
# reads certs from the host filesystem. This script bridges the gap
# by comparing fingerprints and copying when they differ.

set -euo pipefail

ALERT_EMAIL="micke@nysattra.se"
FROM_NAME="VPS Certificate Sync"
LOG_FILE="/var/log/mailcow-cert-sync.log"

# Source: NPM's renewed cert (host-side mount)
NPM_CERT="/root/nginx/letsencrypt/live/npm-2/fullchain.pem"
NPM_KEY="/root/nginx/letsencrypt/live/npm-2/privkey.pem"

# Destination: Mailcow's cert directory
MC_CERT="/opt/mailcow-dockerized/data/assets/ssl/cert.pem"
MC_KEY="/opt/mailcow-dockerized/data/assets/ssl/key.pem"

MC_SERVICES=(
    mailcowdockerized-dovecot-mailcow-1
    mailcowdockerized-postfix-mailcow-1
    mailcowdockerized-nginx-mailcow-1
)

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

notify() {
    local subject="$1"
    local body="$2"
    msmtp -t <<EOF
To: ${ALERT_EMAIL}
From: ${FROM_NAME} <root@villaherrgard.com>
Subject: ${subject}

${body}
EOF
}

# Verify source certs exist
if [ ! -f "$NPM_CERT" ] || [ ! -f "$NPM_KEY" ]; then
    log "ERROR: NPM certificate files not found"
    notify "[VPS ALERT] Mailcow cert sync failed" \
        "NPM certificate files not found at ${NPM_CERT}. Manual intervention required."
    exit 1
fi

# Compare fingerprints -- exit silently if certs already match
npm_fp=$(openssl x509 -in "$NPM_CERT" -noout -fingerprint -sha256 2>/dev/null)
mc_fp=$(openssl x509 -in "$MC_CERT" -noout -fingerprint -sha256 2>/dev/null)

if [ "$npm_fp" = "$mc_fp" ]; then
    exit 0
fi

# Certs differ -- sync needed
npm_expiry=$(openssl x509 -in "$NPM_CERT" -noout -enddate | sed 's/notAfter=//')
log "Certificate change detected, syncing to Mailcow (new cert expires: ${npm_expiry})"

# Backup current Mailcow certs
cp "$MC_CERT" "${MC_CERT}.bak-$(date +%Y%m%d-%H%M%S)" 2>/dev/null || true
cp "$MC_KEY" "${MC_KEY}.bak-$(date +%Y%m%d-%H%M%S)" 2>/dev/null || true

# Copy new certs
cp "$NPM_CERT" "$MC_CERT"
cp "$NPM_KEY" "$MC_KEY"
log "Certificates copied"

# Restart Mailcow services
docker restart "${MC_SERVICES[@]}"
log "Mailcow services restarted"

# Wait for services to come up, then verify
sleep 5
served_fp=$(echo | openssl s_client -connect localhost:993 -servername mail.villaherrgard.com 2>/dev/null \
    | openssl x509 -noout -fingerprint -sha256 2>/dev/null)

if [ "$served_fp" = "$npm_fp" ]; then
    log "Verified: IMAP now serving the new certificate"
    notify "[VPS OK] Mailcow certificate synced" \
        "New wildcard certificate synced to Mailcow at $(date '+%Y-%m-%d %H:%M:%S').

New cert expires: ${npm_expiry}

Services restarted: ${MC_SERVICES[*]}
Verification: IMAP fingerprint matches."
else
    log "WARNING: IMAP fingerprint does not match after restart"
    notify "[VPS ALERT] Mailcow cert sync - verification failed" \
        "Certificate was copied and services restarted, but IMAP is not serving the expected certificate.

Expected: ${npm_fp}
Got:      ${served_fp}

Manual investigation required."
fi
