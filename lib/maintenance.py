"""
Maintenance Module
Handles updates, cleanup, and maintenance operations
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
    CommandExecutor
)
from .config import get_config


class MaintenanceManager:
    """Manage maintenance operations"""

    def __init__(self):
        """Initialize maintenance manager"""
        self.config = get_config()
        self.nginx_config = self.config.get_nginx_config()
        self.mailcow_config = self.config.get_mailcow_config()

    def update_nginx(self, backup_first: bool = True) -> bool:
        """
        Update nginx Proxy Manager

        Args:
            backup_first: Create backup before update

        Returns:
            True if successful
        """
        logger.info("Starting nginx Proxy Manager update")

        nginx_path = self.nginx_config['install_path']

        if not os.path.exists(nginx_path):
            logger.error(f"nginx directory not found: {nginx_path}")
            return False

        compose_file = os.path.join(nginx_path, 'docker-compose.yml')
        if not os.path.exists(compose_file):
            logger.error(f"docker-compose.yml not found: {compose_file}")
            return False

        try:
            with CommandExecutor("Updating nginx Proxy Manager"):
                # Create backup if requested
                if backup_first:
                    logger.info("Creating pre-update backup...")
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    backup_path = f"{nginx_path}.pre-update.{timestamp}"

                    shutil.copytree(nginx_path, backup_path, symlinks=True)
                    logger.info(f"Backup created at: {backup_path}")

                # Pull latest images
                logger.info("Pulling latest nginx Proxy Manager image...")
                returncode, stdout, stderr = run_command(
                    ['docker', 'compose', 'pull'],
                    check=True,
                    cwd=nginx_path,
                    timeout=600
                )

                # Restart containers with new image
                logger.info("Restarting nginx Proxy Manager...")
                returncode, stdout, stderr = run_command(
                    ['docker', 'compose', 'up', '-d'],
                    check=True,
                    cwd=nginx_path,
                    timeout=300
                )

                # Wait a moment for startup
                import time
                time.sleep(5)

                # Verify containers are running
                returncode, stdout, stderr = run_command(
                    ['docker', 'compose', 'ps', '--format', 'json'],
                    check=True,
                    cwd=nginx_path,
                    timeout=30
                )

                # Check if any containers are not running
                if 'running' not in stdout.lower():
                    logger.error("Containers not running after update")
                    return False

                logger.info("nginx Proxy Manager updated successfully")
                return True

        except subprocess.CalledProcessError as e:
            logger.error(f"nginx update failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during nginx update: {e}")
            return False

    def rollback_nginx(self) -> Optional[str]:
        """
        Rollback nginx to previous backup

        Returns:
            Backup path used for rollback, or None if failed
        """
        logger.info("Starting nginx rollback")

        nginx_path = self.nginx_config['install_path']
        parent_dir = os.path.dirname(nginx_path)

        # Find most recent backup
        backups = []
        for item in os.listdir(parent_dir):
            if item.startswith(os.path.basename(nginx_path) + '.pre-update.'):
                backup_path = os.path.join(parent_dir, item)
                if os.path.isdir(backup_path):
                    backups.append(backup_path)

        if not backups:
            logger.error("No nginx backups found for rollback")
            return None

        # Get most recent backup
        latest_backup = max(backups, key=os.path.getmtime)
        logger.info(f"Rolling back to: {latest_backup}")

        try:
            with CommandExecutor("Rolling back nginx"):
                # Stop current containers
                logger.info("Stopping current nginx containers...")
                run_command(
                    ['docker', 'compose', 'down'],
                    check=False,
                    cwd=nginx_path,
                    timeout=120
                )

                # Move current installation to .rollback
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                rollback_save = f"{nginx_path}.rollback.{timestamp}"
                shutil.move(nginx_path, rollback_save)
                logger.info(f"Current installation saved to: {rollback_save}")

                # Restore from backup
                shutil.copytree(latest_backup, nginx_path, symlinks=True)
                logger.info(f"Restored from backup: {latest_backup}")

                # Start containers
                logger.info("Starting nginx containers...")
                returncode, stdout, stderr = run_command(
                    ['docker', 'compose', 'up', '-d'],
                    check=True,
                    cwd=nginx_path,
                    timeout=300
                )

                logger.info("nginx rollback completed successfully")
                return latest_backup

        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            return None

    def update_mailcow(self) -> bool:
        """
        Update Mailcow using official update script

        Returns:
            True if successful
        """
        logger.info("Starting Mailcow update")

        mailcow_path = self.mailcow_config['install_path']

        if not os.path.exists(mailcow_path):
            logger.error(f"Mailcow directory not found: {mailcow_path}")
            return False

        update_script = os.path.join(mailcow_path, 'update.sh')
        if not os.path.exists(update_script):
            logger.error(f"Mailcow update script not found: {update_script}")
            return False

        try:
            with CommandExecutor("Updating Mailcow"):
                # Mailcow's official update script handles everything
                logger.info("Running Mailcow update script...")
                logger.info("This may take 10-20 minutes...")

                returncode, stdout, stderr = run_command(
                    ['bash', update_script],
                    check=True,
                    cwd=mailcow_path,
                    timeout=1800  # 30 minutes
                )

                logger.info("Mailcow update completed successfully")
                logger.info("Output:\n" + stdout[-500:])  # Last 500 chars
                return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Mailcow update failed: {e}")
            logger.error(f"Stderr: {e.stderr if hasattr(e, 'stderr') else 'N/A'}")
            return False
        except subprocess.TimeoutExpired:
            logger.error("Mailcow update timed out (30 minutes)")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during Mailcow update: {e}")
            return False

    def update_system_packages(self, security_only: bool = False) -> bool:
        """
        Update system packages

        Args:
            security_only: Only install security updates

        Returns:
            True if successful
        """
        logger.info(f"Starting system package update (security_only={security_only})")

        try:
            with CommandExecutor("Updating system packages"):
                # Update package index
                logger.info("Updating package index...")
                returncode, stdout, stderr = run_command(
                    ['apt-get', 'update'],
                    check=True,
                    timeout=300
                )

                if security_only:
                    # Use unattended-upgrades for security updates only
                    logger.info("Installing security updates only...")
                    returncode, stdout, stderr = run_command(
                        ['unattended-upgrade', '-d'],
                        check=True,
                        timeout=1800  # 30 minutes
                    )
                else:
                    # Full system upgrade
                    logger.info("Upgrading all packages...")
                    returncode, stdout, stderr = run_command(
                        ['apt-get', 'upgrade', '-y'],
                        check=True,
                        timeout=1800  # 30 minutes
                    )

                # Autoremove unnecessary packages
                logger.info("Removing unnecessary packages...")
                returncode, stdout, stderr = run_command(
                    ['apt-get', 'autoremove', '-y'],
                    check=True,
                    timeout=300
                )

                # Clean package cache
                logger.info("Cleaning package cache...")
                returncode, stdout, stderr = run_command(
                    ['apt-get', 'clean'],
                    check=True,
                    timeout=60
                )

                logger.info("System package update completed successfully")
                return True

        except subprocess.CalledProcessError as e:
            logger.error(f"System update failed: {e}")
            return False
        except subprocess.TimeoutExpired:
            logger.error("System update timed out")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during system update: {e}")
            return False

    def cleanup_docker(self) -> Dict[str, any]:
        """
        Clean up Docker resources (images, containers, volumes)

        Returns:
            Dictionary with cleanup statistics
        """
        logger.info("Starting Docker cleanup")

        stats = {
            'images_removed': 0,
            'containers_removed': 0,
            'volumes_removed': 0,
            'space_freed': '0B',
            'success': False
        }

        try:
            with CommandExecutor("Cleaning up Docker"):
                # Get initial disk usage
                returncode, stdout_before, stderr = run_command(
                    ['docker', 'system', 'df'],
                    check=True,
                    timeout=30
                )

                # Remove unused containers
                logger.info("Removing stopped containers...")
                returncode, stdout, stderr = run_command(
                    ['docker', 'container', 'prune', '-f'],
                    check=True,
                    timeout=60
                )
                if 'Total reclaimed space' in stdout:
                    stats['containers_removed'] = stdout.count('Deleted')

                # Remove unused images
                logger.info("Removing unused images...")
                returncode, stdout, stderr = run_command(
                    ['docker', 'image', 'prune', '-a', '-f'],
                    check=True,
                    timeout=300
                )
                if 'Total reclaimed space' in stdout:
                    # Parse space freed
                    import re
                    match = re.search(r'Total reclaimed space: (.+)', stdout)
                    if match:
                        stats['space_freed'] = match.group(1)

                # Remove unused volumes
                logger.info("Removing unused volumes...")
                returncode, stdout, stderr = run_command(
                    ['docker', 'volume', 'prune', '-f'],
                    check=True,
                    timeout=60
                )
                if 'Total reclaimed space' in stdout:
                    stats['volumes_removed'] = stdout.count('Deleted')

                # Remove unused networks
                logger.info("Removing unused networks...")
                returncode, stdout, stderr = run_command(
                    ['docker', 'network', 'prune', '-f'],
                    check=True,
                    timeout=60
                )

                # Get final disk usage
                returncode, stdout_after, stderr = run_command(
                    ['docker', 'system', 'df'],
                    check=True,
                    timeout=30
                )

                stats['success'] = True
                logger.info(f"Docker cleanup completed: {stats['space_freed']} freed")
                return stats

        except subprocess.CalledProcessError as e:
            logger.error(f"Docker cleanup failed: {e}")
            return stats
        except Exception as e:
            logger.error(f"Unexpected error during Docker cleanup: {e}")
            return stats

    def cleanup_old_backups(self, keep_days: int = 7) -> Dict[str, any]:
        """
        Clean up old pre-update and pre-restore backups

        Args:
            keep_days: Number of days to keep backups

        Returns:
            Dictionary with cleanup statistics
        """
        logger.info(f"Cleaning up backups older than {keep_days} days")

        stats = {
            'backups_removed': 0,
            'space_freed_mb': 0,
            'success': False
        }

        nginx_path = self.nginx_config['install_path']
        mailcow_path = self.mailcow_config['install_path']
        app_path = '/opt/server-manager'

        backup_patterns = [
            '.pre-update.',
            '.pre-restore.',
            '.rollback.'
        ]

        try:
            cutoff_time = datetime.now().timestamp() - (keep_days * 86400)

            for base_path in [nginx_path, mailcow_path, app_path]:
                parent_dir = os.path.dirname(base_path)
                base_name = os.path.basename(base_path)

                if not os.path.exists(parent_dir):
                    continue

                for item in os.listdir(parent_dir):
                    # Check if it's a backup directory
                    is_backup = any(pattern in item for pattern in backup_patterns)
                    if not is_backup or not item.startswith(base_name):
                        continue

                    backup_path = os.path.join(parent_dir, item)
                    if not os.path.isdir(backup_path):
                        continue

                    # Check age
                    mtime = os.path.getmtime(backup_path)
                    if mtime < cutoff_time:
                        # Get size before deletion
                        try:
                            size_mb = sum(
                                os.path.getsize(os.path.join(dirpath, filename))
                                for dirpath, dirnames, filenames in os.walk(backup_path)
                                for filename in filenames
                            ) / (1024 * 1024)
                        except Exception:
                            size_mb = 0

                        # Remove old backup
                        logger.info(f"Removing old backup: {backup_path}")
                        shutil.rmtree(backup_path)
                        stats['backups_removed'] += 1
                        stats['space_freed_mb'] += size_mb

            stats['success'] = True
            logger.info(f"Cleanup completed: {stats['backups_removed']} backups removed, "
                       f"{stats['space_freed_mb']:.1f} MB freed")
            return stats

        except Exception as e:
            logger.error(f"Backup cleanup failed: {e}")
            return stats

    def check_updates_available(self) -> Dict[str, any]:
        """
        Check if updates are available for system packages

        Returns:
            Dictionary with update information
        """
        logger.info("Checking for available updates")

        info = {
            'updates_available': 0,
            'security_updates': 0,
            'packages': [],
            'success': False
        }

        try:
            # Update package index
            returncode, stdout, stderr = run_command(
                ['apt-get', 'update'],
                check=True,
                timeout=300
            )

            # Check for available updates
            returncode, stdout, stderr = run_command(
                ['apt-get', 'upgrade', '-s'],  # Simulate
                check=True,
                timeout=60
            )

            # Parse output
            for line in stdout.split('\n'):
                if 'upgraded,' in line:
                    # Example: "10 upgraded, 0 newly installed, 0 to remove"
                    parts = line.split()
                    if len(parts) > 0:
                        try:
                            info['updates_available'] = int(parts[0])
                        except ValueError:
                            pass

            # Check for security updates
            try:
                returncode, stdout, stderr = run_command(
                    ['apt-get', 'upgrade', '-s', '-o', 'Dir::Etc::SourceList=/etc/apt/sources.list.d/security.list'],
                    check=False,
                    timeout=60
                )
                # Count security updates (rough estimate)
                info['security_updates'] = stdout.count('Inst ')
            except Exception:
                pass

            info['success'] = True
            logger.info(f"Update check completed: {info['updates_available']} updates available")
            return info

        except Exception as e:
            logger.error(f"Update check failed: {e}")
            return info

    def restart_service(self, service: str) -> bool:
        """
        Restart a service (nginx or mailcow)

        Args:
            service: Service name ('nginx' or 'mailcow')

        Returns:
            True if successful
        """
        logger.info(f"Restarting {service}")

        if service == 'nginx':
            path = self.nginx_config['install_path']
        elif service == 'mailcow':
            path = self.mailcow_config['install_path']
        else:
            logger.error(f"Unknown service: {service}")
            return False

        if not os.path.exists(path):
            logger.error(f"Service directory not found: {path}")
            return False

        try:
            with CommandExecutor(f"Restarting {service}"):
                # Restart using docker compose
                returncode, stdout, stderr = run_command(
                    ['docker', 'compose', 'restart'],
                    check=True,
                    cwd=path,
                    timeout=300
                )

                logger.info(f"{service} restarted successfully")
                return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to restart {service}: {e}")
            return False
