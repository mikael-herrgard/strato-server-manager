#!/bin/bash
# motd-status.sh -- login status screen
#
# Symlinked from /etc/update-motd.d/50-server-manager so pam_motd renders
# it on interactive SSH login; also runnable any time via the `status`
# alias. Two-column layout mimicking Ubuntu's landscape-sysinfo block.
# Quiet when everything is OK; problems get detail lines below the grid.
#
# Rules (this runs during login):
#   - local checks only, no network probes (weekly summary covers those)
#   - every external command is timeboxed and failure-tolerant: a broken
#     probe renders as a warning value, it never hangs or breaks the login
#   - deliberately NOT set -e: wrong info here is bad, blocking a login
#     (possibly the login needed to fix the problem) is worse
set -uo pipefail

# Paths (env-overridable for testing)
LOG_DIR="${MOTD_LOG_DIR:-/opt/server-manager/logs}"
SPOOL_DIR="${MOTD_SPOOL_DIR:-/opt/server-manager/state/failed-notifications}"
REBOOT_FLAG="${MOTD_REBOOT_FLAG:-/var/run/reboot-required}"
CERT_DIR="${MOTD_CERT_DIR:-/root/nginx/letsencrypt/live}"
EXPECTED_CONTAINERS="${MOTD_EXPECTED_CONTAINERS:-21}"
BACKUP_SERVICES="credentials nginx mailcow-directory mailcow server-manager monitoring-stack"
STALE_HOURS=48

# Colors (respect NO_COLOR)
if [ -n "${NO_COLOR:-}" ]; then
    G='' Y='' R='' D='' N=''
else
    G=$'\e[32m' Y=$'\e[33m' R=$'\e[31m' D=$'\e[2m' N=$'\e[0m'
fi

NOW=$(date +%s)

# Detail lines rendered below the grid (problems only)
DETAILS=()

# ── helpers ─────────────────────────────────────────────────────────

age_h() { echo $(( (NOW - $1) / 3600 )); }

# last_log_epoch <file> <pattern> -> epoch of last matching line's [ts], or ""
last_log_epoch() {
    local ts
    ts=$(tail -n 300 "$1" 2>/dev/null | grep "$2" | tail -1 \
        | grep -oP '^\[\K[0-9-]+ [0-9:]+' || true)
    [ -n "$ts" ] && date -d "$ts" +%s 2>/dev/null || true
}

# cell <label> <value> <color> <label_width> <value_width>
# ANSI codes confuse printf's %-Ns padding, so pad the plain value first,
# then colorize the padded string.
cell() {
    local label="$1" value="$2" color="$3" lw="$4" vw="$5" padded
    padded=$(printf '%-*s' "$vw" "$value")
    printf '%-*s%s%s%s' "$lw" "${label}:" "$color" "$padded" "${color:+$N}"
}

# ── left column: system ─────────────────────────────────────────────

read -r l1 l5 l15 _ _ < /proc/loadavg || { l1=?; l5=?; l15=?; }
load_val="$l1 $l5 $l15"

read -r disk_pct disk_size <<< "$(df -h --output=pcent,size / 2>/dev/null | tail -1)" || true
disk_pct_n=$(echo "${disk_pct:-}" | tr -dc '0-9')
if [ -n "${disk_pct_n:-}" ]; then
    disk_val="${disk_pct# } of ${disk_size# }"
    if   [ "$disk_pct_n" -gt 85 ]; then disk_col=$R
    elif [ "$disk_pct_n" -gt 75 ]; then disk_col=$Y
    else disk_col=''; fi
else
    disk_val="?"; disk_col=$Y
fi

mem_total=0 mem_avail=0
read -r mem_total mem_avail <<< "$(awk '/MemTotal/{t=$2} /MemAvailable/{a=$2} END{print t, a}' /proc/meminfo)" || true
if [ "${mem_total:-0}" -gt 0 ]; then
    avail_pct=$(( mem_avail * 100 / mem_total ))
    mem_val="$(( 100 - avail_pct ))% used"
    if   [ "$avail_pct" -lt 15 ]; then mem_col=$R
    elif [ "$avail_pct" -lt 25 ]; then mem_col=$Y
    else mem_col=''; fi
else
    mem_val="?"; mem_col=$Y
fi

