#!/bin/bash
# weekly-summary.sh -- Send weekly server health summary email
# Runs via cron every Sunday at 08:00

set -euo pipefail

ALERT_EMAIL="micke@nysattra.se"
FROM_NAME="VPS Weekly Summary"
HOSTNAME=$(hostname)
DATE=$(date '+%Y-%m-%d')
WEEK_AGO=$(date -d '7 days ago' '+%Y-%m-%d %H:%M:%S')

EXPECTED_CONTAINERS=20
BACKUP_SERVICES="credentials nginx mailcow-directory mailcow server-manager monitoring-stack"
BACKUP_LOG_DIR="/opt/server-manager/logs"
CERT_DIR="/root/nginx/letsencrypt/live"
STALE_HOURS=48

# ── Section collectors ──────────────────────────────────────────────

collect_system() {
    local uptime_str load_1 load_5 load_15
    local mem_total mem_available mem_used swap_total swap_free swap_used
    local disk_usage

    uptime_str=$(uptime -p)
    read -r load_1 load_5 load_15 _ _ < /proc/loadavg

    read -r mem_total mem_available <<< "$(awk '/MemTotal/{t=$2} /MemAvailable/{a=$2} END{print t, a}' /proc/meminfo)"
    mem_used=$(( (mem_total - mem_available) / 1024 ))
    mem_total_mb=$(( mem_total / 1024 ))
    mem_pct=$(( mem_available * 100 / mem_total ))

    read -r swap_total swap_free <<< "$(awk '/SwapTotal/{t=$2} /SwapFree/{f=$2} END{print t, f}' /proc/meminfo)"
    if [ "$swap_total" -gt 0 ]; then
        swap_used=$(( (swap_total - swap_free) / 1024 ))
        swap_total_mb=$(( swap_total / 1024 ))
        swap_pct=$(( (swap_total - swap_free) * 100 / swap_total ))
        swap_line="Swap:     ${swap_used} MB / ${swap_total_mb} MB (${swap_pct}% used)"
    else
        swap_line="Swap:     not configured"
    fi

    disk_usage=$(df -h / | awk 'NR==2{printf "%s used / %s total (%s)", $3, $2, $5}')

    SECTION_SYSTEM=$(cat <<EOF
SYSTEM HEALTH
  Uptime:   ${uptime_str}
  Load:     ${load_1} / ${load_5} / ${load_15} (1/5/15 min)
  RAM:      ${mem_used} MB / ${mem_total_mb} MB (${mem_pct}% available)
  ${swap_line}
  Disk /:   ${disk_usage}
EOF
)
}

collect_security() {
    local sshd_status recidive_status
    local sshd_banned_now recidive_banned_now
    local sshd_bans_week ssh_failures

    # Current fail2ban state
    sshd_status=$(fail2ban-client status sshd 2>/dev/null || echo "unavailable")
    recidive_status=$(fail2ban-client status recidive 2>/dev/null || echo "unavailable")

    sshd_banned_now=$(echo "$sshd_status" | grep -oP 'Currently banned:\s+\K\d+' || echo "0")
    recidive_banned_now=$(echo "$recidive_status" | grep -oP 'Currently banned:\s+\K\d+' || echo "0")

    # Weekly ban counts from log
    sshd_bans_week=$(awk -v since="$WEEK_AGO" '$0 >= since && /\[sshd\].*Ban/' /var/log/fail2ban.log 2>/dev/null | wc -l)

    # SSH failed login attempts this week
    ssh_failures=$(journalctl _COMM=sshd --since "$WEEK_AGO" --no-pager 2>/dev/null | grep -c "Failed password\|Invalid user\|authentication failure" || true)

    # Currently banned IPs (sshd)
    local banned_ips
    banned_ips=$(echo "$sshd_status" | grep -oP 'Banned IP list:\s+\K.*' || echo "none")
    if [ -z "$banned_ips" ]; then
        banned_ips="none"
    fi

    SECTION_SECURITY=$(cat <<EOF
SECURITY
  SSH failed attempts (7d):    ${ssh_failures}
  fail2ban sshd bans (7d):     ${sshd_bans_week}
  Currently banned (sshd):     ${sshd_banned_now}
  Currently banned (recidive): ${recidive_banned_now}
  Banned IPs:                  ${banned_ips}
EOF
)
}

