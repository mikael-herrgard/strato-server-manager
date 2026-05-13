#!/bin/bash
# mailcow-post-update-fixes.sh -- Re-apply local fixes after a Mailcow upgrade
#
# Mailcow's update.sh runs `git merge -X theirs` which overwrites tracked
# config files. This server has three persistent local needs that get
# clobbered every upgrade:
#   1. php-fpm + dovecot must bind to 0.0.0.0 / "*" (IPv6 is disabled).
#   2. data/{web,conf,assets} files need 644/755 perms, but UMASK=027
#      leaves them 640/750 after `git checkout` — containers run as
#      www-data and 403 on the unreadable files.
#   3. Custom postscreen_dnsbl_sites block lives in main.cf, which is
#      tracked and gets reverted on update.
#
# Fix (3) by moving the block into data/conf/postfix/extra.cf, which is
# NOT shipped by mailcow and is preserved across updates -- one-time
# idempotent migration, this script handles it.
#
# Usage: ./mailcow-post-update-fixes.sh [--dry-run]

set -euo pipefail

MAILCOW_DIR="/opt/mailcow-dockerized"
DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[OK]${NC} $*"; }
warn() { echo -e "${YELLOW}[..]${NC} $*"; }
err()  { echo -e "${RED}[!!]${NC} $*" >&2; }

run() {
    if $DRY_RUN; then
        echo "  DRY-RUN: $*"
    else
        eval "$@"
    fi
}

cd "$MAILCOW_DIR"

##############################################################################
# 1. IPv6 listeners (php-fpm pools.conf + dovecot.conf)
##############################################################################

POOLS="data/conf/phpfpm/php-fpm.d/pools.conf"
DOVECOT="data/conf/dovecot/dovecot.conf"

if grep -qE '^listen = \[::\]:900[12]$' "$POOLS"; then
    warn "php-fpm pools.conf binds to [::] -- patching to 0.0.0.0"
    run "sed -i 's|^listen = \[::\]:9001\$|listen = 0.0.0.0:9001|; s|^listen = \[::\]:9002\$|listen = 0.0.0.0:9002|' '$POOLS'"
    PHPFPM_CHANGED=1
else
    log "php-fpm pools.conf listeners already on 0.0.0.0"
    PHPFPM_CHANGED=0
fi

if grep -qE '^listen = \*,\[::\]$' "$DOVECOT"; then
    warn "dovecot.conf binds to *,[::] -- patching to *"
    run "sed -i 's|^listen = \*,\[::\]\$|listen = *|' '$DOVECOT'"
    DOVECOT_CHANGED=1
else
    log "dovecot.conf listener already on * only"
    DOVECOT_CHANGED=0
fi

##############################################################################
# 2. Migrate postscreen_dnsbl_sites override to extra.cf (idempotent)
##############################################################################

EXTRA_CF="data/conf/postfix/extra.cf"
MAIN_CF="data/conf/postfix/main.cf"

if grep -q '^postscreen_dnsbl_sites' "$EXTRA_CF" 2>/dev/null; then
    log "postscreen_dnsbl_sites already in extra.cf (survives updates)"
    POSTFIX_CHANGED=0
else
    warn "postscreen_dnsbl_sites missing from extra.cf -- appending"
    run "cat >> '$EXTRA_CF'" <<'EXTRA_BLOCK'

# Custom DNSBL set -- migrated from main.cf user-overrides 2026-05-13
# so it survives mailcow update.sh's `git merge -X theirs`.
postscreen_dnsbl_sites = wl.mailspike.net=127.0.0.[18;19;20]*-2
  hostkarma.junkemailfilter.com=127.0.0.1*-2
  list.dnswl.org=127.0.[0..255].0*-2
  list.dnswl.org=127.0.[0..255].1*-4
  list.dnswl.org=127.0.[0..255].2*-6
  list.dnswl.org=127.0.[0..255].3*-8
  bl.spamcop.net*2
  bl.suomispam.net*2
  hostkarma.junkemailfilter.com=127.0.0.2*3
  hostkarma.junkemailfilter.com=127.0.0.4*2
  hostkarma.junkemailfilter.com=127.0.1.2*1
  backscatter.spameatingmonkey.net*2
  bl.ipv6.spameatingmonkey.net*2
  bl.spameatingmonkey.net*2
  b.barracudacentral.org=127.0.0.2*7
  bl.mailspike.net=127.0.0.2*5
  bl.mailspike.net=127.0.0.[10;11;12]*4
  zen.spamhaus.org=127.0.0.[10;11]*8
  zen.spamhaus.org=127.0.0.[4..7]*6
  zen.spamhaus.org=127.0.0.3*4
  zen.spamhaus.org=127.0.0.2*3
