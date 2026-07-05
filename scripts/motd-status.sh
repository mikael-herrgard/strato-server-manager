#!/bin/bash
# motd-status.sh -- login status screen
#
# Symlinked from /etc/update-motd.d/50-server-manager so pam_motd renders
# it on interactive SSH login; also runnable any time via the `status`
# alias. Prints a compact health summary: quiet when everything is OK,
# expands detail only for problems.
#
# Rules (this runs during login):
#   - local checks only, no network probes (weekly summary covers those)
#   - every external command is timeboxed and failure-tolerant: a broken
#     probe renders as a warning line, it never hangs or breaks the login
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
    G='' Y='' R='' B='' D='' N=''
else
    G=$'\e[32m' Y=$'\e[33m' R=$'\e[31m' B=$'\e[1m' D=$'\e[2m' N=$'\e[0m'
fi

NOW=$(date +%s)

# ── helpers ─────────────────────────────────────────────────────────

# age_h <epoch> -> hours since
age_h() { echo $(( (NOW - $1) / 3600 )); }

# last_log_epoch <file> <pattern> -> epoch of last matching line's [ts], or ""
last_log_epoch() {
    local ts
    ts=$(tail -n 300 "$1" 2>/dev/null | grep "$2" | tail -1 \
        | grep -oP '^\[\K[0-9-]+ [0-9:]+' || true)
    [ -n "$ts" ] && date -d "$ts" +%s 2>/dev/null || true
}

# ── header ──────────────────────────────────────────────────────────

up=$(uptime -p 2>/dev/null | sed 's/^up //') || up="?"
read -r l1 l5 l15 _ _ < /proc/loadavg || { l1=?; l5=?; l15=?; }
printf '%s── %s ─ up %s ─ load %s %s %s ─ %s ──%s\n' \
    "$D" "$(hostname)" "$up" "$l1" "$l5" "$l15" "$(date '+%Y-%m-%d %H:%M')" "$N"

# ── urgent flags (only render when present) ─────────────────────────

# Undelivered notifications: emails that failed BOTH delivery paths were
# spooled here by lib/notifications.py -- you never saw them, so login is
# the moment to say so.
lost=$(find "$SPOOL_DIR" -name '*.eml' 2>/dev/null | wc -l)
if [ "${lost:-0}" -gt 0 ]; then
    printf ' %s✗ LOST ALERTS: %s undelivered notification(s) in %s%s\n' \
        "$R" "$lost" "$SPOOL_DIR" "$N"
fi

if [ -f "$REBOOT_FLAG" ]; then
    pkgs=$(tr '\n' ' ' < "${REBOOT_FLAG}.pkgs" 2>/dev/null | sed 's/ *$//' || true)
    printf ' %s⚠ Reboot required%s%s\n' "$Y" "${pkgs:+ ($pkgs)}" "$N"
fi

failed_units=$(systemctl --failed --no-legend --plain 2>/dev/null | awk '{print $1}' | tr '\n' ' ')
if [ -n "${failed_units// /}" ]; then
    printf ' %s✗ Failed units: %s%s\n' "$R" "$failed_units" "$N"
fi

# ── resources ───────────────────────────────────────────────────────

mem_total=0 mem_avail=0
read -r mem_total mem_avail <<< "$(awk '/MemTotal/{t=$2} /MemAvailable/{a=$2} END{print t, a}' /proc/meminfo)" || true
if [ "${mem_total:-0}" -gt 0 ]; then
    avail_pct=$(( mem_avail * 100 / mem_total ))
    used_g=$(awk "BEGIN{printf \"%.1f\", ($mem_total-$mem_avail)/1048576}")
    total_g=$(awk "BEGIN{printf \"%.1f\", $mem_total/1048576}")
    if   [ "$avail_pct" -lt 15 ]; then mem_c=$R
    elif [ "$avail_pct" -lt 25 ]; then mem_c=$Y
    else mem_c=$G; fi
    mem_str="${mem_c}${used_g}G/${total_g}G used (${avail_pct}% avail)${N}"
else
    mem_str="${Y}RAM ?${N}"
fi

swap_total=0 swap_free=0
read -r swap_total swap_free <<< "$(awk '/SwapTotal/{t=$2} /SwapFree/{f=$2} END{print t, f}' /proc/meminfo)" || true
if [ "${swap_total:-0}" -gt 0 ]; then
    swap_pct=$(( (swap_total - swap_free) * 100 / swap_total ))
    if   [ "$swap_pct" -gt 50 ]; then swap_c=$R
    elif [ "$swap_pct" -gt 25 ]; then swap_c=$Y
    else swap_c=$G; fi
    swap_str="${swap_c}Swap ${swap_pct}%${N}"
else
    swap_str="${Y}Swap none${N}"
fi

disk_pct=$(df --output=pcent / 2>/dev/null | tail -1 | tr -dc '0-9')
if [ -n "${disk_pct:-}" ]; then
    if   [ "$disk_pct" -gt 85 ]; then disk_c=$R
    elif [ "$disk_pct" -gt 75 ]; then disk_c=$Y
    else disk_c=$G; fi
    disk_str="${disk_c}Disk / ${disk_pct}%${N}"
else
    disk_str="${Y}Disk ?${N}"
fi

printf ' %-9s %s  ·  %s  ·  %s\n' "RAM" "$mem_str" "$swap_str" "$disk_str"

# ── docker ──────────────────────────────────────────────────────────

