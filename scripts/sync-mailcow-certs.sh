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

# DANE/TLSA: all four mail domains MX to mail.villaherrgard.com,
# so a single TLSA record (3 1 1, SPKI sha256) protects all of them.
# Hosted in Cloudflare, rotated via API when the cert public key changes.
CREDENTIALS_FILE="/root/.credentials.env"
TLSA_RECORD_NAME="_25._tcp.mail.villaherrgard.com"

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
    cert_status="OK: IMAP fingerprint matches."
else
    log "WARNING: IMAP fingerprint does not match after restart"
    cert_status="WARN: IMAP fingerprint mismatch.
Expected: ${npm_fp}
Got:      ${served_fp}"
fi

# Rotate DANE/TLSA record so Microsoft (and other DANE-enforcing receivers)
# don't reject mail after a key rotation. Mailcow renewals can change the
# public key, which invalidates the previously published 3 1 1 SPKI hash.
tlsa_status="SKIPPED"
if [ -f "$CREDENTIALS_FILE" ]; then
    # shellcheck disable=SC1090
    source "$CREDENTIALS_FILE"
fi

if [ -n "${CF_API_TOKEN:-}" ] && [ -n "${CF_ZONE_ID:-}" ]; then
    new_spki=$(openssl x509 -in "$NPM_CERT" -noout -pubkey \
        | openssl pkey -pubin -outform DER 2>/dev/null \
        | sha256sum | awk '{print $1}')

    cf_response=$(curl -fsS -G "https://api.cloudflare.com/client/v4/zones/${CF_ZONE_ID}/dns_records" \
        -H "Authorization: Bearer ${CF_API_TOKEN}" \
        --data-urlencode "type=TLSA" \
        --data-urlencode "name=${TLSA_RECORD_NAME}" 2>/dev/null) || cf_response=""

    record_id=$(echo "$cf_response" | python3 -c \
        'import json,sys; d=json.load(sys.stdin); r=d.get("result",[]); print(r[0]["id"] if r else "")' 2>/dev/null)
    current_spki=$(echo "$cf_response" | python3 -c \
        'import json,sys; d=json.load(sys.stdin); r=d.get("result",[]); print(r[0]["data"]["certificate"] if r else "")' 2>/dev/null)

    if [ -z "$record_id" ]; then
        log "WARNING: TLSA record ${TLSA_RECORD_NAME} not found in Cloudflare zone"
        tlsa_status="WARN: TLSA record not found in Cloudflare"
    elif [ "$current_spki" = "$new_spki" ]; then
        log "TLSA already matches new SPKI -- no rotation needed"
        tlsa_status="OK: TLSA already matches (${new_spki:0:16}...)"
    else
        log "Rotating TLSA: ${current_spki:0:16}... -> ${new_spki:0:16}..."
        patch_payload=$(python3 -c \
            'import json,sys; print(json.dumps({"data":{"usage":3,"selector":1,"matching_type":1,"certificate":sys.argv[1]},"comment":"Mailcow mail server (auto-rotated)"}))' \
            "$new_spki")

        if curl -fsS -X PATCH "https://api.cloudflare.com/client/v4/zones/${CF_ZONE_ID}/dns_records/${record_id}" \
            -H "Authorization: Bearer ${CF_API_TOKEN}" \
            -H "Content-Type: application/json" \
            --data "$patch_payload" >/dev/null 2>&1; then
            log "TLSA rotated successfully"
            tlsa_status="OK: TLSA rotated to ${new_spki:0:16}..."
        else
            log "ERROR: TLSA rotation failed (Cloudflare API error)"
            tlsa_status="ERROR: TLSA rotation failed -- DANE delivery will break"
        fi
    fi
else
    log "WARNING: CF_API_TOKEN/CF_ZONE_ID not set, skipping TLSA rotation"
    tlsa_status="SKIPPED: Cloudflare credentials not available"
fi

# Single consolidated notification covering both cert sync and TLSA rotation
if [[ "$cert_status" == OK* && "$tlsa_status" == OK* ]]; then
    notify "[VPS OK] Mailcow certificate synced" \
        "New wildcard certificate synced to Mailcow at $(date '+%Y-%m-%d %H:%M:%S').

New cert expires: ${npm_expiry}

Services restarted: ${MC_SERVICES[*]}

Cert sync: ${cert_status}
TLSA:      ${tlsa_status}"
else
    notify "[VPS ALERT] Mailcow cert sync needs attention" \
        "Certificate sync ran at $(date '+%Y-%m-%d %H:%M:%S') but at least one step did not succeed cleanly.

New cert expires: ${npm_expiry}

Cert sync: ${cert_status}
TLSA:      ${tlsa_status}

Manual investigation may be required."
fi
