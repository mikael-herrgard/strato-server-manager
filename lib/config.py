"""
Configuration Management Module
Handles loading, validation, and access to configuration settings
"""

import os
import yaml
from pathlib import Path
from typing import Any, Dict, Optional
from .utils import logger, validate_path


class ConfigManager:
    """Manage application configuration"""

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize configuration manager

        Args:
            config_path: Path to settings.yaml (default: /opt/server-manager/config/settings.yaml)
        """
        if config_path is None:
            config_path = "/opt/server-manager/config/settings.yaml"

        self.config_path = config_path
        self.config = {}
        self._load_config()

    def _load_config(self):
        """Load configuration from YAML file"""
        try:
            if not os.path.exists(self.config_path):
                logger.warning(f"Configuration file not found: {self.config_path}")
                logger.info("Using default configuration")
                self.config = self._get_default_config()
                return

            with open(self.config_path, 'r') as f:
                self.config = yaml.safe_load(f)

            logger.info(f"Configuration loaded from: {self.config_path}")

            # Validate configuration
            if not self._validate_config():
                logger.warning("Configuration validation failed, using defaults for missing values")

        except yaml.YAMLError as e:
            logger.error(f"Error parsing YAML configuration: {e}")
            logger.info("Using default configuration")
            self.config = self._get_default_config()

        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            logger.info("Using default configuration")
            self.config = self._get_default_config()

    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration"""
        return {
            'rsync': {
                'host': 'rsync-backup',
                'user': 'root',
                'base_path': '/backups',
                'ssh_key': '/root/.ssh/backup_key'
            },
            'borg': {
                'remote_path': 'borg14',
                'compression': 'zstd,3',
                'retention': {
                    'daily': 7,
                    'weekly': 4,
                    'monthly': 6
                }
            },
            'mailcow': {
                'install_path': '/opt/mailcow-dockerized',
                'backup_types': ['all'],
                'domain': 'mail.example.com'
            },
            'nginx': {
                'install_path': '/root/nginx',
                'domain': 'nginx.example.com'
            },
            'system': {
                'ipv6_enabled': False,
                'auto_updates': False,
                'notification_email': None
            },
            'backup': {
                'local_staging': '/var/backups/local',
                'schedule': {
                    'nginx': '0 2 * * *',      # 2 AM daily
                    'mailcow': '0 3 * * *',    # 3 AM daily
                    'scripts': '0 4 * * 0'     # 4 AM weekly (Sunday)
                }
            }
        }

    def _validate_config(self) -> bool:
        """
        Validate configuration structure

        Returns:
            True if valid
        """
        required_sections = ['rsync', 'borg', 'mailcow', 'nginx', 'system', 'backup']

        for section in required_sections:
            if section not in self.config:
                logger.warning(f"Missing required configuration section: {section}")
                # Add default section
                default = self._get_default_config()
                self.config[section] = default.get(section, {})

        return True

    def save_config(self) -> bool:
        """
        Save current configuration to file

        Returns:
            True if successful
        """
        try:
            # Ensure config directory exists
            config_dir = os.path.dirname(self.config_path)
            Path(config_dir).mkdir(parents=True, exist_ok=True)

            # Create backup of existing config
            if os.path.exists(self.config_path):
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = f"{self.config_path}.backup.{timestamp}"
                import shutil
                shutil.copy2(self.config_path, backup_path)
                logger.info(f"Configuration backed up to: {backup_path}")

            # Write new config
            with open(self.config_path, 'w') as f:
                yaml.dump(self.config, f, default_flow_style=False, sort_keys=False)

            logger.info(f"Configuration saved to: {self.config_path}")
            return True

        except Exception as e:
            logger.error(f"Error saving configuration: {e}")
            return False

    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Get configuration value by dot-notation path

        Args:
            key_path: Dot-separated path (e.g., 'rsync.host')
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        keys = key_path.split('.')
        value = self.config

        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default

        return value

    def set(self, key_path: str, value: Any) -> bool:
        """
        Set configuration value by dot-notation path

        Args:
            key_path: Dot-separated path (e.g., 'rsync.host')
            value: Value to set

        Returns:
            True if successful
        """
        try:
            keys = key_path.split('.')
            config = self.config

            # Navigate to parent
            for key in keys[:-1]:
                if key not in config:
                    config[key] = {}
                config = config[key]

            # Set value
            config[keys[-1]] = value
            logger.debug(f"Configuration updated: {key_path} = {value}")
            return True

        except Exception as e:
            logger.error(f"Error setting configuration {key_path}: {e}")
            return False

    def get_borg_config(self) -> Dict[str, Any]:
        """Get Borg-specific configuration"""
        return {
            'remote_path': self.get('borg.remote_path', 'borg14'),
            'compression': self.get('borg.compression', 'zstd,3'),
            'retention': self.get('borg.retention', {
                'daily': 7,
                'weekly': 4,
                'monthly': 6
            })
        }

    def get_rsync_config(self) -> Dict[str, Any]:
        """Get rsync-specific configuration"""
        return {
            'host': self.get('rsync.host', 'rsync-backup'),
            'user': self.get('rsync.user', 'root'),
            'base_path': self.get('rsync.base_path', '/backups'),
            'ssh_key': self.get('rsync.ssh_key', '/root/.ssh/backup_key')
        }

    def get_mailcow_config(self) -> Dict[str, Any]:
        """Get Mailcow-specific configuration"""
        return {
            'install_path': self.get('mailcow.install_path', '/opt/mailcow-dockerized'),
            'backup_types': self.get('mailcow.backup_types', ['all']),
            'domain': self.get('mailcow.domain', 'mail.example.com')
        }

    def get_nginx_config(self) -> Dict[str, Any]:
        """Get nginx-specific configuration"""
        return {
            'install_path': self.get('nginx.install_path', '/root/nginx'),
            'domain': self.get('nginx.domain', 'nginx.example.com')
        }

    def get_backup_config(self) -> Dict[str, Any]:
        """Get backup-specific configuration"""
        return {
            'local_staging': self.get('backup.local_staging', '/var/backups/local'),
            'schedule': self.get('backup.schedule', {
                'nginx': '0 2 * * *',
                'mailcow': '0 3 * * *',
                'scripts': '0 4 * * 0'
            })
        }

    def get_secret(self, key: str) -> Optional[str]:
        """
        Get secret from environment or encrypted file

        Args:
            key: Secret key name

        Returns:
            Secret value or None
        """
        # First try environment variable
        env_value = os.environ.get(key.upper())
        if env_value:
            return env_value

        # Try .env file in /root
        env_file = '/root/.env'
        if os.path.exists(env_file):
            try:
                with open(env_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('#') or '=' not in line:
                            continue

                        k, v = line.split('=', 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")

                        if k.upper() == key.upper():
                            return v

            except Exception as e:
                logger.error(f"Error reading .env file: {e}")

        # Try .env file in sh-scripts directory
        env_file = '/root/sh-scripts/.env'
        if os.path.exists(env_file):
            try:
                with open(env_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('#') or '=' not in line:
                            continue

                        k, v = line.split('=', 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")

                        if k.upper() == key.upper():
                            return v

            except Exception as e:
                logger.error(f"Error reading .env file: {e}")

        logger.warning(f"Secret not found: {key}")
        return None

    def reload(self):
        """Reload configuration from file"""
        logger.info("Reloading configuration")
        self._load_config()


# Global configuration instance
_config = None


def get_config(config_path: Optional[str] = None) -> ConfigManager:
    """
    Get global configuration instance

    Args:
        config_path: Optional path to configuration file

    Returns:
        ConfigManager instance
    """
    global _config

    if _config is None:
        _config = ConfigManager(config_path)

    return _config