EXTRA_BLOCK
    POSTFIX_CHANGED=1
fi

# Once extra.cf has it, main.cf shouldn't -- harmless duplicate otherwise,
# postfix uses the last definition wins, and extra.cf is included after.
if grep -q '^postscreen_dnsbl_sites' "$MAIN_CF" 2>/dev/null; then
    warn "main.cf still has postscreen_dnsbl_sites (duplicate, will be"
    warn "  overridden by extra.cf; harmless but consider trimming manually)"
fi

##############################################################################
# 3. UMASK 027 -> chmod sweep on data/{web,conf,assets}
##############################################################################
# Find files/dirs with wrong perms before changing -- gives an honest count
# in dry-run mode. Group perms 0 (=) is the symptom of UMASK 027.

WRONG_FILES=$(find data/web data/conf data/assets -type f ! -perm -040 2>/dev/null | wc -l)
WRONG_DIRS=$(find data/web data/conf data/assets -type d ! -perm -050 2>/dev/null | wc -l)

if [[ "$WRONG_FILES" -gt 0 || "$WRONG_DIRS" -gt 0 ]]; then
    warn "UMASK 027 perms: ${WRONG_FILES} files + ${WRONG_DIRS} dirs unreadable by www-data"
    run "find data/web data/conf data/assets -type f -exec chmod 644 {} +"
    run "find data/web data/conf data/assets -type d -exec chmod 755 {} +"
    PERMS_CHANGED=1
else
    log "data/{web,conf,assets} perms already correct (644/755)"
    PERMS_CHANGED=0
fi

##############################################################################
# 4. Restart services whose config we touched
##############################################################################

SERVICES_TO_RESTART=()
[[ "$PHPFPM_CHANGED"  == 1 ]] && SERVICES_TO_RESTART+=(php-fpm-mailcow nginx-mailcow)
[[ "$DOVECOT_CHANGED" == 1 ]] && SERVICES_TO_RESTART+=(dovecot-mailcow)
[[ "$POSTFIX_CHANGED" == 1 ]] && SERVICES_TO_RESTART+=(postfix-mailcow)
[[ "$PERMS_CHANGED"   == 1 ]] && SERVICES_TO_RESTART+=(php-fpm-mailcow nginx-mailcow)

# dedupe
if [[ ${#SERVICES_TO_RESTART[@]} -gt 0 ]]; then
    UNIQUE=($(printf '%s\n' "${SERVICES_TO_RESTART[@]}" | sort -u))
    warn "Restarting: ${UNIQUE[*]}"
    run "docker compose restart ${UNIQUE[*]}"
else
    log "No restarts needed (nothing changed)"
fi

##############################################################################
# 5. SOGo race check
##############################################################################

if ! $DRY_RUN; then
    sleep 3
    SOGO_STATE=$(docker compose ps --format '{{.Name}}\t{{.State}}' | awk '/sogo-mailcow/ {print $2}')
    if [[ "$SOGO_STATE" != "running" ]]; then
        warn "sogo-mailcow state: $SOGO_STATE -- restarting (MySQL race fix)"
        docker compose restart sogo-mailcow
    else
        log "sogo-mailcow running"
    fi
fi

##############################################################################
# Summary
##############################################################################

echo
log "Post-update fixes complete"
if ! $DRY_RUN; then
    echo
    NOT_RUNNING=$(docker compose ps --format '{{.Name}}\t{{.State}}\t{{.Status}}' | awk '$2!="running"')
    TOTAL=$(docker compose ps --format '{{.Name}}' | wc -l)
    if [[ -z "$NOT_RUNNING" ]]; then
        log "All $TOTAL containers running"
    else
        err "Containers not running:"
        echo "$NOT_RUNNING"
    fi
fi