swap_total=0 swap_free=0
read -r swap_total swap_free <<< "$(awk '/SwapTotal/{t=$2} /SwapFree/{f=$2} END{print t, f}' /proc/meminfo)" || true
if [ "${swap_total:-0}" -gt 0 ]; then
    swap_pct=$(( (swap_total - swap_free) * 100 / swap_total ))
    swap_val="${swap_pct}% used"
    if   [ "$swap_pct" -gt 50 ]; then swap_col=$R
    elif [ "$swap_pct" -gt 25 ]; then swap_col=$Y
    else swap_col=''; fi
else
    swap_val="none"; swap_col=$Y
fi

up_val=$(uptime -p 2>/dev/null | sed 's/^up //; s/ minutes\?/ min/; s/ hours\?/h/; s/ days\?/d/') || up_val="?"
proc_val=$(ps ax --no-heading 2>/dev/null | wc -l) || proc_val="?"

# ── right column: services ──────────────────────────────────────────

if cids=$(timeout 3 docker ps -q 2>/dev/null); then
    running=$(echo "$cids" | grep -c . || true)
    if [ "$running" -eq "$EXPECTED_CONTAINERS" ]; then
        docker_val="${running}/${EXPECTED_CONTAINERS} running"; docker_col=$G
    else
        docker_val="${running}/${EXPECTED_CONTAINERS} ($(( EXPECTED_CONTAINERS - running )) missing)"; docker_col=$R
    fi
    restarts=$(echo "$cids" | xargs -r timeout 5 docker inspect \
        --format '{{.Name}} {{.RestartCount}}' 2>/dev/null \
        | awk '$2 > 0 {gsub("^/","",$1); printf "%s(%s×) ", $1, $2}' || true)
    if [ -n "${restarts:-}" ]; then
        DETAILS+=("${Y}⚠ Containers restarted: ${restarts}${N}")
    fi
else
    docker_val="daemon unreachable"; docker_col=$R
fi

problems=() ok_count=0 oldest_h=0
for svc in $BACKUP_SERVICES; do
    log_file="${LOG_DIR}/backup-${svc}-cron.log"
    if [ ! -f "$log_file" ]; then
        problems+=("${svc}: no log")
        continue
    fi
    ok_epoch=$(last_log_epoch "$log_file" 'Backup completed successfully')
    fail_epoch=$(last_log_epoch "$log_file" 'Backup failed')

    if [ -n "$fail_epoch" ] && { [ -z "$ok_epoch" ] || [ "$fail_epoch" -gt "$ok_epoch" ]; }; then
        problems+=("${svc}: FAILED $(date -d "@$fail_epoch" '+%b %d %H:%M')")
    elif [ -z "$ok_epoch" ]; then
        problems+=("${svc}: never succeeded")
    else
        h=$(age_h "$ok_epoch")
        if [ "$h" -ge "$STALE_HOURS" ]; then
            problems+=("${svc}: stale (${h}h)")
        else
            ok_count=$(( ok_count + 1 ))
            [ "$h" -gt "$oldest_h" ] && oldest_h=$h
        fi
    fi
