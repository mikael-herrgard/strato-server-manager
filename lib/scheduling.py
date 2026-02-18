"""
Scheduling Manager
Handles automated task scheduling via cron
"""

import re
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from .utils import logger
from .config import get_config


class SchedulingManager:
    """Manages automated task scheduling"""

    BACKUP_QUEUE = [
        {'service': 'nginx',             'frequency': 'daily',  'offset_minutes': 0},
        {'service': 'mailcow-directory', 'frequency': 'daily',  'offset_minutes': 30},
        {'service': 'mailcow',           'frequency': 'daily',  'offset_minutes': 60},
        {'service': 'server-manager',    'frequency': 'daily',  'offset_minutes': 180},
        {'service': 'monitoring-stack',  'frequency': 'daily',  'offset_minutes': 210},
    ]

    BACKUP_WINDOWS = {
        'night':     {'hour': 2,  'label': 'Night (02:00)'},
        'morning':   {'hour': 8,  'label': 'Morning (08:00)'},
        'afternoon': {'hour': 14, 'label': 'Afternoon (14:00)'},
        'evening':   {'hour': 20, 'label': 'Evening (20:00)'},
    }

    def __init__(self):
        """Initialize scheduling manager"""
        self.config = get_config()
        self.cron_user = "root"
        self.schedule_dir = Path("/opt/server-manager/schedules")
        self.schedule_dir.mkdir(parents=True, exist_ok=True)

        logger.info("SchedulingManager initialized")

    def get_current_schedule(self) -> Dict[str, any]:
        """
        Get current cron schedule

        Returns:
            Dictionary containing current schedule information
        """
        try:
            result = subprocess.run(
                ["crontab", "-l"],
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                # No crontab exists yet
                return {
                    'exists': False,
                    'jobs': [],
                    'raw': ''
                }

            cron_content = result.stdout
            jobs = self._parse_crontab(cron_content)

            return {
                'exists': True,
                'jobs': jobs,
                'raw': cron_content
            }

        except Exception as e:
            logger.error(f"Failed to get cron schedule: {e}")
            raise

    def _parse_crontab(self, content: str) -> List[Dict[str, str]]:
        """
        Parse crontab content into job list

        Args:
            content: Raw crontab content

        Returns:
            List of job dictionaries
        """
        jobs = []

        for line in content.split('\n'):
            line = line.strip()

            # Skip empty lines and comments (but preserve job descriptions)
            if not line:
                continue

            if line.startswith('#'):
                # Check if it's a job description marker
                if 'server-manager:' in line:
                    continue
                else:
                    continue

            # Parse cron job
            parts = line.split(None, 5)
            if len(parts) >= 6:
                jobs.append({
                    'minute': parts[0],
                    'hour': parts[1],
                    'day': parts[2],
                    'month': parts[3],
                    'weekday': parts[4],
                    'command': parts[5],
                    'schedule': f"{parts[0]} {parts[1]} {parts[2]} {parts[3]} {parts[4]}",
                    'type': self._identify_job_type(parts[5])
                })

        return jobs

    def _identify_job_type(self, command: str) -> str:
        """
        Identify the type of scheduled job by extracting the service name
        from the automated-backup.sh command.

        Args:
            command: Cron command

        Returns:
            Job type identifier (e.g., 'backup_nginx', 'backup_monitoring-stack')
        """
        # Extract service name from: automated-backup.sh <service>
        match = re.search(r'automated-backup\.sh\s+(\S+)', command)
        if match:
            return f'backup_{match.group(1)}'

        if 'cleanup' in command:
            return 'cleanup'
        elif 'update' in command:
            return 'update'
        elif 'health-check' in command:
            return 'health_check'
        else:
            return 'unknown'

    def schedule_backup_queue(self, window_key: str) -> bool:
        """
        Schedule all backups using the queue-based approach.

        Replaces all existing backup_* cron jobs with a sequenced set
        based on the chosen time window.

        Args:
            window_key: One of 'night', 'morning', 'afternoon', 'evening'

        Returns:
            True if scheduled successfully
        """
        try:
            window = self.BACKUP_WINDOWS.get(window_key)
            if not window:
                raise ValueError(f"Invalid backup window: {window_key}")

            start_hour = window['hour']

            # Build new backup jobs from the queue
            new_backup_jobs = []
            for entry in self.BACKUP_QUEUE:
                total_minutes = start_hour * 60 + entry['offset_minutes']
                cron_hour = total_minutes // 60
                cron_minute = total_minutes % 60

                if entry['frequency'] == 'daily':
                    schedule = f"{cron_minute} {cron_hour} * * *"
                else:  # weekly (Sunday)
                    schedule = f"{cron_minute} {cron_hour} * * 0"

                cmd = self._build_backup_command(entry['service'], {'verify': True})

                new_backup_jobs.append({
                    'minute': str(cron_minute),
                    'hour': str(cron_hour),
                    'day': '*',
                    'month': '*',
                    'weekday': '*' if entry['frequency'] == 'daily' else '0',
                    'command': cmd,
                    'schedule': schedule,
                    'type': f"backup_{entry['service']}"
                })

            # Get current crontab and remove all existing backup_* jobs
            current = self.get_current_schedule()
            non_backup_jobs = [
                j for j in current.get('jobs', [])
                if not j['type'].startswith('backup_')
            ]

            # Combine non-backup jobs with new backup queue
            all_jobs = non_backup_jobs + new_backup_jobs

            # Write the full crontab
            self._write_crontab(all_jobs)

            # Persist the window choice in config
            self.config.set('backup.window', window_key)
            self.config.save_config()

            logger.info(f"Backup queue scheduled with window '{window_key}' (start: {start_hour:02d}:00)")
            return True

        except Exception as e:
            logger.error(f"Failed to schedule backup queue: {e}")
            return False

    def get_backup_queue_description(self, window_key: str) -> str:
        """
        Return a formatted preview of the backup queue for a given window.

        Args:
            window_key: One of 'night', 'morning', 'afternoon', 'evening'

        Returns:
            Formatted string showing each service, its time, and frequency
        """
        window = self.BACKUP_WINDOWS.get(window_key)
        if not window:
            return f"Unknown window: {window_key}"

        start_hour = window['hour']
        lines = [f"Backup Queue - {window['label']}", "=" * 50, ""]
        lines.append(f"{'Slot':<6}{'Service':<22}{'Time':<10}{'Frequency'}")
        lines.append("-" * 50)

        for i, entry in enumerate(self.BACKUP_QUEUE, 1):
            total_minutes = start_hour * 60 + entry['offset_minutes']
            h = total_minutes // 60
            m = total_minutes % 60
            time_str = f"{h:02d}:{m:02d}"
            freq = "Daily" if entry['frequency'] == 'daily' else "Weekly (Sun)"
            lines.append(f"{i:<6}{entry['service']:<22}{time_str:<10}{freq}")

        lines.append("")
        lines.append("Daily jobs run every night.")
        lines.append("Weekly jobs run on Sunday only.")

        return "\n".join(lines)

    def _validate_cron_schedule(self, schedule: str) -> bool:
        """
        Validate cron schedule expression

        Args:
            schedule: Cron schedule (e.g., "0 2 * * *")

        Returns:
            True if valid
        """
        parts = schedule.split()
        if len(parts) != 5:
            return False

        # Basic validation of each part
        patterns = [
            r'^(\*|([0-5]?[0-9])(,([0-5]?[0-9]))*(\/([0-5]?[0-9]))?)$',  # minute
            r'^(\*|([01]?[0-9]|2[0-3])(,([01]?[0-9]|2[0-3]))*(\/([01]?[0-9]|2[0-3]))?)$',  # hour
            r'^(\*|([1-9]|[12][0-9]|3[01])(,([1-9]|[12][0-9]|3[01]))*(\/([1-9]|[12][0-9]|3[01]))?)$',  # day
            r'^(\*|([1-9]|1[0-2])(,([1-9]|1[0-2]))*(\/([1-9]|1[0-2]))?)$',  # month
            r'^(\*|[0-6](,[0-6])*(\/[0-6])?)$'  # weekday
        ]

        for part, pattern in zip(parts, patterns):
            if not re.match(pattern, part):
                return False

        return True

    def _build_backup_command(self, service: str, options: Dict) -> str:
        """
        Build backup command for cron with flock to prevent concurrent runs

        Args:
            service: Service name
            options: Backup options

        Returns:
            Full command string
        """
        script_path = "/opt/server-manager/scripts/automated-backup.sh"
        log_file = f"/opt/server-manager/logs/backup-{service}-cron.log"
        lock_file = f"/tmp/backup-{service}.lock"

        backup_cmd = f"{script_path} {service}"

        if options.get('verify'):
            backup_cmd += " --verify"

        # Redirect output to log file
        backup_cmd += f" >> {log_file} 2>&1"

        # Wrap in flock to prevent concurrent runs
        cmd = f"flock -n {lock_file} {backup_cmd}"

        return cmd

    def _write_crontab(self, jobs: List[Dict[str, str]]) -> bool:
        """
        Write crontab from job list

        Args:
            jobs: List of job dictionaries

        Returns:
            True if successful
        """
        try:
            # Build crontab content
            lines = [
                "# server-manager automated schedules",
                "# Generated by SchedulingManager",
                f"# Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                "",
                "# Environment",
                "SHELL=/bin/bash",
                "PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin",
                "MAILTO=root",
                ""
            ]

            # Add jobs
            for job in jobs:
                job_type = job.get('type', 'unknown')
                lines.append(f"# server-manager: {job_type}")

                cron_line = f"{job['minute']} {job['hour']} {job['day']} {job['month']} {job['weekday']} {job['command']}"
                lines.append(cron_line)
                lines.append("")

            # Write to temp file
            temp_file = self.schedule_dir / "crontab.tmp"
            with open(temp_file, 'w') as f:
                f.write('\n'.join(lines))

            # Install crontab
            result = subprocess.run(
                ["crontab", str(temp_file)],
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                raise Exception(f"Failed to install crontab: {result.stderr}")

            # Clean up temp file
            temp_file.unlink()

            logger.info("Crontab updated successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to write crontab: {e}")
            raise

    def remove_schedule(self, job_type: str) -> bool:
        """
        Remove scheduled job

        Args:
            job_type: Type of job to remove

        Returns:
            True if removed successfully
        """
        try:
            current = self.get_current_schedule()

            if not current['exists']:
                return True

            # Filter out the job
            jobs = [j for j in current['jobs'] if j['type'] != job_type]

            if len(jobs) == len(current['jobs']):
                logger.warning(f"Job type {job_type} not found in schedule")
                return False

            # Write updated crontab
            self._write_crontab(jobs)

            logger.info(f"Removed schedule for {job_type}")
            return True

        except Exception as e:
            logger.error(f"Failed to remove schedule: {e}")
            return False

    def get_schedule_presets(self) -> Dict[str, str]:
        """
        Get predefined schedule presets

        Returns:
            Dictionary of preset name to cron schedule
        """
        return {
            'daily_2am': '0 2 * * *',
            'daily_3am': '0 3 * * *',
            'daily_4am': '0 4 * * *',
            'daily_midnight': '0 0 * * *',
            'weekly_sunday_2am': '0 2 * * 0',
            'weekly_monday_2am': '0 2 * * 1',
            'hourly': '0 * * * *',
            'every_6_hours': '0 */6 * * *',
            'every_12_hours': '0 */12 * * *'
        }

    def get_schedule_description(self, schedule: str) -> str:
        """
        Get human-readable description of cron schedule

        Args:
            schedule: Cron schedule expression

        Returns:
            Human-readable description
        """
        presets = {
            '0 2 * * *': 'Daily at 2:00 AM',
            '0 3 * * *': 'Daily at 3:00 AM',
            '0 4 * * *': 'Daily at 4:00 AM',
            '0 0 * * *': 'Daily at midnight',
            '0 2 * * 0': 'Weekly on Sunday at 2:00 AM',
            '0 2 * * 1': 'Weekly on Monday at 2:00 AM',
            '0 * * * *': 'Every hour',
            '0 */6 * * *': 'Every 6 hours',
            '0 */12 * * *': 'Every 12 hours'
        }

        return presets.get(schedule, f"Custom schedule: {schedule}")

    def schedule_cleanup(self, schedule: str, retention_days: int = 30) -> bool:
        """
        Schedule automated backup cleanup

        Args:
            schedule: Cron schedule expression
            retention_days: Days to retain backups

        Returns:
            True if scheduled successfully
        """
        try:
            if not self._validate_cron_schedule(schedule):
                raise ValueError(f"Invalid cron schedule: {schedule}")

            cmd = f"/opt/server-manager/scripts/cleanup-backups.sh {retention_days} >> /opt/server-manager/logs/cleanup-cron.log 2>&1"

            current = self.get_current_schedule()
            jobs = [j for j in current.get('jobs', []) if j['type'] != 'cleanup']

            jobs.append({
                'minute': schedule.split()[0],
                'hour': schedule.split()[1],
                'day': schedule.split()[2],
                'month': schedule.split()[3],
                'weekday': schedule.split()[4],
                'command': cmd,
                'schedule': schedule,
                'type': 'cleanup'
            })

            self._write_crontab(jobs)

            logger.info(f"Scheduled cleanup: {schedule} (retention: {retention_days} days)")
            return True

        except Exception as e:
            logger.error(f"Failed to schedule cleanup: {e}")
            return False

    def get_next_run_time(self, schedule: str) -> Optional[str]:
        """
        Calculate next run time for a schedule

        Args:
            schedule: Cron schedule expression

        Returns:
            Next run time as string, or None if cannot calculate
        """
        try:
            # This is a simplified version
            # For production, consider using python-crontab library
            parts = schedule.split()
            if len(parts) != 5:
                return None

            minute, hour = parts[0], parts[1]

            now = datetime.now()

            # Handle simple cases
            if minute == '*' and hour == '*':
                return "Next hour"
            elif minute.isdigit() and hour.isdigit():
                next_hour = int(hour)
                next_minute = int(minute)

                if now.hour > next_hour or (now.hour == next_hour and now.minute >= next_minute):
                    return f"Tomorrow at {next_hour:02d}:{next_minute:02d}"
                else:
                    return f"Today at {next_hour:02d}:{next_minute:02d}"

            return "See cron schedule"

        except Exception:
            return None