if cids=$(timeout 3 docker ps -q 2>/dev/null); then
    running=$(echo "$cids" | grep -c . || true)
    if [ "$running" -eq "$EXPECTED_CONTAINERS" ]; then
        docker_line="${G}${running}/${EXPECTED_CONTAINERS} running${N}"
    else
        docker_line="${R}${running}/${EXPECTED_CONTAINERS} running ($(( EXPECTED_CONTAINERS - running )) missing)${N}"
    fi
    restarts=$(echo "$cids" | xargs -r timeout 5 docker inspect \
        --format '{{.Name}} {{.RestartCount}}' 2>/dev/null \
        | awk '$2 > 0 {gsub("^/","",$1); printf "%s(%s×) ", $1, $2}' || true)
    if [ -n "${restarts:-}" ]; then
        docker_line="${docker_line}  ${Y}restarted: ${restarts}${N}"
    fi
else
    docker_line="${R}daemon unreachable${N}"
fi
printf ' %-9s %s\n' "Docker" "$docker_line"

# ── backups ─────────────────────────────────────────────────────────

problems=() ok_count=0 newest_h=999999 oldest_h=0
for svc in $BACKUP_SERVICES; do
    log_file="${LOG_DIR}/backup-${svc}-cron.log"
    if [ ! -f "$log_file" ]; then
        problems+=("${R}${svc}: no log${N}")
        continue
    fi
    ok_epoch=$(last_log_epoch "$log_file" 'Backup completed successfully')
    fail_epoch=$(last_log_epoch "$log_file" 'Backup failed')

    if [ -n "$fail_epoch" ] && { [ -z "$ok_epoch" ] || [ "$fail_epoch" -gt "$ok_epoch" ]; }; then
        problems+=("${R}${svc}: FAILED $(date -d "@$fail_epoch" '+%b %d %H:%M')${N}")
    elif [ -z "$ok_epoch" ]; then
        problems+=("${R}${svc}: never succeeded${N}")
    else
        h=$(age_h "$ok_epoch")
        if [ "$h" -ge "$STALE_HOURS" ]; then
            problems+=("${Y}${svc}: stale (${h}h)${N}")
        else
            ok_count=$(( ok_count + 1 ))
            [ "$h" -lt "$newest_h" ] && newest_h=$h
            [ "$h" -gt "$oldest_h" ] && oldest_h=$h
        fi
    fi
done

if [ ${#problems[@]} -eq 0 ]; then
    printf ' %-9s %sall %s OK%s %s(newest %sh, oldest %sh)%s\n' \
        "Backups" "$G" "$ok_count" "$N" "$D" "$newest_h" "$oldest_h" "$N"
else
    first=1
    for p in "${problems[@]}"; do
        if [ "$first" -eq 1 ]; then
            printf ' %-9s %s\n' "Backups" "$p"; first=0
        else
            printf ' %-9s %s\n' "" "$p"
        fi
    done
    [ "$ok_count" -gt 0 ] && printf ' %-9s %s%s other(s) OK%s\n' "" "$D" "$ok_count" "$N"
fi

# ── bottom line: borg check · TLS · fail2ban · mail queue ──────────

borg_log="${LOG_DIR}/borg-check-cron.log"
if [ ! -f "$borg_log" ]; then
    borg_str="${D}Borg-chk pending${N}"
else
    pass_epoch=$(last_log_epoch "$borg_log" 'All repository checks passed')
    fail_epoch=$(last_log_epoch "$borg_log" 'Repository check FAILED')
    if [ -n "$fail_epoch" ] && { [ -z "$pass_epoch" ] || [ "$fail_epoch" -gt "$pass_epoch" ]; }; then
        borg_str="${R}Borg-chk FAILED $(date -d "@$fail_epoch" '+%b %d')${N}"
    elif [ -n "$pass_epoch" ]; then
        if [ "$(age_h "$pass_epoch")" -gt $(( 35 * 24 )) ]; then
            borg_str="${Y}Borg-chk overdue (last $(date -d "@$pass_epoch" '+%b %d'))${N}"
        else
            borg_str="${G}Borg-chk OK $(date -d "@$pass_epoch" '+%b %d')${N}"
        fi
    else
        borg_str="${Y}Borg-chk ?${N}"
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
    tls_str="${R}TLS: no certs${N}"
elif [ "$min_days" -lt 7 ]; then
    tls_str="${R}TLS ${min_days}d!${N}"
elif [ "$overdue" -eq 1 ]; then
    tls_str="${Y}TLS ${min_days}d (renewal overdue)${N}"
else
    tls_str="${G}TLS ${min_days}d${N}"
fi

banned=$(timeout 3 fail2ban-client status sshd 2>/dev/null \
    | grep -oP 'Currently banned:\s+\K\d+' || true)
if [ -n "${banned:-}" ]; then
    f2b_str="${D}f2b ${banned} banned${N}"
else
    f2b_str="${Y}f2b unavailable${N}"
fi

if mailq_out=$(timeout 3 docker exec mailcowdockerized-postfix-mailcow-1 mailq 2>/dev/null); then
    q=$(echo "$mailq_out" | tail -1 | grep -oP '\d+(?= Request)' || echo 0)
    if [ "$q" -gt 0 ]; then
        queue_str="${Y}queue ${q}!${N}"
    else
        queue_str="${G}queue 0${N}"
    fi
else
    queue_str="${Y}queue ?${N}"
fi

printf ' %s  ·  %s  ·  %s  ·  %s\n' "$borg_str" "$tls_str" "$f2b_str" "$queue_str"

exit 0
