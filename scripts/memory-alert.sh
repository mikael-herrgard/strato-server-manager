#!/bin/bash
# memory-alert.sh -- Send email alert when memory or swap is low
# Runs via cron every 5 minutes

set -euo pipefail

ALERT_EMAIL="micke@nysattra.se"
FROM_NAME="VPS Memory Monitor"
STATE_FILE="/tmp/memory-alert-sent"

# Thresholds
RAM_THRESHOLD=15    # alert when available RAM drops below 15%
SWAP_THRESHOLD=50   # alert when swap usage exceeds 50%

# Read memory info
read -r mem_total mem_available <<< "$(awk '/MemTotal/{t=$2} /MemAvailable/{a=$2} END{print t, a}' /proc/meminfo)"
read -r swap_total swap_free <<< "$(awk '/SwapTotal/{t=$2} /SwapFree/{f=$2} END{print t, f}' /proc/meminfo)"

# Calculate percentages
if [ "$mem_total" -gt 0 ]; then
    ram_avail_pct=$(( mem_available * 100 / mem_total ))
else
    ram_avail_pct=100
fi

if [ "$swap_total" -gt 0 ]; then
    swap_used_pct=$(( (swap_total - swap_free) * 100 / swap_total ))
else
    swap_used_pct=0
fi

# Check if alert conditions are met
alert_needed=false
alert_reason=""

if [ "$ram_avail_pct" -lt "$RAM_THRESHOLD" ]; then
    alert_needed=true
    alert_reason="RAM available: ${ram_avail_pct}% (threshold: ${RAM_THRESHOLD}%)"
fi

if [ "$swap_used_pct" -gt "$SWAP_THRESHOLD" ]; then
    alert_needed=true
    alert_reason="${alert_reason:+${alert_reason}; }Swap used: ${swap_used_pct}% (threshold: ${SWAP_THRESHOLD}%)"
fi

if [ "$alert_needed" = true ]; then
    # Only send if we haven't already alerted for this incident
    if [ ! -f "$STATE_FILE" ]; then
        top_consumers=$(ps aux --sort=-%mem | head -11 | awk 'NR==1{printf "%-10s %5s %5s  %s\n",$1,$4,$6,"COMMAND"} NR>1{printf "%-10s %5s %5s  %s\n",$1,$4,$6,$11}')

        msmtp -t <<EOF
To: ${ALERT_EMAIL}
From: ${FROM_NAME} <root@villaherrgard.com>
Subject: [VPS ALERT] Low memory on $(hostname)

Memory alert triggered at $(date '+%Y-%m-%d %H:%M:%S')

${alert_reason}

Memory: $(free -h | awk '/Mem/{printf "%s used / %s total (%s available)", $3, $2, $7}')
Swap:   $(free -h | awk '/Swap/{printf "%s used / %s total (%s free)", $3, $2, $4}')

Top memory consumers:
${top_consumers}

--
earlyoom is active and will kill processes if memory drops below 5%.
This alert is sent once per incident; it resets when memory recovers.
EOF

        touch "$STATE_FILE"
        logger -t memory-alert "Alert sent: ${alert_reason}"
    fi
else
    # Memory recovered -- reset state so next incident triggers a new alert
    if [ -f "$STATE_FILE" ]; then
        rm -f "$STATE_FILE"
        logger -t memory-alert "Memory recovered: RAM available ${ram_avail_pct}%, swap used ${swap_used_pct}%"
    fi
fi

# Check if a reboot is required (e.g. kernel security update)
REBOOT_STATE_FILE="/tmp/reboot-required-alert-sent"

if [ -f /var/run/reboot-required ]; then
    if [ ! -f "$REBOOT_STATE_FILE" ]; then
        reboot_pkgs=""
        if [ -f /var/run/reboot-required.pkgs ]; then
            reboot_pkgs=$(cat /var/run/reboot-required.pkgs)
        fi

        msmtp -t <<EOF
To: ${ALERT_EMAIL}
From: ${FROM_NAME} <root@villaherrgard.com>
Subject: [VPS ALERT] Reboot required on $(hostname)

A system update requires a reboot.

Detected at: $(date '+%Y-%m-%d %H:%M:%S')
Uptime: $(uptime -p)

Packages requiring reboot:
${reboot_pkgs:-unknown}

Please schedule a reboot at your earliest convenience.
EOF

        touch "$REBOOT_STATE_FILE"
        logger -t memory-alert "Reboot-required alert sent"
    fi
else
    rm -f "$REBOOT_STATE_FILE"
fi
