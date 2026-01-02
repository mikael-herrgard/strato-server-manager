"""
System Configuration Module
Handles IPv6, firewall, network, and system settings
"""

import os
import re
import shutil
import subprocess
from datetime import datetime
from typing import Dict, List, Optional
from .utils import (
    logger,
    run_command,
    CommandExecutor
)
from .config import get_config


class SystemConfigManager:
    """Manage system configuration"""

    def __init__(self):
        """Initialize system config manager"""
        self.config = get_config()

    def check_ipv6_status(self) -> Dict[str, any]:
        """
        Check current IPv6 status

        Returns:
            Dictionary with IPv6 status information
        """
        logger.info("Checking IPv6 status")

        status = {
            'enabled': False,
            'interfaces_with_ipv6': [],
            'grub_disabled': False
        }

        # Check if IPv6 is enabled in kernel
        try:
            with open('/proc/sys/net/ipv6/conf/all/disable_ipv6', 'r') as f:
                disabled = f.read().strip()
                status['enabled'] = (disabled == '0')
        except Exception as e:
            logger.error(f"Failed to check IPv6 status: {e}")

        # Check network interfaces for IPv6 addresses
        try:
            returncode, stdout, stderr = run_command(
                ['ip', '-6', 'addr', 'show'],
                check=False,
                timeout=10
            )
            if returncode == 0:
                # Parse output for interfaces with IPv6
                current_iface = None
                for line in stdout.split('\n'):
                    if not line.startswith(' '):
                        # Interface line
                        match = re.match(r'^\d+:\s+(\S+):', line)
                        if match:
                            current_iface = match.group(1)
                    elif 'inet6' in line and current_iface:
                        # IPv6 address found
                        if 'scope global' in line and current_iface not in status['interfaces_with_ipv6']:
                            status['interfaces_with_ipv6'].append(current_iface)
        except Exception as e:
            logger.error(f"Failed to check network interfaces: {e}")

        # Check GRUB configuration
        grub_path = '/etc/default/grub'
        if os.path.exists(grub_path):
            try:
                with open(grub_path, 'r') as f:
                    content = f.read()
                    # Check if ipv6.disable=1 is in GRUB_CMDLINE_LINUX
                    if 'ipv6.disable=1' in content:
                        status['grub_disabled'] = True
            except Exception as e:
                logger.error(f"Failed to read GRUB config: {e}")

        return status

    def disable_ipv6(self) -> bool:
        """
        Disable IPv6 via GRUB configuration

        Returns:
            True if successful (requires reboot)
        """
        logger.info("Disabling IPv6 via GRUB")

        grub_path = '/etc/default/grub'

        # Check current status
        status = self.check_ipv6_status()
        if status['grub_disabled']:
            logger.info("IPv6 is already disabled in GRUB configuration")
            return True

        # Backup GRUB configuration
        backup_path = f"{grub_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        try:
            shutil.copy2(grub_path, backup_path)
            logger.info(f"GRUB configuration backed up to: {backup_path}")
        except Exception as e:
            logger.error(f"Failed to backup GRUB config: {e}")
            return False

        try:
            with CommandExecutor("Disabling IPv6"):
                # Read current GRUB config
                with open(grub_path, 'r') as f:
                    lines = f.readlines()

                # Modify GRUB_CMDLINE_LINUX
                modified = False
                new_lines = []

                for line in lines:
                    if line.startswith('GRUB_CMDLINE_LINUX='):
                        # Extract current value
                        match = re.match(r'GRUB_CMDLINE_LINUX="([^"]*)"', line)
                        if match:
                            current_params = match.group(1)
                            # Add ipv6.disable=1 if not present
                            if 'ipv6.disable=1' not in current_params:
                                if current_params:
                                    new_params = f"{current_params} ipv6.disable=1"
                                else:
                                    new_params = "ipv6.disable=1"
                                new_line = f'GRUB_CMDLINE_LINUX="{new_params}"\n'
                                new_lines.append(new_line)
                                modified = True
                                logger.info(f"Modified GRUB_CMDLINE_LINUX: {new_params}")
                            else:
                                new_lines.append(line)
                        else:
                            new_lines.append(line)
                    else:
                        new_lines.append(line)

                if not modified:
                    logger.error("Failed to modify GRUB configuration")
                    return False

                # Write modified config
                with open(grub_path, 'w') as f:
                    f.writelines(new_lines)

                logger.info("GRUB configuration updated")

                # Update GRUB
                logger.info("Running update-grub...")
                returncode, stdout, stderr = run_command(
                    ['update-grub'],
                    check=True,
                    timeout=60
                )

                logger.info("GRUB updated successfully")
                logger.info("IPv6 will be disabled after reboot")
                return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to update GRUB: {e}")
            # Restore backup
            try:
                shutil.copy2(backup_path, grub_path)
                logger.info("GRUB configuration restored from backup")
            except Exception as restore_error:
                logger.error(f"Failed to restore backup: {restore_error}")
            return False
        except Exception as e:
            logger.error(f"Failed to disable IPv6: {e}")
            return False

    def enable_ipv6(self) -> bool:
        """
        Enable IPv6 via GRUB configuration

        Returns:
            True if successful (requires reboot)
        """
        logger.info("Enabling IPv6 via GRUB")

        grub_path = '/etc/default/grub'

        # Check current status
        status = self.check_ipv6_status()
        if not status['grub_disabled']:
            logger.info("IPv6 is already enabled in GRUB configuration")
            return True

        # Backup GRUB configuration
        backup_path = f"{grub_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        try:
            shutil.copy2(grub_path, backup_path)
            logger.info(f"GRUB configuration backed up to: {backup_path}")
        except Exception as e:
            logger.error(f"Failed to backup GRUB config: {e}")
            return False

        try:
            with CommandExecutor("Enabling IPv6"):
                # Read current GRUB config
                with open(grub_path, 'r') as f:
                    lines = f.readlines()

                # Modify GRUB_CMDLINE_LINUX
                modified = False
                new_lines = []

                for line in lines:
                    if line.startswith('GRUB_CMDLINE_LINUX='):
                        # Extract current value
                        match = re.match(r'GRUB_CMDLINE_LINUX="([^"]*)"', line)
                        if match:
                            current_params = match.group(1)
                            # Remove ipv6.disable=1
                            new_params = current_params.replace('ipv6.disable=1', '').strip()
                            # Clean up double spaces
                            new_params = re.sub(r'\s+', ' ', new_params).strip()
                            new_line = f'GRUB_CMDLINE_LINUX="{new_params}"\n'
                            new_lines.append(new_line)
                            modified = True
                            logger.info(f"Modified GRUB_CMDLINE_LINUX: {new_params}")
                        else:
                            new_lines.append(line)
                    else:
                        new_lines.append(line)

                if not modified:
                    logger.error("Failed to modify GRUB configuration")
                    return False

                # Write modified config
                with open(grub_path, 'w') as f:
                    f.writelines(new_lines)

                logger.info("GRUB configuration updated")

                # Update GRUB
                logger.info("Running update-grub...")
                returncode, stdout, stderr = run_command(
                    ['update-grub'],
                    check=True,
                    timeout=60
                )

                logger.info("GRUB updated successfully")
                logger.info("IPv6 will be enabled after reboot")
                return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to update GRUB: {e}")
            # Restore backup
            try:
                shutil.copy2(backup_path, grub_path)
                logger.info("GRUB configuration restored from backup")
            except Exception as restore_error:
                logger.error(f"Failed to restore backup: {restore_error}")
            return False
        except Exception as e:
            logger.error(f"Failed to enable IPv6: {e}")
            return False

    def check_firewall_status(self) -> Dict[str, any]:
        """
        Check UFW firewall status

        Returns:
            Dictionary with firewall status
        """
        logger.info("Checking firewall status")

        status = {
            'ufw_installed': False,
            'ufw_active': False,
            'rules': []
        }

        # Check if ufw is installed
        try:
            returncode, stdout, stderr = run_command(
                ['which', 'ufw'],
                check=False,
                timeout=5
            )
            status['ufw_installed'] = (returncode == 0)
        except Exception:
            status['ufw_installed'] = False

        if not status['ufw_installed']:
            return status

        # Check if ufw is active
        try:
            returncode, stdout, stderr = run_command(
                ['ufw', 'status'],
                check=False,
                timeout=10
            )
            if returncode == 0:
                status['ufw_active'] = 'Status: active' in stdout
                # Parse rules
                for line in stdout.split('\n'):
                    if line and not line.startswith('Status:') and not line.startswith('To'):
                        if line.strip() and '---' not in line:
                            status['rules'].append(line.strip())
        except Exception as e:
            logger.error(f"Failed to check firewall status: {e}")

        return status

    def configure_firewall(self, preset: str = "mailcow") -> bool:
        """
        Configure UFW firewall with preset rules

        Args:
            preset: Firewall preset ('mailcow', 'nginx', 'basic', 'custom')

        Returns:
            True if successful
        """
        logger.info(f"Configuring firewall with preset: {preset}")

        # Install ufw if not present
        status = self.check_firewall_status()
        if not status['ufw_installed']:
            logger.info("Installing UFW...")
            try:
                returncode, stdout, stderr = run_command(
                    ['apt-get', 'install', '-y', 'ufw'],
                    check=True,
                    timeout=300
                )
            except Exception as e:
                logger.error(f"Failed to install UFW: {e}")
                return False

        try:
            with CommandExecutor("Configuring firewall"):
                # Reset firewall (if already configured)
                if status['ufw_active']:
                    logger.info("Resetting existing firewall rules...")
                    run_command(['ufw', '--force', 'reset'], check=True, timeout=30)

                # Set default policies
                logger.info("Setting default policies...")
                run_command(['ufw', 'default', 'deny', 'incoming'], check=True, timeout=10)
                run_command(['ufw', 'default', 'allow', 'outgoing'], check=True, timeout=10)

                # Allow SSH (critical!)
                logger.info("Allowing SSH...")
                run_command(['ufw', 'allow', '22/tcp'], check=True, timeout=10)

                # Apply preset rules
                if preset == 'mailcow':
                    logger.info("Applying Mailcow rules...")
                    ports = [
                        ('80/tcp', 'HTTP'),
                        ('443/tcp', 'HTTPS'),
                        ('25/tcp', 'SMTP'),
                        ('465/tcp', 'SMTPS'),
                        ('587/tcp', 'Submission'),
                        ('110/tcp', 'POP3'),
                        ('995/tcp', 'POP3S'),
                        ('143/tcp', 'IMAP'),
                        ('993/tcp', 'IMAPS'),
                        ('4190/tcp', 'Sieve')
                    ]
                    for port, description in ports:
                        logger.info(f"Allowing {description} ({port})...")
                        run_command(['ufw', 'allow', port], check=True, timeout=10)

                elif preset == 'nginx':
                    logger.info("Applying nginx rules...")
                    ports = [
                        ('80/tcp', 'HTTP'),
                        ('443/tcp', 'HTTPS'),
                        ('81/tcp', 'nginx Admin')
                    ]
                    for port, description in ports:
                        logger.info(f"Allowing {description} ({port})...")
                        run_command(['ufw', 'allow', port], check=True, timeout=10)

                elif preset == 'basic':
                    logger.info("Applying basic rules...")
                    ports = [
                        ('80/tcp', 'HTTP'),
                        ('443/tcp', 'HTTPS')
                    ]
                    for port, description in ports:
                        logger.info(f"Allowing {description} ({port})...")
                        run_command(['ufw', 'allow', port], check=True, timeout=10)

                # Enable firewall
                logger.info("Enabling firewall...")
                returncode, stdout, stderr = run_command(
                    ['ufw', '--force', 'enable'],
                    check=True,
                    timeout=30
                )

                # Show status
                returncode, stdout, stderr = run_command(
                    ['ufw', 'status', 'verbose'],
                    check=True,
                    timeout=10
                )
                logger.info(f"Firewall status:\n{stdout}")

                logger.info("Firewall configured successfully")
                return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to configure firewall: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error configuring firewall: {e}")
            return False

    def add_firewall_rule(self, port: str, protocol: str = 'tcp', comment: str = '') -> bool:
        """
        Add a custom firewall rule

        Args:
            port: Port number
            protocol: Protocol (tcp or udp)
            comment: Optional comment

        Returns:
            True if successful
        """
        logger.info(f"Adding firewall rule: {port}/{protocol}")

        try:
            rule = f"{port}/{protocol}"
            returncode, stdout, stderr = run_command(
                ['ufw', 'allow', rule],
                check=True,
                timeout=10
            )

            logger.info(f"Rule added: {rule}")
            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to add rule: {e}")
            return False

    def remove_firewall_rule(self, port: str, protocol: str = 'tcp') -> bool:
        """
        Remove a firewall rule

        Args:
            port: Port number
            protocol: Protocol (tcp or udp)

        Returns:
            True if successful
        """
        logger.info(f"Removing firewall rule: {port}/{protocol}")

        try:
            rule = f"{port}/{protocol}"
            returncode, stdout, stderr = run_command(
                ['ufw', 'delete', 'allow', rule],
                check=True,
                timeout=10
            )

            logger.info(f"Rule removed: {rule}")
            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to remove rule: {e}")
            return False

    def disable_firewall(self) -> bool:
        """
        Disable UFW firewall

        Returns:
            True if successful
        """
        logger.info("Disabling firewall")

        try:
            returncode, stdout, stderr = run_command(
                ['ufw', 'disable'],
                check=True,
                timeout=30
            )

            logger.info("Firewall disabled")
            return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to disable firewall: {e}")
            return False
