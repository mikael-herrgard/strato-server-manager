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
        STALE|"RENEW SOON"|"RENEWAL OVERDUE") echo "warn" ;;
        EXPIRING|DEGRADED*|NONE|"NO LOG"|MISMATCH|"NO DNSSEC"|UNREACHABLE) echo "error" ;;
        *)                           echo "" ;;
    esac
}

# Worst-case status across all sections; subject line picks up "ALERT" if any section sets this to "error"
OVERALL_STATUS="ok"
bump_status() {
    case "$1" in
        error) OVERALL_STATUS="error" ;;
        warn)  [ "$OVERALL_STATUS" = "ok" ] && OVERALL_STATUS="warn" ;;
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

# Populated by collect_tls(); consumed by collect_cert_renewal()
RENEWED_CERTS=()
RENEWAL_WINDOW_DAYS=7

collect_tls() {
    local rows=""

    if [ ! -d "$CERT_DIR" ]; then
        SECTION_TLS="<h2>TLS Certificates</h2>
<table>
<tr><td>Certificate directory not found</td></tr>
</table>"
        bump_status error
        return
    fi

    local now_epoch
    now_epoch=$(date +%s)

    for cert_path in "$CERT_DIR"/npm-*/cert.pem; do
        [ -f "$cert_path" ] || continue

        local cn not_after_str not_before_str
        local not_after_epoch not_before_epoch days_left age_days status display_after

        cn=$(openssl x509 -in "$cert_path" -noout -subject 2>/dev/null | sed 's/.*CN = //')
        not_after_str=$(openssl x509 -in "$cert_path" -noout -enddate 2>/dev/null | sed 's/notAfter=//')
        not_before_str=$(openssl x509 -in "$cert_path" -noout -startdate 2>/dev/null | sed 's/notBefore=//')
        not_after_epoch=$(date -d "$not_after_str" +%s 2>/dev/null || echo "0")
        not_before_epoch=$(date -d "$not_before_str" +%s 2>/dev/null || echo "0")
        days_left=$(( (not_after_epoch - now_epoch) / 86400 ))
        age_days=$(( (now_epoch - not_before_epoch) / 86400 ))
        display_after=$(date -d "$not_after_str" '+%Y-%m-%d' 2>/dev/null || echo "$not_after_str")

        # Status logic:
        # ≤ 7 days        -> EXPIRING (red)        regardless of age
        # ≤ 25 days, old  -> RENEWAL OVERDUE (orange)  cert >65d old, NPM should have renewed
        # ≤ 25 days, new  -> OK (green)            cert <=65d old, mid-cycle, no action
        # > 25 days       -> OK (green)
        if [ "$days_left" -lt 7 ]; then
            status="EXPIRING"
        elif [ "$days_left" -le 25 ] && [ "$age_days" -gt 65 ]; then
            status="RENEWAL OVERDUE"
        else
            status="OK"
        fi

        local cls
        cls=$(status_class "$status")
        bump_status "$cls"
        rows+="<tr><td>${cn}</td><td>${display_after}</td><td>${days_left} days</td><td class=\"${cls}\">${status}</td></tr>"

        # Track recent renewals for the conditional renewal-detail block
        if [ "$age_days" -lt "$RENEWAL_WINDOW_DAYS" ]; then
            RENEWED_CERTS+=("$cert_path")
        fi
    done

    if [ -z "$rows" ]; then
        rows="<tr><td colspan=\"4\">No certificates found</td></tr>"
        bump_status error
    fi

    SECTION_TLS="<h2>TLS Certificates</h2>
<table>
<tr><th>Domain</th><th>notAfter</th><th>Days left</th><th>Status</th></tr>
${rows}
</table>"
}

# DANE/TLSA. The MX cert and TLSA record are shared by all four mail domains
# (they all MX to mail.villaherrgard.com), so a single check covers everyone.
MX_HOST="mail.villaherrgard.com"

