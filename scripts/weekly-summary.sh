#!/bin/bash
# weekly-summary.sh -- Send weekly server health summary email (HTML)
# Runs via cron every Sunday at 08:00

set -euo pipefail

ALERT_EMAIL="micke@nysattra.se"
FROM_NAME="VPS Weekly Summary"
HOSTNAME=$(hostname)
DATE=$(date '+%Y-%m-%d')
WEEK_AGO=$(date -d '7 days ago' '+%Y-%m-%d %H:%M:%S')

EXPECTED_CONTAINERS=21
BACKUP_SERVICES="credentials nginx mailcow-directory mailcow server-manager monitoring-stack"
BACKUP_LOG_DIR="/opt/server-manager/logs"
CERT_DIR="/root/nginx/letsencrypt/live"
STALE_HOURS=48

# ── HTML helpers ──────────────────────────────────────────────────

status_class() {
    case "$1" in
        OK)                          echo "ok" ;;
        STALE|"RENEW SOON")         echo "warn" ;;
        EXPIRING|DEGRADED*|NONE|"NO LOG") echo "error" ;;
        *)                           echo "" ;;
    esac
}

html_kv_row() {
    local label="$1" value="$2" class="${3:-}"
    if [ -n "$class" ]; then
        echo "<tr><td class=\"label\">${label}</td><td class=\"value ${class}\">${value}</td></tr>"
    else
        echo "<tr><td class=\"label\">${label}</td><td class=\"value\">${value}</td></tr>"
    fi
}

# ── Section collectors ──────────────────────────────────────────────

collect_system() {
    local uptime_str load_1 load_5 load_15
    local mem_total mem_available mem_used mem_total_mb mem_pct
    local swap_total swap_free swap_line
    local disk_usage

    uptime_str=$(uptime -p)
    read -r load_1 load_5 load_15 _ _ < /proc/loadavg

    read -r mem_total mem_available <<< "$(awk '/MemTotal/{t=$2} /MemAvailable/{a=$2} END{print t, a}' /proc/meminfo)"
    mem_used=$(( (mem_total - mem_available) / 1024 ))
    mem_total_mb=$(( mem_total / 1024 ))
    mem_pct=$(( mem_available * 100 / mem_total ))

    read -r swap_total swap_free <<< "$(awk '/SwapTotal/{t=$2} /SwapFree/{f=$2} END{print t, f}' /proc/meminfo)"
    if [ "$swap_total" -gt 0 ]; then
        local swap_used swap_total_mb swap_pct
        swap_used=$(( (swap_total - swap_free) / 1024 ))
        swap_total_mb=$(( swap_total / 1024 ))
        swap_pct=$(( (swap_total - swap_free) * 100 / swap_total ))
        swap_line="${swap_used} MB / ${swap_total_mb} MB (${swap_pct}% used)"
    else
        swap_line="not configured"
    fi

    disk_usage=$(df -h / | awk 'NR==2{printf "%s used / %s total (%s)", $3, $2, $5}')

    SECTION_SYSTEM="<h2>System Health</h2>
<table>
$(html_kv_row 'Uptime' "$uptime_str")
$(html_kv_row 'Load' "${load_1} / ${load_5} / ${load_15} (1/5/15 min)")
$(html_kv_row 'RAM' "${mem_used} MB / ${mem_total_mb} MB (${mem_pct}% available)")
$(html_kv_row 'Swap' "$swap_line")
$(html_kv_row 'Disk /' "$disk_usage")
</table>"
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

    SECTION_SECURITY="<h2>Security</h2>
<table>
$(html_kv_row 'SSH failures (7d)' "$ssh_failures")
$(html_kv_row 'f2b sshd bans (7d)' "$sshd_bans_week")
$(html_kv_row 'Banned now (sshd)' "$sshd_banned_now")
$(html_kv_row 'Banned now (recid.)' "$recidive_banned_now")
$(html_kv_row 'Banned IPs' "$banned_ips")
</table>"
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

    SECTION_MAIL="<h2>Mail</h2>
<table>
$(html_kv_row 'Delivered (7d)' "$sent")
$(html_kv_row 'Bounced (7d)' "$bounced")
$(html_kv_row 'Rejected (7d)' "$rejected")
$(html_kv_row 'Queue' "${queue_count} messages")
$(html_kv_row 'Rspamd ham' "$ham_count")
$(html_kv_row 'Rspamd spam' "$spam_count")
</table>"
}

