"""
Backup Operations Module
Handles Borg backups for nginx, Mailcow, and application files
"""

import os
import subprocess
from datetime import datetime
from typing import Dict, List, Optional, Union
from .utils import (
    logger,
    run_command,
    check_disk_space,
    test_ssh_connection,
    ensure_directory,
    get_hostname,
    CommandExecutor,
    stop_systemd_service,
    start_systemd_service,
    verify_systemd_service
)
from .borg import BorgRepoBase


class BackupManager(BorgRepoBase):
    """Manage backup operations for all services

    Borg environment, repository addressing, and archive operations
    (create/verify/prune/list) come from BorgRepoBase.
    """

    def __init__(self):
        """Initialize backup manager"""
        super().__init__()
        self.hostname = get_hostname()

    def initialize_all_repos(self) -> Dict[str, bool]:
        """
        Initialize all Borg backup repositories.

        Checks each known service repo and initializes any that don't exist.
        Useful when migrating to a new rsync/Borg provider.

        Returns:
            Dictionary mapping service name to success/failure
        """
        logger.info("Initializing all Borg backup repositories")

        results = {}
        for service in self.BACKUP_SERVICES:
            repo = self._get_borg_repo(service)
            results[service] = self._ensure_borg_repo(repo)

        return results

    def _pre_backup_checks(self, service: str, required_gb: int = 10) -> bool:
        """
        Perform pre-backup checks

        Args:
            service: Service name
            required_gb: Required disk space in GB

        Returns:
            True if all checks pass
        """
        logger.info(f"Running pre-backup checks for {service}")

        # Check disk space
        if not check_disk_space(self.local_staging, required_gb):
            return self._error(f"Insufficient disk space for {service} backup at {self.local_staging}")

        # Check SSH connection to rsync server
        ssh_key = self.rsync_config.get('ssh_key')
        rsync_host = self.rsync_config['host']
        rsync_user = self.rsync_config['user']

        if not test_ssh_connection(rsync_host, rsync_user, ssh_key):
            return self._error(f"Cannot connect to rsync server: {rsync_host} (SSH failed after retries)")

        # Check Borg passphrase
        if 'BORG_PASSPHRASE' not in self.borg_env:
            return self._error("BORG_PASSPHRASE not set")

        # Ensure Borg repository exists (auto-initialize if missing)
        repo = self._get_borg_repo(service)
        if not self._ensure_borg_repo(repo):
            # _ensure_borg_repo already recorded the specific error
            logger.error(f"Borg repository not available for {service}")
            return False

        logger.info("Pre-backup checks passed")
        return True

    def get_backup_info(self, repo: str, archive_name: str) -> Optional[Dict[str, str]]:
        """
        Get detailed information about a backup

        Args:
            repo: Borg repository URL
            archive_name: Archive name

        Returns:
            Dictionary with backup information or None
        """
        cmd = ['borg', 'info', f"{repo}::{archive_name}"]

        try:
            returncode, stdout, stderr = run_command(
                cmd,
                check=True,
                env=self.borg_env,
                timeout=60
            )

            # Parse output (simplified)
            info = {
                'name': archive_name,
                'output': stdout
            }

            return info

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get backup info: {e}")
            return None

    def backup_nginx(self, verify: bool = True) -> bool:
        """
        Backup nginx Proxy Manager

        Args:
            verify: Verify backup after creation

        Returns:
            True if successful
        """
        logger.info("Starting nginx backup")

        # Get configuration
        nginx_path = self.nginx_config['install_path']
        repo = self._get_borg_repo('nginx')

        # Pre-backup checks
        if not self._pre_backup_checks('nginx', required_gb=5):
            return False

        # Check if nginx directory exists
        if not os.path.exists(nginx_path):
            return self._error(f"nginx directory not found: {nginx_path}")

        # Create archive name with timestamp
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        archive_name = f"{self.hostname}-nginx-{timestamp}"

        # Exclude patterns (from your bash script)
        excludes = [
            '*.log',
            '*/logs/*',
            '*/.git/*',
            '*/tmp/*'
        ]

        # Create backup
        if not self._create_borg_backup(repo, archive_name, nginx_path, excludes):
            return False

        # Verify backup
        if verify:
            if not self.verify_backup(repo, archive_name):
                logger.error("Backup verification failed")
                return False

        # Prune old backups
        self.prune_old_backups(repo)

        logger.info("nginx backup completed successfully")
        return True

    def backup_mailcow(self, backup_type: str = "all", verify: bool = True) -> bool:
        """
        Backup Mailcow using official backup script

        Args:
            backup_type: Type of backup (all, config, mail, db)
            verify: Verify backup after creation

        Returns:
            True if successful
        """
        logger.info(f"Starting Mailcow backup (type: {backup_type})")

        # Get configuration
        mailcow_path = self.mailcow_config['install_path']
        backup_script = os.path.join(mailcow_path, 'helper-scripts', 'backup_and_restore.sh')
        # Use separate backup directory outside mailcow install path
        mailcow_backup_dir = '/var/backups/mailcow-data'

        # Pre-backup checks
        if not self._pre_backup_checks('mailcow', required_gb=20):
            return False

        # Check if Mailcow is installed
        if not os.path.exists(mailcow_path):
            return self._error(f"Mailcow directory not found: {mailcow_path}")

        if not os.path.exists(backup_script):
            return self._error(f"Mailcow backup script not found: {backup_script}")

        # Ensure backup directory exists
        ensure_directory(mailcow_backup_dir)

        # Set environment variables for backup location and resource limits
        mailcow_env = os.environ.copy()
        mailcow_env['MAILCOW_BACKUP_LOCATION'] = mailcow_backup_dir
        mailcow_env['THREADS'] = '2'  # Limit CPU usage, leaving 2 cores for other tasks

        try:
            # Run Mailcow's official backup script with local retention policy
            with CommandExecutor(f"Mailcow backup ({backup_type})"):
                cmd = [backup_script, 'backup', backup_type, '--delete-days', '7']
                returncode, stdout, stderr = run_command(
                    cmd,
                    check=True,
                    cwd=mailcow_path,
                    env=mailcow_env,
                    timeout=3600  # 1 hour
                )

            # Find the latest backup directory created
            backup_dirs = []
            for item in os.listdir(mailcow_backup_dir):
                item_path = os.path.join(mailcow_backup_dir, item)
                if os.path.isdir(item_path) and item.startswith('mailcow-'):
                    backup_dirs.append(item_path)

            if not backup_dirs:
                return self._error("No backup directory created by Mailcow script")

            # Get the most recent backup directory
            latest_backup = max(backup_dirs, key=os.path.getmtime)
            logger.info(f"Mailcow backup created: {latest_backup}")

            # Now create Borg archive from this backup
            timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            archive_name = f"{self.hostname}-mailcow-{timestamp}"
            repo = self._get_borg_repo('mailcow')

            if not self._create_borg_backup(repo, archive_name, latest_backup):
                return False

            # Verify backup
            if verify:
                if not self.verify_backup(repo, archive_name):
                    logger.error("Backup verification failed")
                    return False

            # Prune old backups
            self.prune_old_backups(repo)

            logger.info("Mailcow backup completed successfully")
            return True

        except subprocess.CalledProcessError as e:
            stderr_tail = (e.stderr or '').strip()[-300:]
            return self._error(f"Mailcow backup script failed (rc={e.returncode}): {stderr_tail or e}")
        except subprocess.TimeoutExpired:
            return self._error("Mailcow backup timed out after 1 hour")

    def backup_mailcow_directory(self, verify: bool = True) -> bool:
        """
        Backup Mailcow installation directory (configuration and certificates)

        This backs up /opt/mailcow-dockerized including:
        - mailcow.conf
        - docker-compose.yml and related files
        - SSL certificates
        - DKIM keys
        - Configuration files

        Args:
            verify: Verify backup after creation

        Returns:
            True if successful
        """
        logger.info("Starting Mailcow directory backup")

        # Get configuration
        mailcow_path = self.mailcow_config['install_path']
        repo = self._get_borg_repo('mailcow-directory')

        # Pre-backup checks
        if not self._pre_backup_checks('mailcow-directory', required_gb=5):
            return False

        # Check if mailcow directory exists
        if not os.path.exists(mailcow_path):
            return self._error(f"Mailcow directory not found: {mailcow_path}")

        # Create archive name with timestamp
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        archive_name = f"{self.hostname}-mailcow-directory-{timestamp}"

        # Exclude patterns - we don't need backups, logs, or temporary data
        excludes = [
            '*/backups/*',      # Old backup location (if any remain)
            '*.log',            # Log files
            '*/logs/*',         # Log directories
            '*/.git/*',         # Git metadata
            '*/tmp/*',          # Temporary files
            '*/data/redis/*',   # Redis temporary data (regenerated)
        ]

        # Create backup
        if not self._create_borg_backup(repo, archive_name, mailcow_path, excludes):
            return False

        # Verify backup
        if verify:
            if not self.verify_backup(repo, archive_name):
                logger.error("Backup verification failed")
                return False

        # Prune old backups
        self.prune_old_backups(repo)

        logger.info("Mailcow directory backup completed successfully")
        return True

    def backup_server_manager(self, verify: bool = True) -> bool:
        """
        Backup server-manager configuration files

        This backs up /opt/server-manager/config/ including:
        - settings.yaml
        - notifications.yaml

        Args:
            verify: Verify backup after creation

        Returns:
            True if successful
        """
        logger.info("Starting server-manager config backup")

        config_path = '/opt/server-manager/config'
        repo = self._get_borg_repo('server-manager')

        # Pre-backup checks
        if not self._pre_backup_checks('server-manager', required_gb=1):
            return False

        if not os.path.exists(config_path):
            return self._error(f"Config directory not found: {config_path}")

        # Create archive name with timestamp
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        archive_name = f"{self.hostname}-server-manager-{timestamp}"

        excludes = [
            '*.example*',
        ]

        # Create backup
        if not self._create_borg_backup(repo, archive_name, config_path, excludes):
            return False

        # Verify backup
        if verify:
            if not self.verify_backup(repo, archive_name):
                logger.error("Backup verification failed")
                return False

        # Prune old backups
        self.prune_old_backups(repo)

        logger.info("Server-manager config backup completed successfully")
        return True

    def backup_monitoring_stack(self, verify: bool = True) -> bool:
        """
        Backup monitoring stack (Grafana, InfluxDB, pressuresuite-influx-bridge)

        All three components are backed up as a single archive since they form
        one logical unit. Grafana and InfluxDB are stopped during backup for
        data consistency. The Borg repository is auto-initialized if missing.

        Args:
            verify: Verify backup after creation

        Returns:
            True if successful
        """
        logger.info("Starting monitoring stack backup")

        # Get configuration
        monitoring_config = self.config.get_monitoring_stack_config()
        repo = self._get_borg_repo('monitoring-stack')

        # Pre-backup checks
        if not self._pre_backup_checks('monitoring-stack', required_gb=1):
            return False

        # Collect source paths and validate they exist
        source_paths = [
            monitoring_config['grafana_data_path'],
            monitoring_config['grafana_config_path'],
            monitoring_config['influxdb_data_path'],
            monitoring_config['influxdb_config_path'],
            monitoring_config['bridge_install_path'],
        ]

        # Include InfluxDB CLI config if it exists (contains API token for CLI access)
        influxdb_cli_config = os.path.expanduser('~/.influxdbv2')
        if os.path.isdir(influxdb_cli_config):
            source_paths.append(influxdb_cli_config)

        # Add systemd unit files if they exist
        bridge_service_path = f"/etc/systemd/system/{monitoring_config['bridge_service']}"
        bridge_timer_path = f"/etc/systemd/system/{monitoring_config['bridge_timer']}"
        if os.path.exists(bridge_service_path):
            source_paths.append(bridge_service_path)
        if os.path.exists(bridge_timer_path):
            source_paths.append(bridge_timer_path)

        # Validate all paths exist
        missing = [p for p in source_paths if not os.path.exists(p)]
        if missing:
            return self._error(f"Missing source paths: {missing}")

        # Stop services for consistent snapshot
        logger.info("Stopping monitoring services for consistent backup...")
        services_to_stop = ['grafana-server', 'influxdb']
        stopped_services = []

        try:
            for svc in services_to_stop:
                if verify_systemd_service(svc):
                    if stop_systemd_service(svc):
                        stopped_services.append(svc)
                    else:
                        logger.warning(f"Failed to stop {svc}, continuing anyway")

            # Create archive name with timestamp
            timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            archive_name = f"{self.hostname}-monitoring-stack-{timestamp}"

            # Exclude patterns
            excludes = [
                '*/.git/*',
                '*/__pycache__/*',
                '*.log',
                '*/logs/*',
            ]

            # Create backup
            if not self._create_borg_backup(repo, archive_name, source_paths, excludes):
                return False

            # Verify backup
            if verify:
                if not self.verify_backup(repo, archive_name):
                    logger.error("Backup verification failed")
                    return False

            # Prune old backups
            self.prune_old_backups(repo)

            logger.info("Monitoring stack backup completed successfully")
            return True

        except Exception as e:
            return self._error(f"Monitoring stack backup failed: {e}")

        finally:
            # Always restart services
            logger.info("Restarting monitoring services...")
            restart_failures = []
            for svc in reversed(stopped_services):
                if not start_systemd_service(svc):
                    restart_failures.append(svc)
            if restart_failures:
                logger.error(f"CRITICAL: Failed to restart services: {', '.join(restart_failures)}")
                logger.error("Manual intervention required — run: systemctl start " + " ".join(restart_failures))

    def backup_credentials(self, verify: bool = True) -> bool:
        """
        Backup centralized credentials files

        Backs up /root/.credentials.env and /root/.dns-config to a dedicated
        Borg repository. These are tiny files (~1KB) so the backup is very fast.

        Args:
            verify: Verify backup after creation

        Returns:
            True if successful
        """
        logger.info("Starting credentials backup")

        repo = self._get_borg_repo('credentials')

        # Pre-backup checks (minimal disk space needed)
        if not self._pre_backup_checks('credentials', required_gb=1):
            return False

        # Collect source paths
        source_paths = []
        for path in ['/root/.credentials.env', '/root/.dns-config']:
            if os.path.exists(path):
                source_paths.append(path)
            else:
                logger.warning(f"Credentials file not found: {path}")

        if not source_paths:
            return self._error("No credentials files found to back up")

        # Create archive name with timestamp
        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        archive_name = f"{self.hostname}-credentials-{timestamp}"

        # Create backup
        if not self._create_borg_backup(repo, archive_name, source_paths):
            return False

        # Verify backup
        if verify:
            if not self.verify_backup(repo, archive_name):
                logger.error("Backup verification failed")
                return False

        # Prune old backups
        self.prune_old_backups(repo)

        logger.info("Credentials backup completed successfully")
        return True

    def get_backup_status(self) -> Dict[str, any]:
        """
        Get status of all backups

        Returns:
            Dictionary with backup status for all services
        """
        status = {}

        for service in self.BACKUP_SERVICES:
            repo = self._get_borg_repo(service)
            backups = self.list_backups(repo)

            status[service] = {
                'repository': repo,
                'backup_count': len(backups),
                'latest_backup': backups[-1]['name'] if backups else None,
                'all_backups': backups
            }

        return status
