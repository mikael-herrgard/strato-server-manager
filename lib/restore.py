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
    CommandExecutor,
    stop_systemd_service,
    start_systemd_service,
    verify_systemd_service
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
        self.borg_env['BORG_RELOCATED_REPO_ACCESS_IS_OK'] = 'yes'

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
            selected_backup = backups[-1]['name']
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
            run_command(['chown', '-R', 'root:root', nginx_path], check=False, timeout=60)

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
            selected_backup = backups[-1]['name']
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
            # The restore script expects the PARENT directory containing mailcow-* subdirectories
            # Support both old (in /opt/mailcow-dockerized/backups) and new (in /var/backups/mailcow-data) structures
            backup_parent_dir = None
            found_backup_name = None

            # First, check if extraction created nested path structure (old backups)
            old_backup_path = os.path.join(temp_dir, 'opt/mailcow-dockerized/backups')
            if os.path.exists(old_backup_path):
                logger.info("Found old backup structure with nested path")
                for item in os.listdir(old_backup_path):
                    item_path = os.path.join(old_backup_path, item)
                    if os.path.isdir(item_path) and item.startswith('mailcow-'):
                        backup_parent_dir = old_backup_path
                        found_backup_name = item
                        break

            # Try new backup location structure
            if not backup_parent_dir:
                new_backup_path = os.path.join(temp_dir, 'var/backups/mailcow-data')
                if os.path.exists(new_backup_path):
                    logger.info("Found new backup structure with nested path")
                    for item in os.listdir(new_backup_path):
                        item_path = os.path.join(new_backup_path, item)
                        if os.path.isdir(item_path) and item.startswith('mailcow-'):
                            backup_parent_dir = new_backup_path
                            found_backup_name = item
                            break

            # Finally, check directly in temp_dir (for manually extracted backups)
            if not backup_parent_dir:
                for item in os.listdir(temp_dir):
                    item_path = os.path.join(temp_dir, item)
                    if os.path.isdir(item_path) and item.startswith('mailcow-'):
                        backup_parent_dir = temp_dir
                        found_backup_name = item
                        break

            if not backup_parent_dir:
                logger.error("Mailcow backup directory not found in extraction")
                logger.error(f"Checked paths:")
                logger.error(f"  - {old_backup_path}")
                logger.error(f"  - {new_backup_path}")
                logger.error(f"  - {temp_dir}")
                logger.error(f"Contents of temp_dir: {os.listdir(temp_dir)}")
                return False

            logger.info(f"Found Mailcow backup: {found_backup_name} in {backup_parent_dir}")

            # Use Mailcow's official restore script
            restore_script = os.path.join(mailcow_path, 'helper-scripts', 'backup_and_restore.sh')

            if not os.path.exists(restore_script):
                logger.error(f"Mailcow restore script not found: {restore_script}")
                logger.info("Please ensure Mailcow is installed before restoring")
                return False

            # Run Mailcow restore
            logger.info("Running Mailcow restore script...")
            # The script expects "restore" command without path argument
            # It will ask for the backup location via stdin
            cmd = [restore_script, 'restore']

            mailcow_env = os.environ.copy()

            # The mailcow script is interactive and asks:
            # 1. "Backup location (absolute path, starting with /):" - provide the parent directory
            # 2. "Select a restore point:" - provide "1" to select the first mailcow-* folder
            # 3. "Select a dataset to restore:" - provide "0" for all datasets
            # Provide automatic responses to interactive prompts
            input_data = f"{backup_parent_dir}\n1\n0\n"

            logger.info(f"Providing backup location: {backup_parent_dir}")

            returncode, stdout, stderr = run_command(
                cmd,
                check=False,
                cwd=mailcow_path,
                env=mailcow_env,
                timeout=3600,  # 1 hour
                input_data=input_data
            )

            # The mailcow script may return non-zero even on success,
            # so check for actual restore activity in the output
            if returncode != 0:
                # Check if data was actually restored despite exit code
                if 'Restoring' in (stdout or '') or '/vmail/' in (stdout or ''):
                    logger.warning(f"Mailcow restore script exited with code {returncode} but data appears restored")
                else:
                    logger.error(f"Mailcow restore script failed (exit code {returncode})")
                    if stderr:
                        logger.error(f"Stderr: {stderr[:1000]}")
                    return False

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

    def restore_mailcow_directory(self, backup_name: str = "latest") -> bool:
        """
        Restore Mailcow directory (configuration and certificates) from backup

        This restores /opt/mailcow-dockerized including:
        - mailcow.conf
        - docker-compose.yml and related files
        - SSL certificates
        - DKIM keys
        - Configuration files

        Args:
            backup_name: Backup name to restore ("latest" for most recent)

        Returns:
            True if successful
        """
        logger.info(f"Starting Mailcow directory restore (backup: {backup_name})")

        # Get Mailcow configuration
        mailcow_path = self.mailcow_config['install_path']
        repo = self._get_borg_repo('mailcow-directory')

        # Get backup list
        backups = self.list_remote_backups('mailcow-directory')
        if not backups:
            logger.error("No Mailcow directory backups found")
            return False

        # Select backup
        if backup_name == "latest":
            selected_backup = backups[-1]['name']
            logger.info(f"Using latest backup: {selected_backup}")
        else:
            selected_backup = backup_name

        # Check disk space
        if not check_disk_space(self.local_staging, 5):
            logger.error("Insufficient disk space for restore")
            return False

        # Backup existing installation if it exists
        if os.path.exists(mailcow_path):
            # Stop mailcow services first
            logger.info("Stopping Mailcow services...")
            self._stop_service(mailcow_path)

            # Backup existing directory
            backup_path = self._backup_existing_installation(mailcow_path, 'mailcow-directory')
            if backup_path:
                logger.info(f"Existing installation saved to: {backup_path}")

            # Remove existing installation
            logger.info(f"Removing existing installation: {mailcow_path}")
            shutil.rmtree(mailcow_path)

        # Create temporary extraction directory
        temp_dir = os.path.join(
            self.local_staging,
            f'restore-mailcow-directory-{datetime.now().strftime("%Y%m%d_%H%M%S")}'
        )
        ensure_directory(temp_dir)

        try:
            # Extract backup
            if not self._extract_backup(repo, selected_backup, temp_dir):
                return False

            # Find extracted mailcow directory
            extracted_mailcow = os.path.join(temp_dir, mailcow_path.lstrip('/'))

            if not os.path.exists(extracted_mailcow):
                logger.error(f"Mailcow directory not found in backup: {extracted_mailcow}")
                return False

            # Move to target location
            logger.info(f"Moving Mailcow directory to: {mailcow_path}")
            ensure_directory(os.path.dirname(mailcow_path))
            shutil.move(extracted_mailcow, mailcow_path)

            # Set permissions
            logger.info("Setting permissions...")
            run_command(['chown', '-R', 'root:root', mailcow_path], check=False, timeout=60)
            for script in ['generate_config.sh', 'update.sh']:
                script_path = os.path.join(mailcow_path, script)
                if os.path.exists(script_path):
                    os.chmod(script_path, 0o755)

            logger.info("Mailcow directory restore completed successfully")

            # Start services (docker compose up -d will pull images if needed)
            logger.info("Starting Mailcow services...")
            self._start_service(mailcow_path)

            # Wait for services to start
            import time
            time.sleep(20)

            # Verify services are running
            if self._verify_service_running(mailcow_path):
                logger.info("Mailcow services are running")
            else:
                logger.warning("Mailcow restored but services may not be running properly")

            return True

        except Exception as e:
            logger.error(f"Mailcow directory restore failed: {e}", exc_info=True)
            return False
        finally:
            # Cleanup temp directory
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

    def restore_server_manager(self, backup_name: str = "latest") -> bool:
        """
        Restore server-manager configuration files from backup

        Restores /opt/server-manager/config/ (settings.yaml, notifications.yaml)

        Args:
            backup_name: Backup name to restore ("latest" for most recent)

        Returns:
            True if successful
        """
        logger.info(f"Starting server-manager config restore (backup: {backup_name})")

        config_path = '/opt/server-manager/config'
        repo = self._get_borg_repo('server-manager')

        # Get backup list
        backups = self.list_remote_backups('server-manager')
        if not backups:
            logger.error("No server-manager backups found")
            return False

        # Select backup
        if backup_name == "latest":
            selected_backup = backups[-1]['name']
            logger.info(f"Using latest backup: {selected_backup}")
        else:
            selected_backup = backup_name

        # Check disk space
        if not check_disk_space(self.local_staging, 1):
            logger.error("Insufficient disk space for restore")
            return False

        # Backup existing config
        if os.path.exists(config_path):
            backup_path = self._backup_existing_installation(config_path, 'server-manager')
            if backup_path:
                logger.info(f"Existing config saved to: {backup_path}")

        # Create temporary extraction directory
        temp_dir = os.path.join(
            self.local_staging,
            f'restore-server-manager-{datetime.now().strftime("%Y%m%d_%H%M%S")}'
        )
        ensure_directory(temp_dir)

        try:
            # Extract backup
            if not self._extract_backup(repo, selected_backup, temp_dir):
                return False

            # Find extracted config directory
            extracted_config = os.path.join(temp_dir, config_path.lstrip('/'))

            if not os.path.exists(extracted_config):
                logger.error(f"Config directory not found in backup: {extracted_config}")
                return False

            # Restore config files individually (don't overwrite .example files or other non-config)
            restored = 0
            for filename in os.listdir(extracted_config):
                src = os.path.join(extracted_config, filename)
                dst = os.path.join(config_path, filename)
                if os.path.isfile(src):
                    logger.info(f"Restoring: {filename}")
                    shutil.copy2(src, dst)
                    restored += 1

            logger.info(f"Server-manager config restore completed — {restored} file(s) restored")
            return True

        except Exception as e:
            logger.error(f"Server-manager config restore failed: {e}", exc_info=True)
            return False
        finally:
            # Cleanup temp directory
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

    def restore_credentials(self, backup_name: str = "latest") -> bool:
        """
        Restore centralized credentials files from backup

        Restores /root/.credentials.env and /root/.dns-config, sets permissions,
        and syncs certbot credential files.

        Args:
            backup_name: Backup name to restore ("latest" for most recent)

        Returns:
            True if successful
        """
        logger.info(f"Starting credentials restore (backup: {backup_name})")

        repo = self._get_borg_repo('credentials')

        # Get backup list
        backups = self.list_remote_backups('credentials')
        if not backups:
            logger.error("No credentials backups found")
            return False

        # Select backup
        if backup_name == "latest":
            selected_backup = backups[-1]['name']
            logger.info(f"Using latest backup: {selected_backup}")
        else:
            selected_backup = backup_name

        # Check disk space
        if not check_disk_space(self.local_staging, 1):
            logger.error("Insufficient disk space for restore")
            return False

        # Create temporary extraction directory
        temp_dir = os.path.join(
            self.local_staging,
            f'restore-credentials-{datetime.now().strftime("%Y%m%d_%H%M%S")}'
        )
        ensure_directory(temp_dir)

        try:
            # Extract backup
            if not self._extract_backup(repo, selected_backup, temp_dir):
                return False

            # Restore each credentials file
            restored = 0
            for filename in ['.credentials.env', '.dns-config']:
                extracted_path = os.path.join(temp_dir, 'root', filename)
                target_path = f'/root/{filename}'

                if os.path.exists(extracted_path):
                    # Backup existing file if present
                    if os.path.exists(target_path):
                        import shutil
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        shutil.copy2(target_path, f"{target_path}.pre-restore.{timestamp}")

                    import shutil
                    shutil.copy2(extracted_path, target_path)
                    os.chmod(target_path, 0o600)
                    logger.info(f"Restored: {target_path}")
                    restored += 1
                else:
                    logger.warning(f"File not found in backup: {filename}")

            # Sync certbot credentials from restored .credentials.env
            if os.path.exists('/root/.credentials.env'):
                self._sync_certbot_credentials()

            logger.info(f"Credentials restore completed -- {restored} file(s) restored")
            return True

        except Exception as e:
            logger.error(f"Credentials restore failed: {e}", exc_info=True)
            return False
        finally:
            # Cleanup temp directory
            if os.path.exists(temp_dir):
                import shutil
                shutil.rmtree(temp_dir)

    def _sync_certbot_credentials(self):
        """Sync certbot credential files from centralized .credentials.env"""
        try:
            # Read credentials
            credentials = {}
            with open('/root/.credentials.env', 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, _, value = line.partition('=')
                        credentials[key.strip()] = value.strip().strip('"')

            cred_dir = '/root/nginx/letsencrypt/credentials'
            ensure_directory(cred_dir)

            # Cloudflare credentials
            cf_token = credentials.get('CF_API_TOKEN', '')
            if cf_token:
                cf_path = os.path.join(cred_dir, 'credentials-2')
                with open(cf_path, 'w') as f:
                    f.write(f"dns_cloudflare_api_token={cf_token}\n")
                os.chmod(cf_path, 0o600)
                logger.info("Synced Cloudflare certbot credentials")

            # Gandi credentials
            gandi_token = credentials.get('GANDI_TOKEN', '')
            if gandi_token:
                gandi_path = os.path.join(cred_dir, 'credentials-gandi')
                with open(gandi_path, 'w') as f:
                    f.write(f"dns_gandi_token={gandi_token}\n")
                os.chmod(gandi_path, 0o600)
                logger.info("Synced Gandi certbot credentials")

        except Exception as e:
            logger.warning(f"Failed to sync certbot credentials: {e}")

    def _install_monitoring_packages(self) -> bool:
        """
        Install InfluxDB and Grafana packages if not already present.

        Adds the official APT repositories and GPG keys, then installs
        influxdb2, influxdb2-cli, and grafana. Stops services after install
        so the restore can replace their data.

        Returns:
            True if packages are installed (or were already installed)
        """
        # Check if already installed
        influx_installed = subprocess.run(
            ['dpkg', '-s', 'influxdb2'], capture_output=True
        ).returncode == 0
        grafana_installed = subprocess.run(
            ['dpkg', '-s', 'grafana'], capture_output=True
        ).returncode == 0

        if influx_installed and grafana_installed:
            logger.info("InfluxDB and Grafana already installed")
            return True

        logger.info("Installing monitoring stack packages...")

        try:
            # Fix any packages left in a half-configured state (e.g. from a prior timeout)
            run_command(['dpkg', '--configure', '-a'], check=False, timeout=120)

            # Ensure prerequisites
            apt_env = {**os.environ, 'DEBIAN_FRONTEND': 'noninteractive'}
            run_command(
                ['apt-get', 'install', '-y', 'apt-transport-https', 'gnupg', 'curl'],
                check=True, timeout=120, env=apt_env
            )

            if not influx_installed:
                logger.info("Adding InfluxData APT repository...")
                ensure_directory('/usr/share/keyrings')
                run_command(
                    ['bash', '-c',
                     'curl -fsSL https://repos.influxdata.com/influxdata-archive.key '
                     '| gpg --dearmor --yes -o /usr/share/keyrings/influxdb-keyring.gpg'],
                    check=True, timeout=60
                )
                # InfluxData only publishes up to jammy — use that for noble+
                codename = subprocess.check_output(
                    ['lsb_release', '-cs'], text=True
                ).strip()
                influx_codename = codename if codename in ('focal', 'jammy') else 'jammy'
                with open('/etc/apt/sources.list.d/influxdata.list', 'w') as f:
                    f.write(
                        f'deb [signed-by=/usr/share/keyrings/influxdb-keyring.gpg] '
                        f'https://repos.influxdata.com/ubuntu {influx_codename} stable\n'
                    )

            if not grafana_installed:
                logger.info("Adding Grafana APT repository...")
                ensure_directory('/etc/apt/keyrings')
                run_command(
                    ['bash', '-c',
                     'curl -fsSL https://apt.grafana.com/gpg.key '
                     '| gpg --dearmor --yes -o /etc/apt/keyrings/grafana.gpg'],
                    check=True, timeout=60
                )
                with open('/etc/apt/sources.list.d/grafana.list', 'w') as f:
                    f.write(
                        'deb [signed-by=/etc/apt/keyrings/grafana.gpg] '
                        'https://apt.grafana.com stable main\n'
                    )

            # Update and install
            run_command(['apt-get', 'update'], check=True, timeout=120)

            packages = []
            if not influx_installed:
                packages += ['influxdb2', 'influxdb2-cli']
            if not grafana_installed:
                packages += ['grafana']

            run_command(
                ['apt-get', 'install', '-y'] + packages,
                check=True, timeout=600, env=apt_env
            )

            # Stop services — restore will replace data and start them
            for svc in ['influxdb', 'grafana-server']:
                run_command(['systemctl', 'stop', svc], check=False, timeout=30)

            logger.info("Monitoring stack packages installed successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to install monitoring packages: {e}")
            return False

    def restore_monitoring_stack(self, backup_name: str = "latest") -> bool:
        """
        Restore monitoring stack (Grafana, InfluxDB, pressuresuite-influx-bridge) from backup

        Args:
            backup_name: Backup name to restore ("latest" for most recent)

        Returns:
            True if successful
        """
        logger.info(f"Starting monitoring stack restore (backup: {backup_name})")

        # Install packages if not present (needed for fresh DR)
        if not self._install_monitoring_packages():
            logger.error("Failed to install monitoring stack packages")
            return False

        # Get configuration
        monitoring_config = self.config.get_monitoring_stack_config()
        repo = self._get_borg_repo('monitoring-stack')

        # Get backup list
        backups = self.list_remote_backups('monitoring-stack')
        if not backups:
            logger.error("No monitoring stack backups found")
            return False

        # Select backup
        if backup_name == "latest":
            selected_backup = backups[-1]['name']
            logger.info(f"Using latest backup: {selected_backup}")
        else:
            selected_backup = backup_name

        # Check disk space
        if not check_disk_space(self.local_staging, 1):
            logger.error("Insufficient disk space for restore")
            return False

        # Paths to restore
        grafana_data = monitoring_config['grafana_data_path']
        grafana_config = monitoring_config['grafana_config_path']
        influxdb_data = monitoring_config['influxdb_data_path']
        influxdb_config = monitoring_config['influxdb_config_path']
        bridge_path = monitoring_config['bridge_install_path']
        bridge_service = monitoring_config['bridge_service']
        bridge_timer = monitoring_config['bridge_timer']

        # Stop services (if running — on fresh DR they won't be)
        logger.info("Stopping monitoring services...")
        services_to_stop = ['grafana-server', 'influxdb', bridge_timer]
        for svc in services_to_stop:
            stop_systemd_service(svc)

        # Create temporary extraction directory
        temp_dir = os.path.join(
            self.local_staging,
            f'restore-monitoring-stack-{datetime.now().strftime("%Y%m%d_%H%M%S")}'
        )
        ensure_directory(temp_dir)

        try:
            # Backup existing directories
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            for path in [grafana_data, influxdb_data, bridge_path]:
                if os.path.exists(path):
                    backup_path = f"{path}.pre-restore.{timestamp}"
                    logger.info(f"Backing up {path} to {backup_path}")
                    shutil.copytree(path, backup_path, symlinks=True)

            # Extract backup
            if not self._extract_backup(repo, selected_backup, temp_dir):
                return False

            # Restore each component from extracted archive
            restore_mappings = [
                (grafana_data, grafana_data),
                (grafana_config, grafana_config),
                (influxdb_data, influxdb_data),
                (influxdb_config, influxdb_config),
                (bridge_path, bridge_path),
                (os.path.expanduser('~/.influxdbv2'), os.path.expanduser('~/.influxdbv2')),
            ]

            for target_path, source_rel in restore_mappings:
                extracted_path = os.path.join(temp_dir, source_rel.lstrip('/'))

                if not os.path.exists(extracted_path):
                    logger.warning(f"Path not found in backup: {extracted_path}")
                    continue

                # Remove existing and move extracted
                if os.path.exists(target_path):
                    logger.info(f"Removing existing: {target_path}")
                    shutil.rmtree(target_path)

                logger.info(f"Restoring: {target_path}")
                ensure_directory(os.path.dirname(target_path))
                shutil.move(extracted_path, target_path)

            # Restore systemd unit files if present in backup
            for unit_file in [bridge_service, bridge_timer]:
                extracted_unit = os.path.join(temp_dir, 'etc/systemd/system', unit_file)
                target_unit = f"/etc/systemd/system/{unit_file}"
                if os.path.exists(extracted_unit):
                    logger.info(f"Restoring systemd unit: {unit_file}")
                    shutil.copy2(extracted_unit, target_unit)

            # Set permissions
            logger.info("Setting permissions...")
            run_command(['chown', '-R', 'grafana:grafana', grafana_data], check=False, timeout=60)
            run_command(['chown', '-R', 'grafana:grafana', grafana_config], check=False, timeout=60)
            run_command(['chown', '-R', 'influxdb:influxdb', influxdb_data], check=False, timeout=60)
            run_command(['chown', '-R', 'influxdb:influxdb', influxdb_config], check=False, timeout=60)

            # Reload systemd in case units changed
            logger.info("Reloading systemd daemon...")
            run_command(['systemctl', 'daemon-reload'], check=False, timeout=30)

            # Start services
            logger.info("Starting monitoring services...")
            start_systemd_service('influxdb')
            start_systemd_service('grafana-server')

            # Enable and start the bridge timer
            run_command(['systemctl', 'enable', bridge_timer], check=False, timeout=30)
            start_systemd_service(bridge_timer)

            # Wait for services to start
            import time
            time.sleep(5)

            # Verify services
            all_running = True
            for svc in ['influxdb', 'grafana-server']:
                if not verify_systemd_service(svc):
                    logger.warning(f"Service may not be running properly: {svc}")
                    all_running = False

            if all_running:
                logger.info("Monitoring stack restore completed successfully")
            else:
                logger.warning("Monitoring stack restored but some services may not be running properly")

            return True

        except Exception as e:
            logger.error(f"Monitoring stack restore failed: {e}", exc_info=True)
            return False
        finally:
            # Cleanup temp directory
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

