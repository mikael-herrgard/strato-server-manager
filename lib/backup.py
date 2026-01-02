"""
Backup Operations Module
Handles Borg backups for nginx, Mailcow, and application files
"""

import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from .utils import (
    logger,
    run_command,
    check_disk_space,
    test_ssh_connection,
    validate_backup_name,
    ensure_directory,
    get_hostname,
    CommandExecutor
)
from .config import get_config


class BackupManager:
    """Manage backup operations for all services"""

    def __init__(self):
        """Initialize backup manager"""
        self.config = get_config()
        self.hostname = get_hostname()

        # Get configuration
        self.borg_config = self.config.get_borg_config()
        self.rsync_config = self.config.get_rsync_config()
        self.backup_config = self.config.get_backup_config()
        self.nginx_config = self.config.get_nginx_config()
        self.mailcow_config = self.config.get_mailcow_config()

        # Setup environment for Borg
        self.borg_env = os.environ.copy()
        passphrase = self.config.get_secret('BORG_PASSPHRASE')
        if passphrase:
            self.borg_env['BORG_PASSPHRASE'] = passphrase

        self.borg_env['BORG_REMOTE_PATH'] = self.borg_config['remote_path']

        # Local staging area
        self.local_staging = self.backup_config['local_staging']
        ensure_directory(self.local_staging)

    def _get_borg_repo(self, service: str) -> str:
        """
        Get Borg repository URL for a service

        Args:
            service: Service name (nginx, mailcow, application)

        Returns:
            Borg repository URL
        """
        rsync_host = self.rsync_config['host']
        base_path = self.rsync_config['base_path'].strip('/')

        # Use relative path format (./path) for rsync.net compatibility
        return f"ssh://{rsync_host}/./{base_path}/{service}-backup"

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
            logger.error(f"Insufficient disk space for {service} backup")
            return False

        # Check SSH connection to rsync server
        ssh_key = self.rsync_config.get('ssh_key')
        rsync_host = self.rsync_config['host']
        rsync_user = self.rsync_config['user']

        if not test_ssh_connection(rsync_host, rsync_user, ssh_key):
            logger.error(f"Cannot connect to rsync server: {rsync_host}")
            return False

        # Check Borg passphrase
        if 'BORG_PASSPHRASE' not in self.borg_env:
            logger.error("BORG_PASSPHRASE not set")
            return False

        logger.info("Pre-backup checks passed")
        return True

    def _create_borg_backup(
        self,
        repo: str,
        archive_name: str,
        source_path: str,
        excludes: Optional[List[str]] = None
    ) -> bool:
        """
        Create a Borg backup

        Args:
            repo: Borg repository URL
            archive_name: Archive name
            source_path: Path to backup
            excludes: List of exclude patterns

        Returns:
            True if successful
        """
        logger.info(f"Creating Borg backup: {archive_name}")

        # Check if source exists
        if not os.path.exists(source_path):
            logger.error(f"Source path does not exist: {source_path}")
            return False

        # Build command
        cmd = [
            'borg', 'create',
            '--stats',
            '--progress',
            '--compression', self.borg_config['compression'],
            '--verbose'
        ]

        # Add excludes
        if excludes:
            for pattern in excludes:
                cmd.extend(['--exclude', pattern])

        # Add archive and source
        cmd.append(f"{repo}::{archive_name}")
        cmd.append(source_path)

        try:
            with CommandExecutor(f"Borg backup: {archive_name}"):
                returncode, stdout, stderr = run_command(
                    cmd,
                    check=True,
                    env=self.borg_env,
                    timeout=3600  # 1 hour timeout
                )

            logger.info(f"Backup created successfully: {archive_name}")
            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Borg backup failed: {e}")
            return False
        except subprocess.TimeoutExpired:
            logger.error(f"Borg backup timed out: {archive_name}")
            return False

    def verify_backup(self, repo: str, archive_name: str) -> bool:
        """
        Verify backup integrity

        Args:
            repo: Borg repository URL
            archive_name: Archive name to verify

        Returns:
            True if backup is valid
        """
        logger.info(f"Verifying backup: {archive_name}")

        try:
            # List archive to verify it's readable
            cmd = ['borg', 'list', f"{repo}::{archive_name}"]

            returncode, stdout, stderr = run_command(
                cmd,
                check=True,
                env=self.borg_env,
                timeout=300
            )

            logger.info(f"Backup verified successfully: {archive_name}")
            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Backup verification failed: {e}")
            return False

    def prune_old_backups(self, repo: str) -> bool:
        """
        Prune old backups based on retention policy

        Args:
            repo: Borg repository URL

        Returns:
            True if successful
        """
        logger.info(f"Pruning old backups in repository: {repo}")

        retention = self.borg_config['retention']

        cmd = [
            'borg', 'prune',
            '--verbose',
            '--list',
            '--stats',
            f"--keep-daily={retention['daily']}",
            f"--keep-weekly={retention['weekly']}",
            f"--keep-monthly={retention['monthly']}",
            repo
        ]

        try:
            with CommandExecutor("Pruning old backups"):
                returncode, stdout, stderr = run_command(
                    cmd,
                    check=True,
                    env=self.borg_env,
                    timeout=600
                )

            logger.info("Pruning completed successfully")
            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Pruning failed: {e}")
            return False

    def list_backups(self, repo: str) -> List[Dict[str, str]]:
        """
        List all backups in repository

        Args:
            repo: Borg repository URL

        Returns:
            List of backup information dictionaries
        """
        logger.info(f"Listing backups in repository: {repo}")

        cmd = ['borg', 'list', '--short', repo]

        try:
            returncode, stdout, stderr = run_command(
                cmd,
                check=True,
                env=self.borg_env,
                timeout=60
            )

            backups = []
            for line in stdout.strip().split('\n'):
                if line:
                    backups.append({'name': line.strip()})

            logger.info(f"Found {len(backups)} backups")
            return backups

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to list backups: {e}")
            return []

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
            logger.error(f"nginx directory not found: {nginx_path}")
            return False

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
        mailcow_backup_dir = os.path.join(mailcow_path, 'backups')

        # Pre-backup checks
        if not self._pre_backup_checks('mailcow', required_gb=20):
            return False

        # Check if Mailcow is installed
        if not os.path.exists(mailcow_path):
            logger.error(f"Mailcow directory not found: {mailcow_path}")
            return False

        if not os.path.exists(backup_script):
            logger.error(f"Mailcow backup script not found: {backup_script}")
            return False

        # Ensure backup directory exists
        ensure_directory(mailcow_backup_dir)

        # Set environment variable for backup location
        mailcow_env = os.environ.copy()
        mailcow_env['MAILCOW_BACKUP_LOCATION'] = mailcow_backup_dir

        try:
            # Run Mailcow's official backup script
            with CommandExecutor(f"Mailcow backup ({backup_type})"):
                cmd = [backup_script, 'backup', backup_type]
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
                logger.error("No backup directory created by Mailcow script")
                return False

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
            logger.error(f"Mailcow backup failed: {e}")
            return False
        except subprocess.TimeoutExpired:
            logger.error("Mailcow backup timed out")
            return False

    def get_backup_status(self) -> Dict[str, any]:
        """
        Get status of all backups

        Returns:
            Dictionary with backup status for all services
        """
        status = {}

        for service in ['nginx', 'mailcow', 'server-manager']:
            repo = self._get_borg_repo(service)
            backups = self.list_backups(repo)

            status[service] = {
                'repository': repo,
                'backup_count': len(backups),
                'latest_backup': backups[0]['name'] if backups else None,
                'all_backups': backups
            }

        return status
