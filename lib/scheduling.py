"""
Scheduling Manager
Handles automated task scheduling via cron
"""

import os
import re
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from .utils import logger
from .config import get_config


class SchedulingManager:
    """Manages automated task scheduling"""

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
        Identify the type of scheduled job

        Args:
            command: Cron command

        Returns:
            Job type identifier
        """
        if 'backup-nginx' in command or 'backup_nginx' in command:
            return 'backup_nginx'
        elif 'backup-mailcow' in command or 'backup_mailcow' in command:
            return 'backup_mailcow'
        elif 'backup-application' in command or 'backup_application' in command:
            return 'backup_application'
        elif 'cleanup' in command:
            return 'cleanup'
        elif 'update' in command:
            return 'update'
        elif 'health-check' in command:
            return 'health_check'
        else:
            return 'unknown'

    def schedule_backup(
        self,
        service: str,
        schedule: str,
        options: Optional[Dict] = None
    ) -> bool:
        """
        Schedule automated backup

        Args:
            service: Service to backup (nginx, mailcow, application)
            schedule: Cron schedule expression
            options: Optional backup options

        Returns:
            True if scheduled successfully
        """
        try:
            options = options or {}

            # Validate schedule
            if not self._validate_cron_schedule(schedule):
                raise ValueError(f"Invalid cron schedule: {schedule}")

            # Build backup command
            cmd = self._build_backup_command(service, options)

            # Get current crontab
            current = self.get_current_schedule()

            # Remove existing job for this service if any
            jobs = [j for j in current.get('jobs', []) if j['type'] != f'backup_{service}']

            # Add new job
            jobs.append({
                'minute': schedule.split()[0],
                'hour': schedule.split()[1],
                'day': schedule.split()[2],
                'month': schedule.split()[3],
                'weekday': schedule.split()[4],
                'command': cmd,
                'schedule': schedule,
                'type': f'backup_{service}'
            })

            # Write new crontab
            self._write_crontab(jobs)

            logger.info(f"Scheduled {service} backup: {schedule}")
            return True

        except Exception as e:
            logger.error(f"Failed to schedule backup: {e}")
            return False

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
        Build backup command for cron

        Args:
            service: Service name
            options: Backup options

        Returns:
            Full command string
        """
        script_path = "/opt/server-manager/scripts/automated-backup.sh"
        log_file = f"/opt/server-manager/logs/backup-{service}-cron.log"

        cmd = f"{script_path} {service}"

        if options.get('verify'):
            cmd += " --verify"

        if options.get('remote'):
            cmd += " --remote"

        # Redirect output to log file
        cmd += f" >> {log_file} 2>&1"

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

    def test_schedule(self, service: str) -> Dict[str, any]:
        """
        Test scheduled job execution

        Args:
            service: Service to test backup

        Returns:
            Test results dictionary
        """
        try:
            cmd = self._build_backup_command(service, {'verify': True})

            # Remove log redirection for test
            cmd = cmd.split('>>')[0].strip()

            start_time = datetime.now()
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout for test
            )
            end_time = datetime.now()

            duration = (end_time - start_time).total_seconds()

            return {
                'success': result.returncode == 0,
                'duration': duration,
                'output': result.stdout,
                'error': result.stderr,
                'returncode': result.returncode
            }

        except subprocess.TimeoutExpired:
            return {
                'success': False,
                'duration': 300,
                'output': '',
                'error': 'Test timed out after 5 minutes',
                'returncode': -1
            }
        except Exception as e:
            return {
                'success': False,
                'duration': 0,
                'output': '',
                'error': str(e),
                'returncode': -1
            }

    def disable_all_schedules(self) -> bool:
        """
        Disable all server-manager schedules

        Returns:
            True if disabled successfully
        """
        try:
            # Remove crontab entirely
            result = subprocess.run(
                ["crontab", "-r"],
                capture_output=True,
                text=True
            )

            # Note: crontab -r returns 0 even if no crontab exists
            logger.info("All schedules disabled")
            return True

        except Exception as e:
            logger.error(f"Failed to disable schedules: {e}")
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
