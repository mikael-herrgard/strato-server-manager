#!/bin/bash
##############################################################################
# DNS IP Update Script
# Updates A records and SPF TXT records when server IP changes
#
# Usage: update-dns-ip.sh <old_ip> <new_ip> [--dry-run]
#
# Sources: /root/.credentials.env and /root/.dns-config
# Logging: /var/log/dns-ip-update.log
##############################################################################

set -e
set -o pipefail

LOG_FILE="/var/log/dns-ip-update.log"
CREDENTIALS_FILE="/root/.credentials.env"
DNS_CONFIG_FILE="/root/.dns-config"
DRY_RUN=false

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_FILE"
    exit 1
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1" | tee -a "$LOG_FILE"
}

warn() {
    echo -e "${YELLOW}[WARNING]${NC} $1" | tee -a "$LOG_FILE"
}

##############################################################################
# Certbot credential sync function
##############################################################################

sync_certbot_credentials() {
    source "$CREDENTIALS_FILE"
    echo "dns_cloudflare_api_token=$CF_API_TOKEN" \
      > /root/nginx/letsencrypt/credentials/credentials-2
    chmod 600 /root/nginx/letsencrypt/credentials/credentials-2

    if [ -n "$GANDI_TOKEN" ]; then
        local cred_dir="/root/nginx/letsencrypt/credentials"
        local gandi_synced=0
        for cred_file in "$cred_dir"/credentials-*; do
            [ -f "$cred_file" ] || continue
            if grep -q "^dns_gandi_token=" "$cred_file"; then
                sed -i "s|^dns_gandi_token=.*|dns_gandi_token=$GANDI_TOKEN|" "$cred_file"
                chmod 600 "$cred_file"
                # Not ((gandi_synced++)): that returns exit status 1 when
                # incrementing from 0, which kills the script under set -e.
                gandi_synced=$((gandi_synced + 1))
            fi
        done
        if [ "$gandi_synced" -eq 0 ]; then
            echo "dns_gandi_token=$GANDI_TOKEN" > "$cred_dir/credentials-gandi"
            chmod 600 "$cred_dir/credentials-gandi"
        fi
    fi
    log "Certbot credential files synced from .credentials.env"
}

##############################################################################
# Parse arguments
##############################################################################

if [ $# -lt 2 ]; then
    echo "Usage: $0 <old_ip> <new_ip> [--dry-run]"
    echo ""
    echo "Updates DNS A records and SPF TXT records when server IP changes."
    echo ""
    echo "Arguments:"
    echo "  old_ip    The IP address to replace"
    echo "  new_ip    The new IP address"
    echo "  --dry-run Show what would change without making API calls"
    exit 1
fi

OLD_IP="$1"
NEW_IP="$2"
shift 2

while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run) DRY_RUN=true ;;
        *) error "Unknown argument: $1" ;;
    esac
    shift
done

# Validate IPs
if ! echo "$OLD_IP" | grep -qP '^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$'; then
    error "Invalid old IP: $OLD_IP"
fi
if ! echo "$NEW_IP" | grep -qP '^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$'; then
    error "Invalid new IP: $NEW_IP"
fi

if [ "$OLD_IP" = "$NEW_IP" ]; then
    log "Old and new IP are identical ($OLD_IP). Nothing to do."
    exit 0
fi

##############################################################################
# Source configuration
##############################################################################

if [ ! -f "$CREDENTIALS_FILE" ]; then
    error "Credentials file not found: $CREDENTIALS_FILE"
fi
source "$CREDENTIALS_FILE"

if [ ! -f "$DNS_CONFIG_FILE" ]; then
    error "DNS config file not found: $DNS_CONFIG_FILE"
fi
source "$DNS_CONFIG_FILE"

# Check required tools
if ! command -v jq &>/dev/null; then
    error "jq is not installed. Install with: apt-get install jq"
fi

log "========================================="
log "DNS IP Update: $OLD_IP -> $NEW_IP"
if $DRY_RUN; then
    log "MODE: DRY RUN (no changes will be made)"
fi
log "========================================="

TOTAL_UPDATED=0
TOTAL_ERRORS=0

##############################################################################
# Cloudflare Updates
##############################################################################

