#!/bin/bash
##############################################################################
# Gandi Domain Setup Script
# Sets up a complete mail-ready DNS zone for a domain at Gandi.
#
# Performs: prerequisite checks, DNS record creation via LiveDNS API,
#           LiveDNS activation, DNSSEC enablement, and verification.
#
# Usage: setup-gandi-domain.sh <domain>
#
# Sources: /root/.credentials.env for GANDI_TOKEN
# Logging: stdout (structured for TUI consumption)
##############################################################################

set -e
set -o pipefail

CREDENTIALS_FILE="/root/.credentials.env"
MAIL_HOST="mail.villaherrgard.com"
MAILCOW_DIR="/opt/mailcow-dockerized"
TTL=10800

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

##############################################################################
# Parse arguments
##############################################################################

if [ $# -lt 1 ]; then
    echo "Usage: $0 <domain>"
    echo ""
    echo "Sets up complete DNS zone for a Gandi domain with mail records,"
    echo "DNSSEC, and all supporting records for Mailcow."
    echo ""
    echo "The domain must already exist at Gandi and in Mailcow with DKIM keys."
    exit 1
fi

DOMAIN="$1"

# Basic domain validation
if ! echo "$DOMAIN" | grep -qP '^[a-z0-9][a-z0-9.-]+\.[a-z]{2,}$'; then
    error "Invalid domain format: $DOMAIN"
fi

log "========================================="
log "Gandi Domain Setup: $DOMAIN"
log "========================================="

##############################################################################
# Gandi API helper
##############################################################################

gandi_api() {
    local method="$1"
    local endpoint="$2"
    local data="${3:-}"

    local args=(-s -X "$method"
        "https://api.gandi.net/v5${endpoint}"
        -H "Authorization: Bearer $GANDI_TOKEN"
        -H "Content-Type: application/json")

    if [ -n "$data" ]; then
        args+=(--data "$data")
    fi

    curl "${args[@]}" 2>/dev/null
}

# Create a DNS record via LiveDNS PUT
# Returns: 0 on success, 1 on failure
create_record() {
    local name="$1"
    local type="$2"
    local ttl="$3"
    shift 3
    # Remaining args are values (as JSON array string)
    local values="$1"

    local endpoint="/livedns/domains/$DOMAIN/records/$name/$type"
    local payload="{\"rrset_ttl\": $ttl, \"rrset_values\": $values}"

    local response
    response=$(gandi_api PUT "$endpoint" "$payload")

    # Gandi returns {"message":"DNS Record Created"} on success, or error JSON on failure
    if [ -z "$response" ]; then
        success "  $type $name"
        return 0
    fi

    # Check response message
    local msg
    msg=$(echo "$response" | jq -r '.message // empty' 2>/dev/null)

    if [ -z "$msg" ]; then
        # No message field - assume success
        success "  $type $name"
        return 0
    fi

    # "DNS Record Created" is a success response
    if echo "$msg" | grep -qi "created\|updated\|success"; then
        success "  $type $name"
        return 0
    fi

    # Anything else is an error
    warn "  $type $name - $msg"
    return 1
}

##############################################################################
# Prerequisite checks
##############################################################################

log "--- Prerequisite Checks ---"
CHECKS_PASSED=true

# 1. Credentials file
if [ ! -f "$CREDENTIALS_FILE" ]; then
    echo -e "${RED}[FAIL]${NC} Credentials file not found: $CREDENTIALS_FILE"
    CHECKS_PASSED=false
else
    success "Credentials file exists"
    source "$CREDENTIALS_FILE"
fi

# 2. GANDI_TOKEN
if [ -z "${GANDI_TOKEN:-}" ]; then
    echo -e "${RED}[FAIL]${NC} GANDI_TOKEN is empty or not set"
    CHECKS_PASSED=false
else
    success "GANDI_TOKEN is set"
fi

# Stop here if no token
if [ "$CHECKS_PASSED" = false ]; then
    error "Cannot proceed without credentials"
fi

# 3. Validate Gandi API token
info "Validating Gandi API token..."
TOKEN_CHECK=$(curl -sf "https://id.gandi.net/tokeninfo" \
    -H "Authorization: Bearer $GANDI_TOKEN" 2>/dev/null) || true

if [ -z "$TOKEN_CHECK" ] || ! echo "$TOKEN_CHECK" | jq -e '.expires_in' >/dev/null 2>&1; then
    # Try domain list as fallback token check
    DOMAIN_LIST=$(gandi_api GET "/domain/domains")
    if ! echo "$DOMAIN_LIST" | jq -e 'type == "array"' >/dev/null 2>&1; then
        echo -e "${RED}[FAIL]${NC} Gandi API token is invalid"
        CHECKS_PASSED=false
    else
        success "Gandi API token is valid (domain list check)"
    fi
else
    EXPIRES_DAYS=$(( $(echo "$TOKEN_CHECK" | jq -r '.expires_in') / 86400 ))
    success "Gandi API token is valid ($EXPIRES_DAYS days remaining)"
fi

# 4. Domain exists at Gandi
info "Checking domain at Gandi..."
DOMAIN_INFO=$(gandi_api GET "/domain/domains/$DOMAIN")
if echo "$DOMAIN_INFO" | jq -e '.fqdn' >/dev/null 2>&1; then
    DOMAIN_SERVICES=$(echo "$DOMAIN_INFO" | jq -r '.services[]? // empty' 2>/dev/null)
    success "Domain exists at Gandi: $DOMAIN"
else
    echo -e "${RED}[FAIL]${NC} Domain not found at Gandi: $DOMAIN"
    echo "         (Has the transfer completed?)"
    CHECKS_PASSED=false
fi

# 5. Domain exists in Mailcow
info "Checking domain in Mailcow..."
if [ ! -d "$MAILCOW_DIR" ]; then
    echo -e "${RED}[FAIL]${NC} Mailcow directory not found: $MAILCOW_DIR"
    CHECKS_PASSED=false
else
    REDIS_PASS=$(grep '^DBPASS=' "$MAILCOW_DIR/.env" 2>/dev/null | cut -d= -f2)
    MC_DOMAIN=$(cd "$MAILCOW_DIR" && docker compose exec -T mysql-mailcow \
        mysql -umailcow -p"$REDIS_PASS" mailcow \
        -N -e "SELECT domain FROM domain WHERE domain='$DOMAIN';" 2>/dev/null)

    if [ "$MC_DOMAIN" = "$DOMAIN" ]; then
        success "Domain exists in Mailcow: $DOMAIN"
    else
        echo -e "${RED}[FAIL]${NC} Domain not found in Mailcow: $DOMAIN"
        echo "         (Add it via Mailcow admin first)"
        CHECKS_PASSED=false
    fi
fi

# 6. DKIM public key exists
info "Checking DKIM key..."
REDIS_AUTH=$(grep '^REDISPASS=' "$MAILCOW_DIR/.env" 2>/dev/null | cut -d= -f2)
DKIM_PUBKEY=$(cd "$MAILCOW_DIR" && docker compose exec -T redis-mailcow \
    redis-cli -a "$REDIS_AUTH" HGET DKIM_PUB_KEYS "$DOMAIN" 2>/dev/null | tr -d '[:space:]')
DKIM_SELECTOR=$(cd "$MAILCOW_DIR" && docker compose exec -T redis-mailcow \
    redis-cli -a "$REDIS_AUTH" HGET DKIM_SELECTORS "$DOMAIN" 2>/dev/null | tr -d '[:space:]')

if [ -n "$DKIM_PUBKEY" ] && [ ${#DKIM_PUBKEY} -gt 100 ]; then
    DKIM_SELECTOR="${DKIM_SELECTOR:-dkim}"
    success "DKIM public key found (selector: $DKIM_SELECTOR, ${#DKIM_PUBKEY} chars)"
else
    echo -e "${RED}[FAIL]${NC} DKIM public key not found for $DOMAIN"
    echo "         (Generate DKIM key in Mailcow admin first)"
    CHECKS_PASSED=false
fi

# 7. mail.villaherrgard.com resolves
info "Checking mail host resolution..."
MAIL_IP=$(dig +short "$MAIL_HOST" A 2>/dev/null | head -1)
if [ -n "$MAIL_IP" ] && echo "$MAIL_IP" | grep -qP '^\d+\.\d+\.\d+\.\d+$'; then
    SERVER_IP="$MAIL_IP"
    success "$MAIL_HOST resolves to $SERVER_IP"
else
    echo -e "${RED}[FAIL]${NC} $MAIL_HOST does not resolve to an IP"
    CHECKS_PASSED=false
fi

# 8. Required tools
for tool in jq dig curl docker; do
    if ! command -v "$tool" &>/dev/null; then
        echo -e "${RED}[FAIL]${NC} Required tool not found: $tool"
        CHECKS_PASSED=false
    fi
done

# Abort if any checks failed
if [ "$CHECKS_PASSED" = false ]; then
    log ""
    error "Prerequisite checks failed. Fix the issues above and retry."
fi

log ""
log "All prerequisite checks passed."
log ""

##############################################################################
# DNS Record Creation
##############################################################################

log "--- Creating DNS Records ---"
RECORDS_CREATED=0
RECORDS_FAILED=0

# Wrapper: call create_record and track success/failure without triggering set -e
do_record() {
    if create_record "$@"; then
        RECORDS_CREATED=$((RECORDS_CREATED + 1))
    else
        RECORDS_FAILED=$((RECORDS_FAILED + 1))
    fi
}

# A record: @ -> server IP
do_record "@" "A" "$TTL" "[\"$SERVER_IP\"]"

# MX record: @ -> mail.villaherrgard.com. priority 10
do_record "@" "MX" "$TTL" "[\"10 $MAIL_HOST.\"]"

# SPF TXT: @ -> v=spf1 mx a:mail.villaherrgard.com ip4:{IP} -all
do_record "@" "TXT" "$TTL" "[\"\\\"v=spf1 mx a:$MAIL_HOST ip4:$SERVER_IP -all\\\"\"]"

# DKIM TXT: {selector}._domainkey -> v=DKIM1;k=rsa;t=s;s=email;p={KEY}
do_record "${DKIM_SELECTOR}._domainkey" "TXT" "$TTL" \
    "[\"\\\"v=DKIM1;k=rsa;t=s;s=email;p=$DKIM_PUBKEY\\\"\"]"

# DMARC TXT: _dmarc -> v=DMARC1; p=quarantine; adkim=s; aspf=s
do_record "_dmarc" "TXT" "$TTL" \
    "[\"\\\"v=DMARC1; p=quarantine; rua=mailto:postmaster@$DOMAIN; ruf=mailto:postmaster@$DOMAIN; fo=1\\\"\"]"

# MTA-STS A: mta-sts -> server IP
do_record "mta-sts" "A" "$TTL" "[\"$SERVER_IP\"]"

# MTA-STS TXT: _mta-sts -> v=STSv1; id={YYYYMMDD}0001;
MTA_STS_ID="$(date '+%Y%m%d')0001"
do_record "_mta-sts" "TXT" "$TTL" "[\"\\\"v=STSv1; id=$MTA_STS_ID\\\"\"]"

# TLS-RPT TXT: _smtp._tls -> v=TLSRPTv1; rua=mailto:postmaster@{domain}
do_record "_smtp._tls" "TXT" "$TTL" \
    "[\"\\\"v=TLSRPTv1; rua=mailto:postmaster@$DOMAIN\\\"\"]"

# Autoconfig CNAME: autoconfig -> mail.villaherrgard.com.
do_record "autoconfig" "CNAME" "$TTL" "[\"$MAIL_HOST.\"]"

# Autodiscover CNAME: autodiscover -> mail.villaherrgard.com.
do_record "autodiscover" "CNAME" "$TTL" "[\"$MAIL_HOST.\"]"

# SRV records
do_record "_autodiscover._tcp" "SRV" "$TTL" "[\"0 1 443 $MAIL_HOST.\"]"
do_record "_imap._tcp" "SRV" "$TTL" "[\"0 1 143 $MAIL_HOST.\"]"
do_record "_imaps._tcp" "SRV" "$TTL" "[\"0 1 993 $MAIL_HOST.\"]"
do_record "_pop3._tcp" "SRV" "$TTL" "[\"0 1 110 $MAIL_HOST.\"]"
do_record "_pop3s._tcp" "SRV" "$TTL" "[\"0 1 995 $MAIL_HOST.\"]"
do_record "_submission._tcp" "SRV" "$TTL" "[\"0 1 587 $MAIL_HOST.\"]"

# CAA records: issue, issuewild, iodef
do_record "@" "CAA" "$TTL" \
    "[\"0 issue \\\"letsencrypt.org\\\"\", \"0 issuewild \\\"letsencrypt.org\\\"\", \"0 iodef \\\"mailto:postmaster@$DOMAIN\\\"\"]"

log ""
log "DNS records: $RECORDS_CREATED created, $RECORDS_FAILED failed"

if [ $RECORDS_FAILED -gt 0 ]; then
    warn "Some records failed to create. Review the output above."
fi

##############################################################################
# LiveDNS Activation
##############################################################################

log ""
log "--- LiveDNS Activation ---"

# Check current nameserver service
CURRENT_NS=$(echo "$DOMAIN_INFO" | jq -r '.nameserver.current // empty')

if [ "$CURRENT_NS" = "livedns" ]; then
    success "LiveDNS is already active"
else
    info "Activating Gandi LiveDNS nameservers..."
    NS_RESPONSE=$(gandi_api PUT "/domain/domains/$DOMAIN/nameservers" \
        '{"nameservers": ["ns-64-a.gandi.net", "ns-90-b.gandi.net", "ns-58-c.gandi.net"]}')

    if [ -z "$NS_RESPONSE" ] || ! echo "$NS_RESPONSE" | jq -e '.message' >/dev/null 2>&1; then
        success "LiveDNS nameservers set"
    else
        warn "Nameserver update response: $(echo "$NS_RESPONSE" | jq -r '.message // empty')"
    fi

    # Verify by re-checking domain info
    sleep 2
    VERIFY_INFO=$(gandi_api GET "/domain/domains/$DOMAIN")
    VERIFY_SERVICES=$(echo "$VERIFY_INFO" | jq -r '.services[]?' 2>/dev/null)

    if echo "$VERIFY_SERVICES" | grep -q "gandilivedns"; then
        success "LiveDNS activation verified"
    else
        warn "LiveDNS activation not yet confirmed (may take a moment)"
    fi
fi

##############################################################################
# DNSSEC Enablement
##############################################################################

log ""
log "--- DNSSEC Enablement ---"

# Check if DNSSEC is already active
if echo "$DOMAIN_SERVICES" | grep -q "dnssec"; then
    success "DNSSEC is already active"
else
    # Step 1: Create DNSSEC signing key in LiveDNS
    info "Creating DNSSEC signing key..."
    KEY_RESPONSE=$(gandi_api POST "/livedns/domains/$DOMAIN/keys" '{"flags": 257}')

    if echo "$KEY_RESPONSE" | jq -e '.id' >/dev/null 2>&1; then
        KEY_ID=$(echo "$KEY_RESPONSE" | jq -r '.id')
        success "DNSSEC key created: $KEY_ID"
    else
        # Key may already exist
        EXISTING_KEYS=$(gandi_api GET "/livedns/domains/$DOMAIN/keys")
        ACTIVE_KEY=$(echo "$EXISTING_KEYS" | jq -r '.[] | select(.deleted == false) | .id' 2>/dev/null | head -1)

        if [ -n "$ACTIVE_KEY" ]; then
            KEY_ID="$ACTIVE_KEY"
            success "Using existing DNSSEC key: $KEY_ID"
        else
            warn "Could not create DNSSEC key: $(echo "$KEY_RESPONSE" | jq -r '.message // empty')"
            KEY_ID=""
        fi
    fi

    if [ -n "$KEY_ID" ]; then
        # Step 2: Wait for key to propagate, then get DS record
        info "Waiting for DNSSEC key propagation (10s)..."
        sleep 10

        # Get the key details including DS record
        KEY_DETAIL=$(gandi_api GET "/livedns/domains/$DOMAIN/keys/$KEY_ID")
        DS_RECORD=$(echo "$KEY_DETAIL" | jq -r '.ds // empty')

        if [ -n "$DS_RECORD" ]; then
            # Extract keytag and algorithm from DS record for domain registration
            # DS format: "domain. TTL IN DS keytag algorithm digest_type digest"
            KEYTAG=$(echo "$DS_RECORD" | awk '{print $5}')
            ALGO=$(echo "$DS_RECORD" | awk '{print $6}')
            DIGEST_TYPE=$(echo "$DS_RECORD" | awk '{print $7}')
            DIGEST=$(echo "$DS_RECORD" | awk '{print $8}')

            info "DS record: keytag=$KEYTAG algo=$ALGO digest_type=$DIGEST_TYPE"

            # Step 3: Also try to dig the DNSKEY from Gandi's nameserver directly
            info "Verifying DNSKEY via dig..."
            DIG_RESULT=$(dig @ns-64-a.gandi.net DNSKEY "$DOMAIN" +short 2>/dev/null | head -1)
            if [ -n "$DIG_RESULT" ]; then
                success "DNSKEY visible at Gandi nameservers"
            else
                warn "DNSKEY not yet visible at nameservers (may take time)"
            fi

            # Step 4: Publish DS record at registrar level
            info "Publishing DS record to registrar..."

            # Get the public key from the key detail
            PUBKEY=$(echo "$KEY_DETAIL" | jq -r '.public_key // empty')

            if [ -n "$PUBKEY" ]; then
                DS_PAYLOAD=$(cat <<DSJSON
{
    "algorithm": $ALGO,
    "digest": "$DIGEST",
    "digest_type": $DIGEST_TYPE,
    "keytag": $KEYTAG,
    "public_key": "$PUBKEY",
    "type": "ksk",
    "flags": 257
}
DSJSON
)
                DS_RESPONSE=$(gandi_api POST "/domain/domains/$DOMAIN/dnskeys" "$DS_PAYLOAD")

                if [ -z "$DS_RESPONSE" ] || echo "$DS_RESPONSE" | jq -e '.id' >/dev/null 2>&1; then
                    success "DS record published at registrar"
                else
                    MSG=$(echo "$DS_RESPONSE" | jq -r '.message // empty')
                    if echo "$MSG" | grep -qi "already"; then
                        success "DS record already exists at registrar"
                    else
                        warn "DS record publish response: $MSG"
                    fi
                fi
            else
                warn "Could not extract public key from DNSSEC key detail"
            fi
        else
            warn "DS record not available yet in key detail"
        fi
    fi

    # Final DNSSEC verification
    sleep 3
    FINAL_INFO=$(gandi_api GET "/domain/domains/$DOMAIN")
    FINAL_SERVICES=$(echo "$FINAL_INFO" | jq -r '.services[]?' 2>/dev/null)
    if echo "$FINAL_SERVICES" | grep -q "dnssec"; then
        success "DNSSEC is now active"
    else
        warn "DNSSEC not yet showing as active (may take time to propagate)"
    fi
fi

##############################################################################
# Verification
##############################################################################

log ""
log "--- DNS Verification ---"

# Use Gandi's own nameserver for verification
NS="ns-64-a.gandi.net"

info "Verifying records via $NS..."

# Check MX
MX_CHECK=$(dig @"$NS" MX "$DOMAIN" +short 2>/dev/null)
if echo "$MX_CHECK" | grep -q "$MAIL_HOST"; then
    success "MX record verified: $MX_CHECK"
else
    warn "MX record not found or incorrect"
fi

# Check SPF
SPF_CHECK=$(dig @"$NS" TXT "$DOMAIN" +short 2>/dev/null | grep "v=spf1")
if [ -n "$SPF_CHECK" ]; then
    success "SPF record verified: $SPF_CHECK"
else
    warn "SPF record not found"
fi

# Check DKIM
DKIM_CHECK=$(dig @"$NS" TXT "${DKIM_SELECTOR}._domainkey.$DOMAIN" +short 2>/dev/null | grep "v=DKIM1")
if [ -n "$DKIM_CHECK" ]; then
    success "DKIM record verified"
else
    warn "DKIM record not yet visible (may take a moment)"
fi

# Check DMARC
DMARC_CHECK=$(dig @"$NS" TXT "_dmarc.$DOMAIN" +short 2>/dev/null | grep "v=DMARC1")
if [ -n "$DMARC_CHECK" ]; then
    success "DMARC record verified: $DMARC_CHECK"
else
    warn "DMARC record not found"
fi

# Count total records
TOTAL_RECORDS=$(gandi_api GET "/livedns/domains/$DOMAIN/records" | jq 'length' 2>/dev/null)
info "Total records in zone: ${TOTAL_RECORDS:-unknown}"

##############################################################################
# Summary
##############################################################################

log ""
log "========================================="
log "Gandi Domain Setup Complete: $DOMAIN"
log "  DNS records created: $RECORDS_CREATED"
log "  DNS records failed:  $RECORDS_FAILED"
log "========================================="

if [ $RECORDS_FAILED -gt 0 ]; then
    warn "Some records failed. Review output above."
fi

log ""
log "--- Manual Steps Remaining ---"
info "1. In Nginx Proxy Manager:"
info "   - Request SSL certificate for $DOMAIN, mta-sts.$DOMAIN"
info "     (Use DNS challenge with Gandi credentials)"
info "2. In Nginx Proxy Manager:"
info "   - Create proxy host: $DOMAIN -> http://127.0.0.1:8080 (or desired backend)"
info "   - Create proxy host: mta-sts.$DOMAIN -> Mailcow MTA-STS"
info "3. Wait for DNS propagation (up to 48h for full global propagation)"
info "4. Test email delivery: send test emails to/from $DOMAIN"

if [ $RECORDS_FAILED -gt 0 ]; then
    exit 1
fi

exit 0