collect_backups() {
    local now_epoch rows=""
    now_epoch=$(date +%s)

    for service in $BACKUP_SERVICES; do
        local log_file="${BACKUP_LOG_DIR}/backup-${service}-cron.log"
        local last_success last_failure age_hours status

        if [ ! -f "$log_file" ]; then
            local cls
            cls=$(status_class "NO LOG")
            rows+="<tr><td>${service}</td><td>--</td><td>--</td><td class=\"${cls}\">NO LOG</td></tr>"
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
                status="STALE"
            else
                status="OK"
            fi

            local cls
            cls=$(status_class "$status")
            rows+="<tr><td>${service}</td><td>${last_success}</td><td>${age_hours}h</td><td class=\"${cls}\">${status}</td></tr>"
        else
            local cls
            cls=$(status_class "NONE")
            rows+="<tr><td>${service}</td><td>--</td><td>--</td><td class=\"${cls}\">NONE</td></tr>"
        fi

        if [ -n "$last_failure" ]; then
            rows+="<tr><td colspan=\"4\" style=\"font-size:11px;color:#999;padding-left:20px;\">Last failure: ${last_failure}</td></tr>"
        fi
    done

    SECTION_BACKUPS="<h2>Backups</h2>
<table>
<tr><th>Service</th><th>Last Success</th><th>Age</th><th>Status</th></tr>
${rows}
</table>"
}

collect_tls() {
    local rows=""

    if [ ! -d "$CERT_DIR" ]; then
        SECTION_TLS="<h2>TLS Certificates</h2>
<table>
<tr><td>Certificate directory not found</td></tr>
</table>"
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

        local cls
        cls=$(status_class "$status")
        rows+="<tr><td>${cn}</td><td>${days_left} days</td><td class=\"${cls}\">${status}</td></tr>"
    done

    if [ -z "$rows" ]; then
        rows="<tr><td colspan=\"3\">No certificates found</td></tr>"
    fi

    SECTION_TLS="<h2>TLS Certificates</h2>
<table>
<tr><th>Domain</th><th>Expires</th><th>Status</th></tr>
${rows}
</table>"
}

collect_docker() {
    local running restart_rows=""

    running=$(docker ps -q 2>/dev/null | wc -l)

    local status
    if [ "$running" -eq "$EXPECTED_CONTAINERS" ]; then
        status="OK"
    elif [ "$running" -lt "$EXPECTED_CONTAINERS" ]; then
        status="DEGRADED ($(( EXPECTED_CONTAINERS - running )) missing)"
    else
        status="UNEXPECTED (more than expected)"
    fi

    local cls
    cls=$(status_class "$status")

    # Check for containers with restart counts > 0
    local restarts
    restarts=$(docker ps -q 2>/dev/null | xargs -r docker inspect --format '{{.Name}} {{.RestartCount}}' 2>/dev/null \
        | awk '$2 > 0' || echo "")

    if [ -n "$restarts" ]; then
        restart_rows="<h2>Container Restarts</h2>
<table>
<tr><th>Container</th><th>Restarts</th></tr>"
        while read -r name count; do
            restart_rows+="<tr><td>${name}</td><td>${count}</td></tr>"
        done <<< "$restarts"
        restart_rows+="
</table>"
    fi

    SECTION_DOCKER="<h2>Docker</h2>
<table>
$(html_kv_row 'Containers' "${running} / ${EXPECTED_CONTAINERS}" "$cls")
$(html_kv_row 'Status' "$status" "$cls")
</table>
${restart_rows}"
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
MIME-Version: 1.0
Content-Type: text/html; charset=utf-8

<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; background: #f5f5f5; margin: 0; padding: 20px; }
.container { max-width: 640px; margin: 0 auto; background: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
.header { background: #2c3e50; color: #ffffff; padding: 16px 20px; }
.header h1 { margin: 0; font-size: 18px; font-weight: 600; }
.header p { margin: 4px 0 0; font-size: 13px; opacity: 0.8; }
.content { padding: 0 20px 20px; }
h2 { background: #2c3e50; color: #ffffff; padding: 8px 14px; margin: 20px -20px 0; font-size: 14px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
td, th { padding: 7px 10px; border-bottom: 1px solid #eee; text-align: left; }
td.label { width: 40%; color: #555; }
td.value { font-weight: 500; }
th { background: #f8f9fa; text-transform: uppercase; font-size: 12px; color: #666; font-weight: 600; letter-spacing: 0.3px; }
.ok { color: #27ae60; font-weight: 600; }
.warn { color: #e67e22; font-weight: 600; }
.error { color: #e74c3c; font-weight: 600; }
.footer { padding: 14px 20px; font-size: 11px; color: #999; border-top: 1px solid #eee; text-align: center; }
</style>
</head>
<body>
<div class="container">
<div class="header">
<h1>Weekly Health Report</h1>
<p>${HOSTNAME} &mdash; ${DATE}</p>
</div>
<div class="content">
${SECTION_SYSTEM}
${SECTION_SECURITY}
${SECTION_MAIL}
${SECTION_BACKUPS}
${SECTION_TLS}
${SECTION_DOCKER}
</div>
<div class="footer">
Weekly health summary from ${HOSTNAME}<br>
Generated at $(date '+%Y-%m-%d %H:%M:%S')
</div>
</div>
</body>
</html>
EOF

logger -t weekly-summary "Weekly health summary sent to ${ALERT_EMAIL}"
