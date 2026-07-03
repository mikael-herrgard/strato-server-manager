"""
Shared Borg Repository Base
Common Borg environment, repository addressing, and archive operations
used by both BackupManager and RestoreManager. Everything here was
previously duplicated verbatim between backup.py and restore.py.
"""

import os
import subprocess
from typing import Dict, List, Optional, Union
from .utils import (
    logger,
    run_command,
    ensure_directory,
    CommandExecutor
)
from .config import get_config


class BorgRepoBase:
    """Shared Borg repository plumbing for backup and restore managers"""

    # All known service names that have Borg repositories
    BACKUP_SERVICES = ['nginx', 'mailcow', 'mailcow-directory', 'server-manager', 'monitoring-stack', 'credentials']

    def __init__(self):
        """Initialize shared Borg configuration and environment"""
        self.config = get_config()

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
        self.borg_env['BORG_RELOCATED_REPO_ACCESS_IS_OK'] = 'yes'

        # Local staging area
        self.local_staging = self.backup_config['local_staging']
        ensure_directory(self.local_staging)

        # Last failure reason — surfaced in failure notifications by cli.py
        self.last_error: Optional[str] = None

    def _error(self, message: str) -> bool:
        """Log an error, record it as the last failure reason, and return False."""
        logger.error(message)
        self.last_error = message
        return False

    def _get_borg_repo(self, service: str) -> str:
        """
        Get Borg repository URL for a service

        Args:
            service: Service name (nginx, mailcow, ...)

        Returns:
            Borg repository URL
        """
        rsync_host = self.rsync_config['host']
        base_path = self.rsync_config['base_path'].strip('/')

        # Use relative path format (./path) for rsync.net compatibility
        return f"ssh://{rsync_host}/./{base_path}/{service}-backup"

    def _ensure_borg_repo(self, repo: str) -> bool:
        """
        Ensure a Borg repository exists, initializing it if necessary.

        Uses 'borg info' to check existence. If the repo does not exist,
        initializes it with the configured encryption mode.

        Args:
            repo: Borg repository URL

        Returns:
            True if repo exists or was successfully initialized
        """
        logger.info(f"Checking Borg repository: {repo}")

        # Try to access the repo
        try:
            returncode, stdout, stderr = run_command(
                ['borg', 'info', repo],
                check=False,
                env=self.borg_env,
                timeout=60
            )

            if returncode == 0:
                logger.info(f"Borg repository exists: {repo}")
                return True

        except subprocess.TimeoutExpired:
            return self._error(f"Timeout checking Borg repository: {repo}")

        # Repository doesn't exist — initialize it
        encryption = self.borg_config.get('encryption', 'repokey')
        logger.info(f"Initializing Borg repository: {repo} (encryption: {encryption})")

        try:
            returncode, stdout, stderr = run_command(
                ['borg', 'init', f'--encryption={encryption}', repo],
                check=True,
                env=self.borg_env,
                timeout=120
            )

            logger.info(f"Borg repository initialized: {repo}")
            return True

        except subprocess.CalledProcessError as e:
            stderr_tail = (e.stderr or '').strip()[-300:]
            return self._error(f"Failed to initialize Borg repository {repo}: {stderr_tail or e}")
        except subprocess.TimeoutExpired:
            return self._error(f"Timeout initializing Borg repository: {repo}")

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
            stderr_tail = (e.stderr or '').strip()[-300:]
            self._error(f"Failed to list backups in {repo}: {stderr_tail or e}")
            return []

    def list_remote_backups(self, service: str) -> List[Dict[str, str]]:
        """
        List available backups for a service from the rsync server

        Args:
            service: Service name (nginx, mailcow, server-manager, ...)

        Returns:
            List of backup dictionaries with name and service
        """
        logger.info(f"Listing remote backups for {service}")

        repo = self._get_borg_repo(service)
        backups = self.list_backups(repo)

        for backup in backups:
            backup['service'] = service

        logger.info(f"Found {len(backups)} backups for {service}")
        return backups

    def _create_borg_backup(
        self,
        repo: str,
        archive_name: str,
        source_paths: Union[str, List[str]],
        excludes: Optional[List[str]] = None
    ) -> bool:
        """
        Create a Borg backup

        Args:
            repo: Borg repository URL
            archive_name: Archive name
            source_paths: Path or list of paths to backup
            excludes: List of exclude patterns

        Returns:
            True if successful
        """
        logger.info(f"Creating Borg backup: {archive_name}")

        # Normalize to list
        if isinstance(source_paths, str):
            source_paths = [source_paths]

        # Check if all sources exist
        for source_path in source_paths:
            if not os.path.exists(source_path):
                return self._error(f"Source path does not exist: {source_path}")

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

        # Add archive and sources
        cmd.append(f"{repo}::{archive_name}")
        cmd.extend(source_paths)

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
            stderr_tail = (e.stderr or '').strip()[-300:]
            return self._error(f"Borg backup failed (rc={e.returncode}): {stderr_tail or e}")
        except subprocess.TimeoutExpired:
            return self._error(f"Borg backup timed out after 1 hour: {archive_name}")

    def _extract_backup(
        self,
        repo: str,
        archive_name: str,
        extract_path: str
    ) -> bool:
        """
        Extract a Borg backup to specified path

        Args:
            repo: Borg repository URL
            archive_name: Archive name to extract
            extract_path: Path to extract to

        Returns:
            True if successful
        """
        logger.info(f"Extracting backup: {archive_name} to {extract_path}")

        # Ensure extract path exists
        ensure_directory(extract_path)

        # Build command
        cmd = [
            'borg', 'extract',
            '--verbose',
            '--progress',
            f"{repo}::{archive_name}"
        ]

        try:
            with CommandExecutor(f"Extracting backup: {archive_name}"):
                returncode, stdout, stderr = run_command(
                    cmd,
                    check=True,
                    cwd=extract_path,
                    env=self.borg_env,
                    timeout=3600  # 1 hour timeout
                )

            logger.info(f"Extraction completed successfully: {archive_name}")
            return True

        except subprocess.CalledProcessError as e:
            stderr_tail = (e.stderr or '').strip()[-300:]
            return self._error(f"Extraction failed: {stderr_tail or e}")
        except subprocess.TimeoutExpired:
            return self._error(f"Extraction timed out: {archive_name}")

    def verify_backup(self, repo: str, archive_name: str) -> bool:
        """
        Verify backup is listable (existence/readability check)

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
            stderr_tail = (e.stderr or '').strip()[-300:]
            return self._error(f"Backup verification failed for {archive_name}: {stderr_tail or e}")

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

    def check_repository(self, service: str, timeout: int = 3600) -> bool:
        """
        Run 'borg check' against a service's repository.

        Verifies repository segment consistency and archive metadata.
        The heavy repository I/O runs server-side (borg serve on the
        remote), so this does not download archive data. Deliberately
        NOT --verify-data, which would download every byte.

        Args:
            service: Service name (nginx, mailcow, ...)
            timeout: Per-repository timeout in seconds

        Returns:
            True if the repository checks out
        """
        repo = self._get_borg_repo(service)
        logger.info(f"Running borg check on repository: {repo}")

        try:
            with CommandExecutor(f"Borg check: {service}"):
                returncode, stdout, stderr = run_command(
                    ['borg', 'check', repo],
                    check=True,
                    env=self.borg_env,
                    timeout=timeout
                )

            logger.info(f"Repository check passed: {service}")
            return True

        except subprocess.CalledProcessError as e:
            stderr_tail = (e.stderr or '').strip()[-500:]
            return self._error(
                f"borg check FAILED for {service} ({repo}): {stderr_tail or e}"
            )
        except subprocess.TimeoutExpired:
            return self._error(
                f"borg check timed out after {timeout}s for {service} ({repo})"
            )

    def check_all_repositories(self, timeout: int = 3600) -> Dict[str, bool]:
        """
        Run 'borg check' against every known service repository.

        Args:
            timeout: Per-repository timeout in seconds

        Returns:
            Dictionary mapping service name to check result
        """
        logger.info("Checking integrity of all Borg repositories")

        results = {}
        errors = []
        for service in self.BACKUP_SERVICES:
            results[service] = self.check_repository(service, timeout=timeout)
            if not results[service] and self.last_error:
                errors.append(self.last_error)

        failed = [s for s, ok in results.items() if not ok]
        if failed:
            # Collect all failure reasons, not just the last one
            self.last_error = '; '.join(errors) or f"check failed for: {', '.join(failed)}"
            logger.error(f"Repository check failures: {', '.join(failed)}")
        else:
            logger.info("All repository checks passed")

        return results
