"""
Utility Functions Module
Provides logging, command execution, and common utilities
"""

import logging
import logging.handlers
import subprocess
import os
import shutil
from typing import Tuple, Optional, List
from pathlib import Path


class ServerManagerLogger:
    """Centralized logging for server manager"""

    _instance = None
    _logger = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._logger is None:
            self._setup_logger()

    def _setup_logger(self):
        """Set up logging with file and syslog handlers"""
        self._logger = logging.getLogger('server_manager')
        self._logger.setLevel(logging.INFO)

        # Prevent duplicate handlers
        if self._logger.handlers:
            return

        # File handler with rotation
        log_dir = Path('/opt/server-manager/logs')
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / 'server-manager.log'

        fh = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        fh.setLevel(logging.INFO)

        # Syslog handler
        try:
            sh = logging.handlers.SysLogHandler(address='/dev/log')
            sh.setLevel(logging.WARNING)  # Only warnings and errors to syslog
        except Exception:
            sh = None  # Syslog not available

        # Formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        fh.setFormatter(formatter)
        if sh:
            sh.setFormatter(formatter)

        # Add handlers
        self._logger.addHandler(fh)
        if sh:
            self._logger.addHandler(sh)

    def get_logger(self):
        """Get the logger instance"""
        return self._logger


# Global logger instance
logger = ServerManagerLogger().get_logger()


def run_command(
    cmd: List[str],
    check: bool = True,
    capture_output: bool = True,
    timeout: Optional[int] = None,
    cwd: Optional[str] = None,
    env: Optional[dict] = None,
    input_data: Optional[str] = None
) -> Tuple[int, str, str]:
    """
    Execute a shell command safely

    Args:
        cmd: Command as list of strings
        check: Raise exception on non-zero exit
        capture_output: Capture stdout/stderr
        timeout: Command timeout in seconds
        cwd: Working directory
        env: Environment variables
        input_data: Data to pass to stdin

    Returns:
        Tuple of (return_code, stdout, stderr)

    Raises:
        subprocess.CalledProcessError: If check=True and command fails
        subprocess.TimeoutExpired: If timeout exceeded
    """
    logger.info(f"Executing command: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd,
            check=check,
            capture_output=capture_output,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env=env,
            input=input_data
        )

        logger.debug(f"Command completed with return code: {result.returncode}")

        if capture_output:
            return result.returncode, result.stdout, result.stderr
        else:
            return result.returncode, "", ""

    except subprocess.CalledProcessError as e:
        logger.error(f"Command failed: {' '.join(cmd)}")
        logger.error(f"Return code: {e.returncode}")
        if capture_output:
            logger.error(f"Stdout: {e.stdout}")
            logger.error(f"Stderr: {e.stderr}")
        raise

    except subprocess.TimeoutExpired as e:
        logger.error(f"Command timed out after {timeout}s: {' '.join(cmd)}")
        raise


def check_disk_space(path: str, required_gb: int) -> bool:
    """
    Check if sufficient disk space is available

    Args:
        path: Path to check
        required_gb: Required space in GB

    Returns:
        True if sufficient space available
    """
    try:
        stat = shutil.disk_usage(path)
        available_gb = stat.free / (1024**3)

        logger.info(f"Disk space at {path}: {available_gb:.2f} GB available")

        if available_gb >= required_gb:
            return True
        else:
            logger.warning(
                f"Insufficient disk space at {path}: "
                f"{available_gb:.2f} GB available, {required_gb} GB required"
            )
            return False

    except Exception as e:
        logger.error(f"Error checking disk space at {path}: {e}")
        return False


def check_root() -> bool:
    """
    Check if running as root

    Returns:
        True if running as root
    """
    is_root = os.geteuid() == 0
    if not is_root:
        logger.warning("Not running as root")
    return is_root