update_cloudflare_domains() {
    if [ -z "$CF_API_TOKEN" ] || [ -z "$CF_ZONE_ID" ]; then
        warn "Cloudflare credentials not set, skipping Cloudflare domains"
        return
    fi

    for DOMAIN in $CLOUDFLARE_DOMAINS; do
        log "Processing Cloudflare domain: $DOMAIN"

        # Get all A records for the zone
        RESPONSE=$(curl -s -X GET \
            "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/dns_records?type=A&per_page=100" \
            -H "Authorization: Bearer $CF_API_TOKEN" \
            -H "Content-Type: application/json")

        if [ "$(echo "$RESPONSE" | jq -r '.success')" != "true" ]; then
            warn "Failed to list A records for $DOMAIN: $(echo "$RESPONSE" | jq -r '.errors[0].message')"
            TOTAL_ERRORS=$((TOTAL_ERRORS + 1))
            continue
        fi

        # Find A records matching the old IP
        MATCHING_RECORDS=$(echo "$RESPONSE" | jq -c ".result[] | select(.content == \"$OLD_IP\")")

        while IFS= read -r RECORD; do
            [ -z "$RECORD" ] && continue
            RECORD_ID=$(echo "$RECORD" | jq -r '.id')
            RECORD_NAME=$(echo "$RECORD" | jq -r '.name')
            RECORD_PROXIED=$(echo "$RECORD" | jq -r '.proxied')
            RECORD_TTL=$(echo "$RECORD" | jq -r '.ttl')

            if $DRY_RUN; then
                log "  [DRY RUN] Would update A record: $RECORD_NAME ($OLD_IP -> $NEW_IP)"
            else
                UPDATE_RESPONSE=$(curl -s -X PATCH \
                    "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/dns_records/$RECORD_ID" \
                    -H "Authorization: Bearer $CF_API_TOKEN" \
                    -H "Content-Type: application/json" \
                    --data "{\"content\": \"$NEW_IP\"}")

                if [ "$(echo "$UPDATE_RESPONSE" | jq -r '.success')" = "true" ]; then
                    success "  Updated A record: $RECORD_NAME ($OLD_IP -> $NEW_IP)"
                    TOTAL_UPDATED=$((TOTAL_UPDATED + 1))
                else
                    warn "  Failed to update A record $RECORD_NAME: $(echo "$UPDATE_RESPONSE" | jq -r '.errors[0].message')"
                    TOTAL_ERRORS=$((TOTAL_ERRORS + 1))
                fi
            fi
        done <<< "$MATCHING_RECORDS"

        # Update SPF record
        SPF_RESPONSE=$(curl -s -X GET \
            "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/dns_records?type=TXT&name=$DOMAIN&per_page=100" \
            -H "Authorization: Bearer $CF_API_TOKEN" \
            -H "Content-Type: application/json")

        if [ "$(echo "$SPF_RESPONSE" | jq -r '.success')" = "true" ]; then
            SPF_RECORD=$(echo "$SPF_RESPONSE" | jq -c ".result[] | select(.content | contains(\"v=spf1\")) | select(.content | contains(\"$OLD_IP\"))")

            if [ -n "$SPF_RECORD" ]; then
                SPF_ID=$(echo "$SPF_RECORD" | jq -r '.id')
                SPF_CONTENT=$(echo "$SPF_RECORD" | jq -r '.content')
                NEW_SPF_CONTENT=$(echo "$SPF_CONTENT" | sed "s|ip4:$OLD_IP|ip4:$NEW_IP|g")

                if $DRY_RUN; then
                    log "  [DRY RUN] Would update SPF for $DOMAIN:"
                    log "    Old: $SPF_CONTENT"
                    log "    New: $NEW_SPF_CONTENT"
                else
                    SPF_UPDATE=$(curl -s -X PATCH \
                        "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/dns_records/$SPF_ID" \
                        -H "Authorization: Bearer $CF_API_TOKEN" \
                        -H "Content-Type: application/json" \
                        --data "{\"content\": \"$NEW_SPF_CONTENT\"}")

                    if [ "$(echo "$SPF_UPDATE" | jq -r '.success')" = "true" ]; then
                        success "  Updated SPF for $DOMAIN: ip4:$OLD_IP -> ip4:$NEW_IP"
                        TOTAL_UPDATED=$((TOTAL_UPDATED + 1))
                    else
                        warn "  Failed to update SPF for $DOMAIN: $(echo "$SPF_UPDATE" | jq -r '.errors[0].message')"
                        TOTAL_ERRORS=$((TOTAL_ERRORS + 1))
                    fi
                fi
            else
                log "  No SPF record with $OLD_IP found for $DOMAIN"
            fi
        fi
    done
}

##############################################################################
# Gandi Updates
##############################################################################