collect_mail() {
    local sent bounced rejected queue_count
    local spam_count ham_count

    # Postfix stats from docker logs (last 7 days = 168h)
    local postfix_logs
    postfix_logs=$(docker logs mailcowdockerized-postfix-mailcow-1 --since 168h 2>&1 || echo "")

    sent=$(echo "$postfix_logs" | grep -c 'status=sent' || true)
    bounced=$(echo "$postfix_logs" | grep -c 'status=bounced' || true)
    rejected=$(echo "$postfix_logs" | grep -c 'NOQUEUE: reject' || true)

    # Mail queue
    queue_count=$(docker exec mailcowdockerized-postfix-mailcow-1 mailq 2>/dev/null | tail -1 | grep -oP '\d+(?= Request)' || echo "0")
    if [ -z "$queue_count" ]; then
        queue_count="0"
    fi

    # Rspamd stats
    local rspamd_stats
    rspamd_stats=$(docker exec mailcowdockerized-rspamd-mailcow-1 wget -qO- http://localhost:11334/stat 2>/dev/null || echo "")
    if [ -n "$rspamd_stats" ]; then
        spam_count=$(echo "$rspamd_stats" | grep -oP '"spam_count":\s*\K\d+' || echo "n/a")
        ham_count=$(echo "$rspamd_stats" | grep -oP '"ham_count":\s*\K\d+' || echo "n/a")
    else
        spam_count="n/a"
        ham_count="n/a"
    fi

    SECTION_MAIL=$(cat <<EOF
MAIL
  Delivered (7d):  ${sent}
  Bounced (7d):    ${bounced}
  Rejected (7d):   ${rejected}
  Queue:           ${queue_count} messages
  Rspamd ham:      ${ham_count}
  Rspamd spam:     ${spam_count}
EOF
)
}

collect_backups() {
    local lines=""
    local now_epoch
    now_epoch=$(date +%s)

    for service in $BACKUP_SERVICES; do
        local log_file="${BACKUP_LOG_DIR}/backup-${service}-cron.log"
        local last_success last_failure age_hours status

        if [ ! -f "$log_file" ]; then
            lines+="  ${service}: NO LOG FILE"$'\n'
            continue
        fi

        # Last success timestamp
        last_success=$(grep 'Backup completed successfully' "$log_file" | tail -1 | grep -oP '^\[\K[0-9-]+ [0-9:]+' || echo "")
        # Last failure timestamp
        last_failure=$(grep 'Backup failed' "$log_file" | tail -1 | grep -oP '^\[\K[0-9-]+ [0-9:]+' || echo "")

        if [ -n "$last_success" ]; then
            local success_epoch
            success_epoch=$(date -d "$last_success" +%s 2>/dev/null || echo "0")
            age_hours=$(( (now_epoch - success_epoch) / 3600 ))

            if [ "$age_hours" -ge "$STALE_HOURS" ]; then
                status="STALE (${age_hours}h ago)"
            else
                status="OK (${age_hours}h ago)"
            fi

            lines+="$(printf "  %-22s %s  %s" "${service}:" "${last_success}" "${status}")"$'\n'
        else
            lines+="  ${service}: NO SUCCESSFUL BACKUP FOUND"$'\n'
        fi

        if [ -n "$last_failure" ]; then
            lines+="    Last failure: ${last_failure}"$'\n'
        fi
    done

    # Remove trailing newline
    SECTION_BACKUPS="BACKUPS"$'\n'"${lines%$'\n'}"
}

collect_tls() {
    local lines=""

    if [ ! -d "$CERT_DIR" ]; then
        SECTION_TLS="TLS CERTIFICATES"$'\n'"  Certificate directory not found"
        return
    fi

    local now_epoch
    now_epoch=$(date +%s)

    for cert_path in "$CERT_DIR"/npm-*/cert.pem; do
        [ -f "$cert_path" ] || continue

        local cn expiry_str expiry_epoch days_left status

        cn=$(openssl x509 -in "$cert_path" -noout -subject 2>/dev/null | sed 's/.*CN = //')
        expiry_str=$(openssl x509 -in "$cert_path" -noout -enddate 2>/dev/null | sed 's/notAfter=//')
        expiry_epoch=$(date -d "$expiry_str" +%s 2>/dev/null || echo "0")
        days_left=$(( (expiry_epoch - now_epoch) / 86400 ))

        if [ "$days_left" -lt 7 ]; then
            status="EXPIRING"
        elif [ "$days_left" -lt 14 ]; then
            status="RENEW SOON"
        else
            status="OK"
        fi

        lines+="$(printf "  %-35s %3d days  %s" "$cn" "$days_left" "$status")"$'\n'
    done

    if [ -z "$lines" ]; then
        lines="  No certificates found"$'\n'
    fi

    # Remove trailing newline
    SECTION_TLS="TLS CERTIFICATES"$'\n'"${lines%$'\n'}"
}

collect_docker() {
    local running restart_info=""

    running=$(docker ps -q 2>/dev/null | wc -l)

    local status
    if [ "$running" -eq "$EXPECTED_CONTAINERS" ]; then
        status="OK"
    elif [ "$running" -lt "$EXPECTED_CONTAINERS" ]; then
        status="DEGRADED ($(( EXPECTED_CONTAINERS - running )) missing)"
    else
        status="UNEXPECTED (more than expected)"
    fi

    # Check for containers with restart counts > 0
    local restarts
    restarts=$(docker ps -q 2>/dev/null | xargs -r docker inspect --format '{{.Name}} {{.RestartCount}}' 2>/dev/null | awk '$2 > 0 {printf "  %-40s restarts: %s\n", $1, $2}' || echo "")

    if [ -n "$restarts" ]; then
        restart_info="\n${restarts}"
    fi

    SECTION_DOCKER=$(cat <<EOF
DOCKER
  Running: ${running} / ${EXPECTED_CONTAINERS} — ${status}${restart_info}
EOF
)
}

# ── Main ────────────────────────────────────────────────────────────

collect_system
collect_security
collect_mail
collect_backups
collect_tls
collect_docker

msmtp -t <<EOF
To: ${ALERT_EMAIL}
From: ${FROM_NAME} <root@villaherrgard.com>
Subject: [VPS Summary] Weekly Health Report — ${HOSTNAME} (${DATE})

${SECTION_SYSTEM}

${SECTION_SECURITY}

${SECTION_MAIL}

${SECTION_BACKUPS}

${SECTION_TLS}

${SECTION_DOCKER}

--
Weekly health summary from ${HOSTNAME}
Generated at $(date '+%Y-%m-%d %H:%M:%S')
EOF

logger -t weekly-summary "Weekly health summary sent to ${ALERT_EMAIL}"
