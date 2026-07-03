#!/bin/bash
# await-gandi-transfer.sh -- Poll for domain transfer completion, then run setup
# Usage: await-gandi-transfer.sh <domain>
# Runs via cron (hourly). Self-removes its own cron entry after successful setup.

set -euo pipefail

if [ $# -ne 1 ] || [ -z "${1:-}" ]; then
    echo "Usage: $0 <domain>" >&2
    exit 2
fi

DOMAIN="$1"
CREDENTIALS_FILE="/root/.credentials.env"
SETUP_SCRIPT="/opt/server-manager/scripts/setup-gandi-domain.sh"
ALERT_EMAIL="micke@nysattra.se"
CRON_TAG="await-gandi-transfer-${DOMAIN}"

source "$CREDENTIALS_FILE"

# Check if domain exists at Gandi (transfer complete)
RESPONSE=$(curl -sf "https://api.gandi.net/v5/domain/domains/$DOMAIN" \
    -H "Authorization: Bearer $GANDI_TOKEN" 2>/dev/null) || true

if ! echo "$RESPONSE" | jq -e '.fqdn' >/dev/null 2>&1; then
    logger -t "$CRON_TAG" "$DOMAIN not yet at Gandi"
    exit 0
fi

# Domain found — run setup
logger -t "$CRON_TAG" "$DOMAIN found at Gandi, running setup..."

SETUP_OUTPUT=$("$SETUP_SCRIPT" "$DOMAIN" 2>&1) && SETUP_OK=true || SETUP_OK=false

if [ "$SETUP_OK" = true ]; then
    # Remove this domain's cron entry + its comment line (matches both forms)
    crontab -l 2>/dev/null \
        | grep -vF "await-gandi-transfer-${DOMAIN}" \
        | grep -vF "await-gandi-transfer.sh ${DOMAIN}" \
        | crontab -

    printf "To: %s\nFrom: VPS Automation <root@villaherrgard.com>\nSubject: Gandi transfer complete: %s — setup OK\n\n%s\n" \
        "$ALERT_EMAIL" "$DOMAIN" "$SETUP_OUTPUT" | msmtp -t

    logger -t "$CRON_TAG" "$DOMAIN setup complete, cron entry removed"
else
    printf "To: %s\nFrom: VPS Automation <root@villaherrgard.com>\nSubject: Gandi transfer complete: %s — setup FAILED\n\n%s\n" \
        "$ALERT_EMAIL" "$DOMAIN" "$SETUP_OUTPUT" | msmtp -t

    logger -t "$CRON_TAG" "$DOMAIN setup failed, will retry next hour"
fi