update_gandi_domains() {
    if [ -z "$GANDI_TOKEN" ]; then
        warn "Gandi token not set, skipping Gandi domains"
        return
    fi

    for DOMAIN in $GANDI_DOMAINS; do
        log "Processing Gandi domain: $DOMAIN"

        # Get all records for the domain
        RESPONSE=$(curl -s -X GET \
            "https://api.gandi.net/v5/livedns/domains/$DOMAIN/records" \
            -H "Authorization: Bearer $GANDI_TOKEN" \
            -H "Content-Type: application/json")

        # Check if we got a valid response (array)
        if ! echo "$RESPONSE" | jq -e 'type == "array"' >/dev/null 2>&1; then
            warn "Failed to list records for $DOMAIN (may not exist in Gandi yet)"
            continue
        fi

        # Find A records matching the old IP
        A_RECORDS=$(echo "$RESPONSE" | jq -c ".[] | select(.rrset_type == \"A\") | select(.rrset_values[] == \"$OLD_IP\")")

        while IFS= read -r RECORD; do
            [ -z "$RECORD" ] && continue
            RECORD_NAME=$(echo "$RECORD" | jq -r '.rrset_name')
            RECORD_VALUES=$(echo "$RECORD" | jq -r '.rrset_values[]')
            RECORD_TTL=$(echo "$RECORD" | jq -r '.rrset_ttl')

            # Build new values array replacing old IP with new
            NEW_VALUES=$(echo "$RECORD" | jq -c "[.rrset_values[] | if . == \"$OLD_IP\" then \"$NEW_IP\" else . end]")

            if $DRY_RUN; then
                log "  [DRY RUN] Would update A record: $RECORD_NAME.$DOMAIN ($OLD_IP -> $NEW_IP)"
            else
                UPDATE_RESPONSE=$(curl -s -X PUT \
                    "https://api.gandi.net/v5/livedns/domains/$DOMAIN/records/$RECORD_NAME/A" \
                    -H "Authorization: Bearer $GANDI_TOKEN" \
                    -H "Content-Type: application/json" \
                    --data "{\"rrset_ttl\": $RECORD_TTL, \"rrset_values\": $NEW_VALUES}")

                # Gandi returns 201 on success (empty body)
                if [ -z "$UPDATE_RESPONSE" ] || echo "$UPDATE_RESPONSE" | jq -e '.message' >/dev/null 2>&1; then
                    if [ -z "$UPDATE_RESPONSE" ]; then
                        success "  Updated A record: $RECORD_NAME.$DOMAIN ($OLD_IP -> $NEW_IP)"
                        TOTAL_UPDATED=$((TOTAL_UPDATED + 1))
                    else
                        warn "  Failed to update A record $RECORD_NAME.$DOMAIN: $UPDATE_RESPONSE"
                        TOTAL_ERRORS=$((TOTAL_ERRORS + 1))
                    fi
                else
                    success "  Updated A record: $RECORD_NAME.$DOMAIN ($OLD_IP -> $NEW_IP)"
                    TOTAL_UPDATED=$((TOTAL_UPDATED + 1))
                fi
            fi
        done <<< "$A_RECORDS"

        # Update SPF record
        SPF_RECORDS=$(echo "$RESPONSE" | jq -c ".[] | select(.rrset_type == \"TXT\") | select(.rrset_name == \"@\") | select(.rrset_values[] | contains(\"v=spf1\")) | select(.rrset_values[] | contains(\"$OLD_IP\"))")

        if [ -n "$SPF_RECORDS" ]; then
            while IFS= read -r SPF_RECORD; do
                [ -z "$SPF_RECORD" ] && continue
                SPF_TTL=$(echo "$SPF_RECORD" | jq -r '.rrset_ttl')
                SPF_VALUES=$(echo "$SPF_RECORD" | jq -c "[.rrset_values[] | gsub(\"ip4:$OLD_IP\"; \"ip4:$NEW_IP\")]")

                if $DRY_RUN; then
                    log "  [DRY RUN] Would update SPF for $DOMAIN:"
                    log "    Old values: $(echo "$SPF_RECORD" | jq -r '.rrset_values[]')"
                    log "    New values: $(echo "$SPF_VALUES" | jq -r '.[]')"
                else
                    SPF_UPDATE=$(curl -s -X PUT \
                        "https://api.gandi.net/v5/livedns/domains/$DOMAIN/records/@/TXT" \
                        -H "Authorization: Bearer $GANDI_TOKEN" \
                        -H "Content-Type: application/json" \
                        --data "{\"rrset_ttl\": $SPF_TTL, \"rrset_values\": $SPF_VALUES}")

                    if [ -z "$SPF_UPDATE" ]; then
                        success "  Updated SPF for $DOMAIN: ip4:$OLD_IP -> ip4:$NEW_IP"
                        TOTAL_UPDATED=$((TOTAL_UPDATED + 1))
                    else
                        warn "  Failed to update SPF for $DOMAIN: $SPF_UPDATE"
                        TOTAL_ERRORS=$((TOTAL_ERRORS + 1))
                    fi
                fi
            done <<< "$SPF_RECORDS"
        else
            log "  No SPF record with $OLD_IP found for $DOMAIN"
        fi
    done
}

##############################################################################
# Main
##############################################################################

update_cloudflare_domains
update_gandi_domains

# Sync certbot credentials (ensures consistency)
if ! $DRY_RUN; then
    sync_certbot_credentials
fi

##############################################################################
# Summary
##############################################################################

log "========================================="
log "DNS IP Update Complete"
log "  Records updated: $TOTAL_UPDATED"
log "  Errors: $TOTAL_ERRORS"
if $DRY_RUN; then
    log "  Mode: DRY RUN (no changes made)"
fi
log "========================================="

if [ $TOTAL_ERRORS -gt 0 ]; then
    exit 1
fi

exit 0