def test_ssh_connection(host: str, user: str = "root", key_path: Optional[str] = None) -> bool:
    """
    Test SSH connection to remote host

    Args:
        host: Remote hostname
        user: SSH user
        key_path: Path to SSH key

    Returns:
        True if connection successful
    """
    try:
        cmd = ["ssh", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes"]

        if key_path:
            cmd.extend(["-i", key_path])

        cmd.extend([f"{user}@{host}", "echo", "connected"])

        returncode, stdout, stderr = run_command(cmd, check=False, timeout=10)

        if returncode == 0 and "connected" in stdout:
            logger.info(f"SSH connection to {host} successful")
            return True
        else:
            logger.error(f"SSH connection to {host} failed")
            return False

    except Exception as e:
        logger.error(f"Error testing SSH connection to {host}: {e}")
        return False


def safe_delete(path: str, backup: bool = True) -> bool:
    """
    Safely delete a file or directory with optional backup

    Args:
        path: Path to delete
        backup: Create backup before deletion

    Returns:
        True if successful
    """
    try:
        if not os.path.exists(path):
            logger.warning(f"Path does not exist: {path}")
            return True

        if backup:
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = f"{path}.backup.{timestamp}"

            logger.info(f"Creating backup: {backup_path}")

            if os.path.isdir(path):
                shutil.copytree(path, backup_path)
            else:
                shutil.copy2(path, backup_path)

        logger.info(f"Deleting: {path}")

        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)

        return True

    except Exception as e:
        logger.error(f"Error deleting {path}: {e}")
        return False


def ensure_directory(path: str, mode: int = 0o755) -> bool:
    """
    Ensure directory exists with proper permissions

    Args:
        path: Directory path
        mode: Directory permissions

    Returns:
        True if successful
    """
    try:
        Path(path).mkdir(parents=True, exist_ok=True, mode=mode)
        logger.debug(f"Ensured directory exists: {path}")
        return True
    except Exception as e:
        logger.error(f"Error creating directory {path}: {e}")
        return False


def get_hostname() -> str:
    """Get system hostname"""
    try:
        returncode, stdout, stderr = run_command(["hostname"], check=True)
        return stdout.strip()
    except Exception:
        return "unknown"


def get_ip_address() -> str:
    """Get primary IP address"""
    try:
        returncode, stdout, stderr = run_command(
            ["hostname", "-I"],
            check=True
        )
        ips = stdout.strip().split()
        return ips[0] if ips else "unknown"
    except Exception:
        return "unknown"


def format_bytes(bytes_value: int) -> str:
    """
    Format bytes to human-readable string

    Args:
        bytes_value: Number of bytes

    Returns:
        Formatted string (e.g., "1.5 GB")
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_value < 1024.0:
            return f"{bytes_value:.2f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.2f} PB"


def validate_path(path: str, must_exist: bool = False) -> bool:
    """
    Validate a file path

    Args:
        path: Path to validate
        must_exist: If True, path must exist

    Returns:
        True if valid
    """
    try:
        # Check for directory traversal attempts
        normalized = os.path.normpath(path)
        if ".." in normalized:
            logger.warning(f"Path traversal attempt detected: {path}")
            return False

        # Check if exists
        if must_exist and not os.path.exists(path):
            logger.warning(f"Path does not exist: {path}")
            return False

        return True

    except Exception as e:
        logger.error(f"Error validating path {path}: {e}")
        return False


def validate_backup_name(name: str) -> bool:
    """
    Validate backup archive name for security

    Args:
        name: Backup name to validate

    Returns:
        True if valid
    """
    import re

    # Only allow alphanumeric, dash, underscore, and dot
    pattern = r'^[a-zA-Z0-9_.-]+$'

    if not re.match(pattern, name):
        logger.warning(f"Invalid backup name: {name}")
        return False

    # Check for directory traversal
    if ".." in name or "/" in name:
        logger.warning(f"Path traversal attempt in backup name: {name}")
        return False

    return True


class CommandExecutor:
    """Context manager for executing commands with logging"""

    def __init__(self, description: str):
        self.description = description
        self.start_time = None

    def __enter__(self):
        import time
        self.start_time = time.time()
        logger.info(f"Starting: {self.description}")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        import time
        duration = time.time() - self.start_time

        if exc_type is None:
            logger.info(f"Completed: {self.description} (took {duration:.2f}s)")
        else:
            logger.error(
                f"Failed: {self.description} (after {duration:.2f}s) - {exc_val}"
            )

        return False  # Don't suppress exceptions