done
if [ ${#problems[@]} -eq 0 ]; then
    backup_val="all ${ok_count} OK (oldest ${oldest_h}h)"; backup_col=$G
else
    backup_val="${#problems[@]} problem(s)!"; backup_col=$R
    for p in "${problems[@]}"; do
        DETAILS+=("${R}✗ Backup ${p}${N}")
    done
fi

borg_log="${LOG_DIR}/borg-check-cron.log"
if [ ! -f "$borg_log" ]; then
    borg_val="pending"; borg_col=$D
else
    pass_epoch=$(last_log_epoch "$borg_log" 'All repository checks passed')
    bfail_epoch=$(last_log_epoch "$borg_log" 'Repository check FAILED')
    if [ -n "$bfail_epoch" ] && { [ -z "$pass_epoch" ] || [ "$bfail_epoch" -gt "$pass_epoch" ]; }; then
        borg_val="FAILED $(date -d "@$bfail_epoch" '+%b %d')"; borg_col=$R
    elif [ -n "$pass_epoch" ]; then
        if [ "$(age_h "$pass_epoch")" -gt $(( 35 * 24 )) ]; then
            borg_val="overdue (last $(date -d "@$pass_epoch" '+%b %d'))"; borg_col=$Y
        else
            borg_val="OK $(date -d "@$pass_epoch" '+%b %d')"; borg_col=$G
        fi
    else
        borg_val="?"; borg_col=$Y
    fi
fi

min_days=999999 overdue=0
for cert in "$CERT_DIR"/npm-*/cert.pem; do
    [ -f "$cert" ] || continue
    na=$(openssl x509 -in "$cert" -noout -enddate 2>/dev/null | sed 's/notAfter=//')
    nb=$(openssl x509 -in "$cert" -noout -startdate 2>/dev/null | sed 's/notBefore=//')
    na_e=$(date -d "$na" +%s 2>/dev/null || echo 0)
    nb_e=$(date -d "$nb" +%s 2>/dev/null || echo 0)
    days=$(( (na_e - NOW) / 86400 ))
    age_d=$(( (NOW - nb_e) / 86400 ))
    [ "$days" -lt "$min_days" ] && min_days=$days
    if [ "$days" -le 25 ] && [ "$age_d" -gt 65 ]; then overdue=1; fi
done
if [ "$min_days" -eq 999999 ]; then
    tls_val="no certs found!"; tls_col=$R
elif [ "$min_days" -lt 7 ]; then
    tls_val="${min_days} days left!"; tls_col=$R
elif [ "$overdue" -eq 1 ]; then
    tls_val="${min_days} days (renewal overdue)"; tls_col=$Y
else
    tls_val="${min_days} days left"; tls_col=$G
fi

if mailq_out=$(timeout 3 docker exec mailcowdockerized-postfix-mailcow-1 mailq 2>/dev/null); then
    q=$(echo "$mailq_out" | tail -1 | grep -oP '\d+(?= Request)' || echo 0)
    if [ "$q" -gt 0 ]; then
        queue_val="${q} message(s)!"; queue_col=$Y
    else
        queue_val="0 messages"; queue_col=$G
    fi
else
    queue_val="unreachable"; queue_col=$Y
fi

banned=$(timeout 3 fail2ban-client status sshd 2>/dev/null \
    | grep -oP 'Currently banned:\s+\K\d+' || true)
if [ -n "${banned:-}" ]; then
    f2b_val="${banned} banned"; f2b_col=''
else
    f2b_val="unavailable"; f2b_col=$Y
fi

# ── urgent flags (detail lines) ─────────────────────────────────────

# Undelivered notifications: emails that failed BOTH delivery paths were
# spooled here by lib/notifications.py -- you never saw them, so login is
# the moment to say so.
lost=$(find "$SPOOL_DIR" -name '*.eml' 2>/dev/null | wc -l)
if [ "${lost:-0}" -gt 0 ]; then
    DETAILS+=("${R}✗ LOST ALERTS: ${lost} undelivered notification(s) in ${SPOOL_DIR}${N}")
fi

if [ -f "$REBOOT_FLAG" ]; then
    pkgs=$(tr '\n' ' ' < "${REBOOT_FLAG}.pkgs" 2>/dev/null | sed 's/ *$//' || true)
    DETAILS+=("${Y}⚠ Reboot required${pkgs:+ ($pkgs)}${N}")
fi

failed_units=$(systemctl --failed --no-legend --plain 2>/dev/null | awk '{print $1}' | tr '\n' ' ')
if [ -n "${failed_units// /}" ]; then
    DETAILS+=("${R}✗ Failed units: ${failed_units}${N}")
fi

# ── render ──────────────────────────────────────────────────────────

# Column widths: label / value / label (right value unpadded)
LW=15; VW=18; RW=13

printf ' Server status as of %s\n\n' "$(date)"

printf '  %s %s\n' "$(cell 'System load'  "$load_val" ''         $LW $VW)" "$(cell 'Docker'     "$docker_val" "$docker_col" $RW 0)"
printf '  %s %s\n' "$(cell 'Usage of /'   "$disk_val" "$disk_col" $LW $VW)" "$(cell 'Backups'    "$backup_val" "$backup_col" $RW 0)"
printf '  %s %s\n' "$(cell 'Memory usage' "$mem_val"  "$mem_col"  $LW $VW)" "$(cell 'Borg check' "$borg_val"   "$borg_col"   $RW 0)"
printf '  %s %s\n' "$(cell 'Swap usage'   "$swap_val" "$swap_col" $LW $VW)" "$(cell 'TLS cert'   "$tls_val"    "$tls_col"    $RW 0)"
printf '  %s %s\n' "$(cell 'Uptime'       "$up_val"   ''          $LW $VW)" "$(cell 'Mail queue' "$queue_val"  "$queue_col"  $RW 0)"
printf '  %s %s\n' "$(cell 'Processes'    "$proc_val" ''          $LW $VW)" "$(cell 'fail2ban'   "$f2b_val"    "$f2b_col"    $RW 0)"

if [ ${#DETAILS[@]} -gt 0 ]; then
    printf '\n'
    for d in "${DETAILS[@]}"; do
        printf '  %b\n' "$d"
    done
fi

exit 0
