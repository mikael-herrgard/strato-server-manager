"""
Backup Operations Module
Handles Borg backups for nginx, Mailcow, and application files
"""

import gzip
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

    def _finish_backup(
        self,
        service: str,
        source_paths: List[str],
        excludes: Optional[List[str]],
        verify: bool
    ) -> bool:
        """
        Shared tail of every backup: create archive, verify, prune.

        Args:
            service: Service name (determines repo and archive naming)
            source_paths: Paths to include in the archive
            excludes: Borg exclude patterns
            verify: Verify archive after creation

        Returns:
            True if successful
        """
        repo = self._get_borg_repo(service)

        timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        archive_name = f"{self.hostname}-{service}-{timestamp}"

        if not self._create_borg_backup(repo, archive_name, source_paths, excludes):
            return False

        if verify:
            if not self.verify_backup(repo, archive_name):
                logger.error("Backup verification failed")
                return False

        self.prune_old_backups(repo)

        logger.info(f"{service} backup completed successfully")
        return True

    def _backup_service(
        self,
        service: str,
        source_paths: List[str],
        verify: bool = True,
        excludes: Optional[List[str]] = None,
        required_gb: int = 10,
        skip_missing: bool = False
    ) -> bool:
        """
        Generic backup flow for services that are plain paths on disk:
        pre-checks -> validate sources -> create/verify/prune.

        Args:
            service: Service name
            source_paths: Paths to back up
            verify: Verify archive after creation
            excludes: Borg exclude patterns
            required_gb: Required staging disk space in GB
            skip_missing: If True, missing paths are skipped with a
                          warning (at least one must exist); if False,
                          any missing path aborts the backup

        Returns:
            True if successful
        """
        logger.info(f"Starting {service} backup")

        if not self._pre_backup_checks(service, required_gb=required_gb):
            return False

        if skip_missing:
            existing = [p for p in source_paths if os.path.exists(p)]
            for p in source_paths:
                if p not in existing:
                    logger.warning(f"Path not found, skipping: {p}")
            if not existing:
                return self._error(f"No source paths found for {service} backup")
            source_paths = existing
        else:
            for p in source_paths:
                if not os.path.exists(p):
                    return self._error(f"{service} source path not found: {p}")

        return self._finish_backup(service, source_paths, excludes, verify)

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
        """Backup nginx Proxy Manager installation directory."""
        return self._backup_service(
            'nginx',
            [self.nginx_config['install_path']],
            verify=verify,
            excludes=['*.log', '*/logs/*', '*/.git/*', '*/tmp/*'],
            required_gb=5,
        )

    def _dump_mailcow_db(self, target_dir: str) -> bool:
        """
        Dump the Mailcow MySQL database into target_dir as backup_mysql.gz.

        Mailcow's own backup script skips the DB on this host: its docker run
        passes --sysctl net.ipv6.conf.all.disable_ipv6=1, which fails when the
        kernel has IPv6 fully disabled. backup_mysql.gz is a filename the
        official restore script picks up natively (gunzip | mysql).
        """
        mailcow_conf = os.path.join(self.mailcow_config['install_path'], 'mailcow.conf')
        db = {}
        try:
            with open(mailcow_conf) as f:
                for line in f:
                    key, _, value = line.strip().partition('=')
                    if key in ('DBNAME', 'DBUSER', 'DBPASS'):
                        db[key] = value
        except OSError as e:
            return self._error(f"Cannot read mailcow.conf for DB dump: {e}")

        missing = [k for k in ('DBNAME', 'DBUSER', 'DBPASS') if not db.get(k)]
        if missing:
            return self._error(f"mailcow.conf missing {', '.join(missing)} — cannot dump database")

        returncode, stdout, _ = run_command(['docker', 'ps', '-qf', 'name=mysql-mailcow'])
        container_id = stdout.strip().splitlines()[0] if stdout.strip() else ''
        if not container_id:
            return self._error("mysql-mailcow container not running — cannot dump database")

        dump_path = os.path.join(target_dir, 'backup_mysql.gz')
        logger.info(f"Dumping Mailcow database ({db['DBNAME']}) to {dump_path}")
        # Password goes via env inside the container, not argv; run subprocess
        # directly instead of run_command so neither ends up in the log.
        cmd = [
            'docker', 'exec', '-e', f"MYSQL_PWD={db['DBPASS']}", container_id,
            'mysqldump', '--single-transaction', '--default-character-set=utf8mb4',
            '-u', db['DBUSER'], '--databases', db['DBNAME'],
        ]
        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
        except subprocess.TimeoutExpired:
            return self._error("Mailcow DB dump timed out after 300s")

        if result.returncode != 0:
            stderr_tail = result.stderr.decode(errors='replace').strip()[-300:]
            return self._error(f"mysqldump failed (rc={result.returncode}): {stderr_tail}")
        if b'-- Dump completed' not in result.stdout[-500:]:
            return self._error("Mailcow DB dump is truncated (no completion marker)")

        try:
            with gzip.open(dump_path, 'wb') as gz:
                gz.write(result.stdout)
        except OSError as e:
            return self._error(f"Failed to write {dump_path}: {e}")

        logger.info(f"Mailcow database dumped: {len(result.stdout) / 1048576:.1f} MB uncompressed")
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

            # The official script silently skips the DB on this host (its
            # --sysctl IPv6 flag fails with kernel IPv6 disabled), so dump
            # the database ourselves before uploading.
            if backup_type in ('all', 'db', 'mysql'):
                if not self._dump_mailcow_db(latest_backup):
                    return False

            # Now create Borg archive from this backup
            return self._finish_backup('mailcow', [latest_backup], None, verify)

        except subprocess.CalledProcessError as e:
            stderr_tail = (e.stderr or '').strip()[-300:]
            return self._error(f"Mailcow backup script failed (rc={e.returncode}): {stderr_tail or e}")
        except subprocess.TimeoutExpired:
            return self._error("Mailcow backup timed out after 1 hour")

    def backup_mailcow_directory(self, verify: bool = True) -> bool:
        """
        Backup Mailcow installation directory (mailcow.conf, compose
        files, SSL certificates, DKIM keys).
        """
        return self._backup_service(
            'mailcow-directory',
            [self.mailcow_config['install_path']],
            verify=verify,
            excludes=[
                '*/backups/*',      # Old backup location (if any remain)
                '*.log',            # Log files
                '*/logs/*',         # Log directories
                '*/.git/*',         # Git metadata
                '*/tmp/*',          # Temporary files
                '*/data/redis/*',   # Redis temporary data (regenerated)
            ],
            required_gb=5,
        )

    def backup_server_manager(self, verify: bool = True) -> bool:
        """Backup server-manager config (settings.yaml, notifications.yaml)."""
        return self._backup_service(
            'server-manager',
            ['/opt/server-manager/config'],
            verify=verify,
            excludes=['*.example*'],
            required_gb=1,
        )

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

            excludes = [
                '*/.git/*',
                '*/__pycache__/*',
                '*.log',
                '*/logs/*',
            ]

            return self._finish_backup('monitoring-stack', source_paths, excludes, verify)

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
        Backup centralized credentials files (/root/.credentials.env
        and /root/.dns-config). Missing files are skipped with a warning.
        """
        return self._backup_service(
            'credentials',
            ['/root/.credentials.env', '/root/.dns-config'],
            verify=verify,
            required_gb=1,
            skip_missing=True,
        )

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