collect_dane() {
    local live_spki tlsa_raw tlsa_hash tlsa_ttl ad_flag
    local match_status match_cls dnssec_status dnssec_cls ttl_display

    live_spki=$(timeout 5 bash -c "echo | openssl s_client -connect ${MX_HOST}:25 -starttls smtp -servername ${MX_HOST} 2>/dev/null \
        | openssl x509 -noout -pubkey 2>/dev/null \
        | openssl pkey -pubin -outform DER 2>/dev/null | sha256sum | awk '{print \$1}'")

    if [ -z "$live_spki" ]; then
        live_spki="(unreachable)"
    fi

    # Published TLSA + TTL via authoritative resolver
    tlsa_raw=$(timeout 5 dig +short TLSA "_25._tcp.${MX_HOST}" @1.1.1.1 2>/dev/null | head -1)
    tlsa_hash=$(echo "$tlsa_raw" | awk '{$1=$2=$3=""; print tolower($0)}' | tr -d ' ')
    tlsa_ttl=$(timeout 5 dig +noall +answer TLSA "_25._tcp.${MX_HOST}" @1.1.1.1 2>/dev/null | awk '{print $2}' | head -1)
    ad_flag=$(timeout 5 dig +dnssec +adflag TLSA "_25._tcp.${MX_HOST}" @1.1.1.1 +noall +comments 2>/dev/null \
        | grep -oE "flags: [a-z ]+" | head -1)

    if [ -z "$tlsa_hash" ]; then
        match_status="UNREACHABLE"
        tlsa_hash="(no answer)"
    elif [ "$tlsa_hash" = "$live_spki" ]; then
        match_status="OK"
    else
        match_status="MISMATCH"
    fi
    match_cls=$(status_class "$match_status")
    bump_status "$match_cls"

    if echo "$ad_flag" | grep -q " ad"; then
        dnssec_status="OK"
    else
        dnssec_status="NO DNSSEC"
    fi
    dnssec_cls=$(status_class "$dnssec_status")
    bump_status "$dnssec_cls"

    ttl_display="${tlsa_ttl:-?}s"

    SECTION_DANE="<h2>DANE / TLSA (${MX_HOST})</h2>
<table>
$(html_kv_row 'Live cert SPKI (port 25)' "<code>${live_spki}</code>")
$(html_kv_row 'Published TLSA hash' "<code>${tlsa_hash}</code>")
$(html_kv_row 'Match' "$match_status" "$match_cls")
$(html_kv_row 'DNSSEC' "$dnssec_status" "$dnssec_cls")
$(html_kv_row 'TTL' "$ttl_display")
</table>"
}

# MTA-STS. Check the policy's mode + max_age + id for each mail domain.
MAIL_DOMAINS="villaherrgard.com nysattra.se villaherrgard.se"

collect_mtasts() {
    local rows=""

    for d in $MAIL_DOMAINS; do
        local policy mode max_age max_age_days policy_id status cls

        policy=$(timeout 5 curl -fsS --max-time 5 "https://mta-sts.${d}/.well-known/mta-sts.txt" 2>/dev/null || true)

        if [ -z "$policy" ]; then
            status="UNREACHABLE"
            cls=$(status_class "$status")
            bump_status "$cls"
            rows+="<tr><td>${d}</td><td>—</td><td>—</td><td>—</td><td class=\"${cls}\">${status}</td></tr>"
            continue
        fi

        mode=$(echo "$policy" | awk -F': *' '/^mode:/ {print $2}' | tr -d '\r')
        max_age=$(echo "$policy" | awk -F': *' '/^max_age:/ {print $2}' | tr -d '\r')
        max_age_days=$(( ${max_age:-0} / 86400 ))
        policy_id=$(timeout 5 dig +short TXT "_mta-sts.${d}" @1.1.1.1 2>/dev/null \
            | tr -d '"' | grep -oE 'id=[^;]+' | head -1 | sed 's/id=//')

        if [ "$mode" = "enforce" ]; then
            status="OK"
        else
            status="NOT ENFORCING"
        fi
        cls=$(status_class "$status")
        # NOT ENFORCING isn't in status_class — treat as warn manually
        if [ "$status" = "NOT ENFORCING" ]; then
            cls="warn"
            bump_status warn
        fi
        bump_status "$cls"

        rows+="<tr><td>${d}</td><td>${mode}</td><td>${policy_id:-?}</td><td>${max_age_days} days</td><td class=\"${cls}\">${status}</td></tr>"
    done

    SECTION_MTASTS="<h2>MTA-STS</h2>
<table>
<tr><th>Domain</th><th>Mode</th><th>Policy ID</th><th>max_age</th><th>Status</th></tr>
${rows}
</table>"
}

# Renewal detail block: only renders when at least one cert was renewed within
# the last RENEWAL_WINDOW_DAYS days. Populated by collect_tls() into RENEWED_CERTS.
SECTION_RENEWAL=""
SYNC_LOG="/var/log/mailcow-cert-sync.log"

