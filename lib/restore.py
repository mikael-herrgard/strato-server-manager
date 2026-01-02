"""
Restore Operations Module
Handles restoration from Borg backups for nginx, Mailcow, and application files
"""

import os
import subprocess
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from .utils import (
    logger,
    run_command,
    check_disk_space,
    ensure_directory,
    safe_delete,
    CommandExecutor
)
from .config import get_config


class RestoreManager:
    """Manage restore operations for all services"""

    def __init__(self):
        """Initialize restore manager"""
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

        # Local staging area for downloads
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

    def list_remote_backups(self, service: str) -> List[Dict[str, str]]:
        """
        List available backups from rsync server

        Args:
            service: Service name (nginx, mailcow, server-manager)

        Returns:
            List of backup dictionaries with name and timestamp
        """
        logger.info(f"Listing remote backups for {service}")

        repo = self._get_borg_repo(service)
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
                    backups.append({
                        'name': line.strip(),
                        'service': service
                    })

            logger.info(f"Found {len(backups)} backups for {service}")
            return backups

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to list backups for {service}: {e}")
            return []

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
            logger.error(f"Extraction failed: {e}")
            return False
        except subprocess.TimeoutExpired:
            logger.error(f"Extraction timed out: {archive_name}")
            return False

    def _backup_existing_installation(self, path: str, service: str) -> Optional[str]:
        """
        Create backup of existing installation before restore

        Args:
            path: Path to backup
            service: Service name

        Returns:
            Backup path or None if failed
        """
        if not os.path.exists(path):
            logger.info(f"No existing installation at {path}")
            return None

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = f"{path}.pre-restore.{timestamp}"

        logger.info(f"Backing up existing {service} installation to {backup_path}")

        try:
            if os.path.isdir(path):
                shutil.copytree(path, backup_path, symlinks=True)
            else:
                shutil.copy2(path, backup_path)

            logger.info(f"Existing installation backed up successfully")
            return backup_path

        except Exception as e:
            logger.error(f"Failed to backup existing installation: {e}")
            return None

    def _stop_service(self, service_path: str) -> bool:
        """
        Stop Docker Compose service

        Args:
            service_path: Path to docker-compose.yml directory

        Returns:
            True if successful
        """
        if not os.path.exists(os.path.join(service_path, 'docker-compose.yml')):
            logger.warning(f"No docker-compose.yml found at {service_path}")
            return True

        logger.info(f"Stopping services at {service_path}")

        cmd = ['docker', 'compose', 'down']

        try:
            returncode, stdout, stderr = run_command(
                cmd,
                check=True,
                cwd=service_path,
                timeout=300
            )

            logger.info("Services stopped successfully")
            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to stop services: {e}")
            return False

    def _start_service(self, service_path: str) -> bool:
        """
        Start Docker Compose service

        Args:
            service_path: Path to docker-compose.yml directory

        Returns:
            True if successful
        """
        if not os.path.exists(os.path.join(service_path, 'docker-compose.yml')):
            logger.warning(f"No docker-compose.yml found at {service_path}")
            return True

        logger.info(f"Starting services at {service_path}")

        cmd = ['docker', 'compose', 'up', '-d']

        try:
            returncode, stdout, stderr = run_command(
                cmd,
                check=True,
                cwd=service_path,
                timeout=600
            )

            logger.info("Services started successfully")
            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to start services: {e}")
            return False

    def _verify_service_running(self, service_path: str) -> bool:
        """
        Verify Docker Compose services are running

        Args:
            service_path: Path to docker-compose.yml directory

        Returns:
            True if services are running
        """
        if not os.path.exists(os.path.join(service_path, 'docker-compose.yml')):
            logger.info("No docker-compose.yml to verify")
            return True

        logger.info(f"Verifying services at {service_path}")

        cmd = ['docker', 'compose', 'ps', '--services', '--filter', 'status=running']

        try:
            returncode, stdout, stderr = run_command(
                cmd,
                check=True,
                cwd=service_path,
                timeout=60
            )

            running_services = stdout.strip().split('\n') if stdout.strip() else []

            if running_services and running_services[0]:
                logger.info(f"Services running: {len(running_services)}")
                return True
            else:
                logger.warning("No services are running")
                return False

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to verify services: {e}")
            return False

    def restore_nginx(self, backup_name: str = "latest") -> bool:
        """
        Restore nginx Proxy Manager from backup

        Args:
            backup_name: Backup name to restore ("latest" for most recent)

        Returns:
            True if successful
        """
        logger.info(f"Starting nginx restore (backup: {backup_name})")

        # Get nginx configuration
        nginx_path = self.nginx_config['install_path']
        repo = self._get_borg_repo('nginx')

        # Get backup list
        backups = self.list_remote_backups('nginx')
        if not backups:
            logger.error("No nginx backups found")
            return False

        # Select backup
        if backup_name == "latest":
            selected_backup = backups[0]['name']
            logger.info(f"Using latest backup: {selected_backup}")
        else:
            selected_backup = backup_name

        # Check disk space
        if not check_disk_space(self.local_staging, 5):
            logger.error("Insufficient disk space for restore")
            return False

        # Backup existing installation
        if os.path.exists(nginx_path):
            self._stop_service(nginx_path)
            backup_path = self._backup_existing_installation(nginx_path, 'nginx')

            if backup_path:
                logger.info(f"Existing installation saved to: {backup_path}")

            # Remove existing installation
            logger.info(f"Removing existing installation: {nginx_path}")
            shutil.rmtree(nginx_path)

        # Create temporary extraction directory
        temp_dir = os.path.join(self.local_staging, f'restore-nginx-{datetime.now().strftime("%Y%m%d_%H%M%S")}')
        ensure_directory(temp_dir)

        try:
            # Extract backup
            if not self._extract_backup(repo, selected_backup, temp_dir):
                return False

            # Find extracted nginx directory
            extracted_nginx = os.path.join(temp_dir, nginx_path.lstrip('/'))

            if not os.path.exists(extracted_nginx):
                logger.error(f"nginx directory not found in backup: {extracted_nginx}")
                return False

            # Move to target location
            logger.info(f"Moving nginx installation to: {nginx_path}")
            ensure_directory(os.path.dirname(nginx_path))
            shutil.move(extracted_nginx, nginx_path)

            # Set permissions
            os.system(f"chown -R root:root {nginx_path}")

            # Start service
            self._start_service(nginx_path)

            # Wait a moment for services to start
            import time
            time.sleep(10)

            # Verify services are running
            if self._verify_service_running(nginx_path):
                logger.info("nginx restore completed successfully")
                return True
            else:
                logger.warning("nginx restored but services may not be running properly")
                return True

        except Exception as e:
            logger.error(f"nginx restore failed: {e}", exc_info=True)
            return False
        finally:
            # Cleanup temp directory
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

    def restore_mailcow(self, backup_name: str = "latest") -> bool:
        """
        Restore Mailcow from backup

        Args:
            backup_name: Backup name to restore ("latest" for most recent)

        Returns:
            True if successful
        """
        logger.info(f"Starting Mailcow restore (backup: {backup_name})")

        # Get Mailcow configuration
        mailcow_path = self.mailcow_config['install_path']
        repo = self._get_borg_repo('mailcow')

        # Get backup list
        backups = self.list_remote_backups('mailcow')
        if not backups:
            logger.error("No Mailcow backups found")
            return False

        # Select backup
        if backup_name == "latest":
            selected_backup = backups[0]['name']
            logger.info(f"Using latest backup: {selected_backup}")
        else:
            selected_backup = backup_name

        # Check disk space (Mailcow can be large)
        if not check_disk_space(self.local_staging, 20):
            logger.error("Insufficient disk space for restore")
            return False

        # Backup existing installation
        if os.path.exists(mailcow_path):
            self._stop_service(mailcow_path)
            backup_path = self._backup_existing_installation(mailcow_path, 'mailcow')

            if backup_path:
                logger.info(f"Existing installation saved to: {backup_path}")

        # Create temporary extraction directory
        temp_dir = os.path.join(self.local_staging, f'restore-mailcow-{datetime.now().strftime("%Y%m%d_%H%M%S")}')
        ensure_directory(temp_dir)

        try:
            # Extract backup
            if not self._extract_backup(repo, selected_backup, temp_dir):
                return False

            # The backup contains the Mailcow backup directory structure
            # Find the extracted mailcow backup directory
            extracted_backup = None
            for item in os.listdir(temp_dir):
                item_path = os.path.join(temp_dir, item)
                if os.path.isdir(item_path) and item.startswith('mailcow-'):
                    extracted_backup = item_path
                    break

            if not extracted_backup:
                logger.error("Mailcow backup directory not found in extraction")
                return False

            logger.info(f"Found Mailcow backup: {extracted_backup}")

            # Use Mailcow's official restore script
            restore_script = os.path.join(mailcow_path, 'helper-scripts', 'backup_and_restore.sh')

            if not os.path.exists(restore_script):
                logger.error(f"Mailcow restore script not found: {restore_script}")
                logger.info("Please ensure Mailcow is installed before restoring")
                return False

            # Run Mailcow restore
            logger.info("Running Mailcow restore script...")
            cmd = [restore_script, 'restore', extracted_backup]

            mailcow_env = os.environ.copy()
            returncode, stdout, stderr = run_command(
                cmd,
                check=True,
                cwd=mailcow_path,
                env=mailcow_env,
                timeout=3600  # 1 hour
            )

            logger.info("Mailcow restore completed successfully")

            # Start services
            self._start_service(mailcow_path)

            # Wait for services to start
            import time
            time.sleep(20)

            # Verify services
            if self._verify_service_running(mailcow_path):
                logger.info("Mailcow services are running")
                return True
            else:
                logger.warning("Mailcow restored but services may not be running properly")
                return True

        except Exception as e:
            logger.error(f"Mailcow restore failed: {e}", exc_info=True)
            return False
        finally:
            # Cleanup temp directory
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

