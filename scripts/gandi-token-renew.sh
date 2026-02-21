#!/bin/bash
# Gandi PAT Auto-Renewal Script
# Checks token expiry and renews when <=30 days remaining.
# Called daily by cron at 12:00.
#
# API endpoints:
#   Check:  GET  https://id.gandi.net/tokeninfo  (Bearer auth) -> expires_in (seconds)
#   Renew:  POST https://id.gandi.net/v5/organization/access-tokens (Bearer auth, empty JSON)
#
# Renewal window: token must have <=30 days remaining (API rejects >30d).
# TTL doubles with each chained renewal (7->14->28->56 days).
# Old token stays valid until original expiry; no delete API.

set -euo pipefail

# Configuration
CREDENTIALS_FILE="/root/.credentials.env"
CERTBOT_CRED_FILE="/root/nginx/letsencrypt/credentials/credentials-gandi"
LOG_FILE="/var/log/gandi-token-renew.log"
BASE_DIR="/opt/server-manager"
VENV_PYTHON="${BASE_DIR}/venv/bin/python3"
RENEWAL_WINDOW_DAYS=30
URGENT_THRESHOLD_DAYS=7

# Logging (never log token values)
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# Send notification via server-manager NotificationManager
notify() {
    local level="$1"
    local subject="$2"
    local message="$3"
    cd "$BASE_DIR" && "$VENV_PYTHON" -c "
from lib.notifications import NotificationManager
nm = NotificationManager()
nm.send_custom_notification(
    subject='$subject',
    message='''$message''',
    level='$level'
)
" 2>/dev/null || true
}

# Load credentials
if [[ ! -f "$CREDENTIALS_FILE" ]]; then
    log "ERROR: Credentials file not found: $CREDENTIALS_FILE"
    exit 1
fi

source "$CREDENTIALS_FILE"

if [[ -z "${GANDI_TOKEN:-}" ]]; then
    log "ERROR: GANDI_TOKEN not set in $CREDENTIALS_FILE"
    exit 1
fi

# Check token expiry
log "Checking Gandi token expiry..."

TOKENINFO=$(curl -sf -X GET "https://id.gandi.net/tokeninfo" \
    -H "Authorization: Bearer $GANDI_TOKEN" 2>/dev/null) || {
    log "ERROR: Failed to query token info (token may be invalid)"
    notify "ERROR" "Gandi Token Check Failed" \
        "Failed to query Gandi token info. The token may be invalid or expired. Manual intervention required."
    exit 1
}

EXPIRES_IN=$(echo "$TOKENINFO" | jq -r '.expires_in // empty')

if [[ -z "$EXPIRES_IN" ]]; then
    log "ERROR: Could not extract expires_in from token info response"
    exit 1
fi

DAYS_REMAINING=$(( EXPIRES_IN / 86400 ))
log "Token has $DAYS_REMAINING days remaining ($EXPIRES_IN seconds)"

# Check if renewal is needed
if (( DAYS_REMAINING > RENEWAL_WINDOW_DAYS )); then
    log "No action needed ($DAYS_REMAINING days remaining, threshold: ${RENEWAL_WINDOW_DAYS}d)"
    exit 0
fi

log "Token within renewal window ($DAYS_REMAINING days <= ${RENEWAL_WINDOW_DAYS}d). Attempting renewal..."

# Attempt renewal
RENEW_RESPONSE=$(curl -sf -X POST "https://id.gandi.net/v5/organization/access-tokens" \
    -H "Authorization: Bearer $GANDI_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{}' 2>/dev/null) || {
    log "ERROR: Renewal API call failed"
    if (( DAYS_REMAINING <= URGENT_THRESHOLD_DAYS )); then
        notify "ERROR" "URGENT: Gandi Token Renewal Failed" \
            "Token renewal failed with only $DAYS_REMAINING days remaining. Manual intervention required immediately."
    else
        notify "WARNING" "Gandi Token Renewal Failed" \
            "Token renewal failed with $DAYS_REMAINING days remaining. Will retry tomorrow."
    fi
    exit 1
}

NEW_TOKEN=$(echo "$RENEW_RESPONSE" | jq -r '.access_token // empty')

if [[ -z "$NEW_TOKEN" ]]; then
    log "ERROR: Could not extract access_token from renewal response"
    if (( DAYS_REMAINING <= URGENT_THRESHOLD_DAYS )); then
        notify "ERROR" "URGENT: Gandi Token Renewal Failed" \
            "Renewal response did not contain a new token. $DAYS_REMAINING days remaining. Manual intervention required."
    else
        notify "WARNING" "Gandi Token Renewal Failed" \
            "Renewal response did not contain a new token. $DAYS_REMAINING days remaining. Will retry tomorrow."
    fi
    exit 1
fi

log "New token received. Performing atomic update of credentials file..."

# Atomic update of .credentials.env
cp "$CREDENTIALS_FILE" "${CREDENTIALS_FILE}.new"
sed -i "s|^GANDI_TOKEN=.*|GANDI_TOKEN=\"${NEW_TOKEN}\"|" "${CREDENTIALS_FILE}.new"

# Back up current file
cp "$CREDENTIALS_FILE" "${CREDENTIALS_FILE}.previous"

# Atomic move (same filesystem)
mv "${CREDENTIALS_FILE}.new" "$CREDENTIALS_FILE"
chmod 600 "$CREDENTIALS_FILE"

log "Credentials file updated. Verifying new token..."

# Verify new token works
VERIFY_RESPONSE=$(curl -sf -X GET "https://id.gandi.net/tokeninfo" \
    -H "Authorization: Bearer $NEW_TOKEN" 2>/dev/null) || {
    log "ERROR: New token verification failed! Reverting to previous token..."
    cp "${CREDENTIALS_FILE}.previous" "$CREDENTIALS_FILE"
    chmod 600 "$CREDENTIALS_FILE"
    log "Reverted to previous token"
    notify "ERROR" "Gandi Token Renewal: Verification Failed" \
        "New token failed verification. Reverted to previous token ($DAYS_REMAINING days remaining)."
    exit 1
}

NEW_EXPIRES_IN=$(echo "$VERIFY_RESPONSE" | jq -r '.expires_in // empty')
NEW_DAYS=$((NEW_EXPIRES_IN / 86400))
log "New token verified successfully ($NEW_DAYS days remaining)"

# Sync certbot credential file
if [[ -d "$(dirname "$CERTBOT_CRED_FILE")" ]]; then
    echo "dns_gandi_token=${NEW_TOKEN}" > "$CERTBOT_CRED_FILE"
    chmod 600 "$CERTBOT_CRED_FILE"
    log "Certbot credential file updated: $CERTBOT_CRED_FILE"
else
    log "WARNING: Certbot credentials directory does not exist, skipping sync"
fi

log "Token renewal complete. Old token had $DAYS_REMAINING days; new token has $NEW_DAYS days."

notify "INFO" "Gandi Token Renewed Successfully" \
    "Token renewed successfully. Old token had $DAYS_REMAINING days remaining. New token has $NEW_DAYS days remaining."

exit 0
