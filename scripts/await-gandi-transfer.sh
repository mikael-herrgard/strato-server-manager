#!/bin/bash
# await-gandi-transfer.sh -- Poll for domain transfer completion, then run setup
# Runs via cron (hourly). Self-removes from cron after successful setup.

set -euo pipefail

DOMAIN="nysattra.se"
CREDENTIALS_FILE="/root/.credentials.env"
SETUP_SCRIPT="/opt/server-manager/scripts/setup-gandi-domain.sh"
ALERT_EMAIL="micke@nysattra.se"
CRON_TAG="await-gandi-transfer"

source "$CREDENTIALS_FILE"

# Check if domain exists at Gandi
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
    # Remove ourselves from cron
    crontab -l 2>/dev/null | grep -v "$CRON_TAG" | crontab -

    printf "To: %s\nFrom: VPS Automation <root@villaherrgard.com>\nSubject: Gandi transfer complete: %s — setup OK\n\n%s\n" \
        "$ALERT_EMAIL" "$DOMAIN" "$SETUP_OUTPUT" | msmtp -t

    logger -t "$CRON_TAG" "$DOMAIN setup complete, cron entry removed"
else
    printf "To: %s\nFrom: VPS Automation <root@villaherrgard.com>\nSubject: Gandi transfer complete: %s — setup FAILED\n\n%s\n" \
        "$ALERT_EMAIL" "$DOMAIN" "$SETUP_OUTPUT" | msmtp -t

    logger -t "$CRON_TAG" "$DOMAIN setup failed, will retry next hour"
fi