collect_cert_renewal() {
    if [ ${#RENEWED_CERTS[@]} -eq 0 ]; then
        return
    fi

    local blocks=""

    for cert_path in "${RENEWED_CERTS[@]}"; do
        local cn not_before_str not_after_str fingerprint
        local mailcow_line tlsa_line live_match_line

        cn=$(openssl x509 -in "$cert_path" -noout -subject 2>/dev/null | sed 's/.*CN = //')
        not_before_str=$(openssl x509 -in "$cert_path" -noout -startdate 2>/dev/null | sed 's/notBefore=//')
        not_after_str=$(openssl x509 -in "$cert_path" -noout -enddate 2>/dev/null | sed 's/notAfter=//')
        fingerprint=$(openssl x509 -in "$cert_path" -noout -fingerprint -sha256 2>/dev/null \
            | sed -E "s/^[Ss][Hh][Aa]256 Fingerprint=//")

        local extras=""

        # Mail-cert-specific lines: Mailcow restart + TLSA rotation outcome + live port-25 verification
        if [[ "$cn" == "*.villaherrgard.com" ]]; then
            mailcow_line="(no recent log entry)"
            tlsa_line="(no recent log entry)"

            if [ -f "$SYNC_LOG" ]; then
                local recent_block
                # Last "Certificate change detected" run and everything after
                recent_block=$(tac "$SYNC_LOG" 2>/dev/null \
                    | awk '/Certificate change detected/{print; exit} {print}' \
                    | tac)

                if echo "$recent_block" | grep -q "Mailcow services restarted"; then
                    mailcow_line=$(echo "$recent_block" | grep "Mailcow services restarted" | tail -1 | sed 's/^\[\([^]]*\)\].*/✓ restarted at \1/')
                fi

                if echo "$recent_block" | grep -q "TLSA rotated successfully"; then
                    tlsa_line=$(echo "$recent_block" | grep "TLSA rotated successfully" | tail -1 | sed 's/^\[\([^]]*\)\].*/✓ rotated at \1/')
                elif echo "$recent_block" | grep -q "TLSA already matches"; then
                    tlsa_line="✓ already in sync (no rotation needed)"
                elif echo "$recent_block" | grep -q "TLSA rotation failed"; then
                    tlsa_line="✗ rotation FAILED — DANE delivery will break"
                fi
            fi

            # Live port-25 verification: does live cert match the NPM file?
            local live_fp file_fp
            file_fp=$(openssl x509 -in "$cert_path" -noout -fingerprint -sha256 2>/dev/null | sed -E "s/^[Ss][Hh][Aa]256 Fingerprint=//")
            live_fp=$(timeout 5 bash -c "echo | openssl s_client -connect ${MX_HOST}:25 -starttls smtp -servername ${MX_HOST} 2>/dev/null \
                | openssl x509 -noout -fingerprint -sha256 2>/dev/null" | sed -E 's/^[Ss][Hh][Aa]256 Fingerprint=//')

            if [ -n "$live_fp" ] && [ "$live_fp" = "$file_fp" ]; then
                live_match_line="✓ port 25 serves new cert"
            else
                live_match_line="✗ port 25 not serving new cert (file: ${file_fp:0:24}…, live: ${live_fp:0:24}…)"
            fi

            extras="
$(html_kv_row 'Mailcow restart' "$mailcow_line")
$(html_kv_row 'TLSA rotation' "$tlsa_line")
$(html_kv_row 'Port 25' "$live_match_line")"
        fi

        blocks+="<h3 style=\"margin-top:18px;font-size:13px;color:#2c3e50;\">${cn} renewed within last ${RENEWAL_WINDOW_DAYS} days</h3>
<table>
$(html_kv_row 'notBefore' "$not_before_str")
$(html_kv_row 'notAfter' "$not_after_str")
$(html_kv_row 'Fingerprint' "<code style=\"font-size:11px;\">${fingerprint}</code>")${extras}
</table>"
    done

    SECTION_RENEWAL="<h2>Cert Renewal — Last ${RENEWAL_WINDOW_DAYS} Days</h2>
${blocks}"
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
collect_dane
collect_mtasts
collect_cert_renewal
collect_docker

# Compose subject: append "- ALERT" first if any red status, then "+ Cert Renewal" if a renewal happened
SUBJECT="[VPS Summary] Weekly Health Report — ${HOSTNAME} (${DATE})"
if [ "$OVERALL_STATUS" = "error" ]; then
    SUBJECT="[VPS Summary - ALERT] Weekly Health Report — ${HOSTNAME} (${DATE})"
fi
if [ -n "$SECTION_RENEWAL" ]; then
    SUBJECT="${SUBJECT} + Cert Renewal"
fi

msmtp -t <<EOF
To: ${ALERT_EMAIL}
From: ${FROM_NAME} <root@villaherrgard.com>
Subject: ${SUBJECT}
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
${SECTION_DANE}
${SECTION_MTASTS}
${SECTION_RENEWAL}
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
