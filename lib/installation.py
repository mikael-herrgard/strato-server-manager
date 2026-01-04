"""
Installation Module
Handles fresh installation of Docker, Mailcow, and nginx Proxy Manager
"""

import os
import subprocess
import shutil
from pathlib import Path
from typing import Dict, Optional, Tuple
from .utils import (
    logger,
    run_command,
    check_disk_space,
    ensure_directory,
    get_hostname,
    CommandExecutor
)
from .config import get_config


class InstallationManager:
    """Manage installation operations for services"""

    def __init__(self):
        """Initialize installation manager"""
        self.config = get_config()
        self.hostname = get_hostname()

        # Get configuration
        self.nginx_config = self.config.get_nginx_config()
        self.mailcow_config = self.config.get_mailcow_config()

    def check_prerequisites(self) -> Dict[str, any]:
        """
        Check system prerequisites for installations

        Returns:
            Dictionary with check results
        """
        logger.info("Checking installation prerequisites")

        results = {
            'disk_space': False,
            'ram': False,
            'ports_available': {},
            'os_supported': False,
            'docker_installed': False,
            'docker_compose_installed': False
        }

        # Check disk space (20GB minimum for Mailcow)
        results['disk_space'] = check_disk_space('/', 20)

        # Check RAM (4GB minimum for Mailcow)
        try:
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    if line.startswith('MemTotal:'):
                        # Extract memory in KB
                        mem_kb = int(line.split()[1])
                        mem_gb = mem_kb / 1024 / 1024
                        results['ram'] = mem_gb >= 4.0
                        results['ram_gb'] = round(mem_gb, 2)
                        break
        except Exception as e:
            logger.error(f"Failed to check RAM: {e}")
            results['ram'] = False

        # Check if Docker is installed
        try:
            returncode, stdout, stderr = run_command(
                ['docker', '--version'],
                check=False,
                timeout=10
            )
            results['docker_installed'] = (returncode == 0)
        except Exception:
            results['docker_installed'] = False

        # Check if Docker Compose is installed
        try:
            returncode, stdout, stderr = run_command(
                ['docker', 'compose', 'version'],
                check=False,
                timeout=10
            )
            results['docker_compose_installed'] = (returncode == 0)
        except Exception:
            results['docker_compose_installed'] = False

        # Check OS (Debian/Ubuntu supported)
        try:
            if os.path.exists('/etc/os-release'):
                with open('/etc/os-release', 'r') as f:
                    content = f.read().lower()
                    results['os_supported'] = 'debian' in content or 'ubuntu' in content
        except Exception:
            results['os_supported'] = False

        # Check port availability
        for port in [80, 443, 25, 587, 993, 995, 110, 143]:
            try:
                returncode, stdout, stderr = run_command(
                    ['ss', '-tlnH', f'sport = :{port}'],
                    check=False,
                    timeout=5
                )
                # If output is empty, port is free
                results['ports_available'][port] = (stdout.strip() == '')
            except Exception:
                results['ports_available'][port] = None

        return results

    def install_docker(self) -> bool:
        """
        Install Docker and Docker Compose

        Returns:
            True if successful
        """
        logger.info("Starting Docker installation")

        # Check if already installed
        prereqs = self.check_prerequisites()
        if prereqs['docker_installed'] and prereqs['docker_compose_installed']:
            logger.info("Docker and Docker Compose already installed")
            return True

        try:
            with CommandExecutor("Installing Docker"):
                # Update package index
                logger.info("Updating package index...")
                returncode, stdout, stderr = run_command(
                    ['apt-get', 'update'],
                    check=True,
                    timeout=300
                )

                # Install prerequisites
                logger.info("Installing prerequisites...")
                returncode, stdout, stderr = run_command(
                    ['apt-get', 'install', '-y',
                     'ca-certificates', 'curl', 'gnupg', 'lsb-release'],
                    check=True,
                    timeout=300
                )

                # Add Docker's official GPG key
                logger.info("Adding Docker GPG key...")
                ensure_directory('/etc/apt/keyrings')

                returncode, stdout, stderr = run_command(
                    ['curl', '-fsSL', 'https://download.docker.com/linux/ubuntu/gpg'],
                    check=True,
                    timeout=60
                )

                # Save GPG key
                with open('/etc/apt/keyrings/docker.asc', 'w') as f:
                    f.write(stdout)
                os.chmod('/etc/apt/keyrings/docker.asc', 0o644)

                # Get OS codename
                returncode, stdout, stderr = run_command(
                    ['lsb_release', '-cs'],
                    check=True,
                    timeout=10
                )
                codename = stdout.strip()

                # Add Docker repository
                logger.info("Adding Docker repository...")
                repo_line = (
                    f'deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.asc] '
                    f'https://download.docker.com/linux/ubuntu {codename} stable'
                )

                with open('/etc/apt/sources.list.d/docker.list', 'w') as f:
                    f.write(repo_line + '\n')

                # Update package index again
                logger.info("Updating package index with Docker repository...")
                returncode, stdout, stderr = run_command(
                    ['apt-get', 'update'],
                    check=True,
                    timeout=300
                )

                # Install Docker
                logger.info("Installing Docker Engine...")
                returncode, stdout, stderr = run_command(
                    ['apt-get', 'install', '-y',
                     'docker-ce', 'docker-ce-cli', 'containerd.io',
                     'docker-buildx-plugin', 'docker-compose-plugin'],
                    check=True,
                    timeout=600
                )

                # Start and enable Docker service
                logger.info("Starting Docker service...")
                run_command(['systemctl', 'start', 'docker'], check=True, timeout=30)
                run_command(['systemctl', 'enable', 'docker'], check=True, timeout=30)

                # Verify installation
                returncode, stdout, stderr = run_command(
                    ['docker', '--version'],
                    check=True,
                    timeout=10
                )
                logger.info(f"Docker installed: {stdout.strip()}")

                returncode, stdout, stderr = run_command(
                    ['docker', 'compose', 'version'],
                    check=True,
                    timeout=10
                )
                logger.info(f"Docker Compose installed: {stdout.strip()}")

                logger.info("Docker installation completed successfully")
                return True

        except subprocess.CalledProcessError as e:
            logger.error(f"Docker installation failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during Docker installation: {e}")
            return False

    def install_nginx_proxy_manager(self) -> bool:
        """
        Install nginx Proxy Manager

        Returns:
            True if successful
        """
        logger.info("Starting nginx Proxy Manager installation")

        nginx_path = self.nginx_config['install_path']

        # Check if already installed
        if os.path.exists(nginx_path):
            logger.warning(f"nginx directory already exists: {nginx_path}")
            return False

        # Check prerequisites
        prereqs = self.check_prerequisites()
        if not prereqs['docker_installed']:
            logger.error("Docker is not installed. Please install Docker first.")
            return False

        # Check ports 80 and 443
        if not prereqs['ports_available'].get(80) or not prereqs['ports_available'].get(443):
            logger.warning("Ports 80 or 443 may already be in use")

        try:
            with CommandExecutor("Installing nginx Proxy Manager"):
                # Create directory
                ensure_directory(nginx_path)

                # Create docker-compose.yml
                logger.info("Creating docker-compose.yml...")
                compose_content = """version: '3.8'
services:
  app:
    image: 'jc21/nginx-proxy-manager:latest'
    restart: unless-stopped
    ports:
      - '80:80'
      - '81:81'
      - '443:443'
    volumes:
      - ./data:/data
      - ./letsencrypt:/etc/letsencrypt
    networks:
      - npm_network

networks:
  npm_network:
    driver: bridge
"""

                compose_path = os.path.join(nginx_path, 'docker-compose.yml')
                with open(compose_path, 'w') as f:
                    f.write(compose_content)

                logger.info(f"Created {compose_path}")

                # Create data directories
                ensure_directory(os.path.join(nginx_path, 'data'))
                ensure_directory(os.path.join(nginx_path, 'letsencrypt'))

                # Pull images
                logger.info("Pulling Docker images...")
                returncode, stdout, stderr = run_command(
                    ['docker', 'compose', 'pull'],
                    check=True,
                    cwd=nginx_path,
                    timeout=600
                )

                # Start containers
                logger.info("Starting nginx Proxy Manager...")
                returncode, stdout, stderr = run_command(
                    ['docker', 'compose', 'up', '-d'],
                    check=True,
                    cwd=nginx_path,
                    timeout=300
                )

                logger.info("nginx Proxy Manager installed successfully")
                logger.info("Default login: admin@example.com / changeme")
                logger.info(f"Access at: http://{self.hostname}:81")

                return True

        except subprocess.CalledProcessError as e:
            logger.error(f"nginx installation failed: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during nginx installation: {e}")
            return False

    def _get_public_ip(self) -> str:
        """
        Get public IP address

        Returns:
            Public IP or 'YOUR_SERVER_IP'
        """
        try:
            returncode, stdout, stderr = run_command(
                ['curl', '-s', 'https://api.ipify.org'],
                check=False,
                timeout=10
            )
            if returncode == 0 and stdout.strip():
                return stdout.strip()
        except Exception:
            pass

        return "YOUR_SERVER_IP"

    def uninstall_service(self, service: str) -> bool:
        """
        Uninstall a service (nginx or Mailcow)

        Args:
            service: Service to uninstall ('nginx' or 'mailcow')

        Returns:
            True if successful
        """
        logger.info(f"Uninstalling {service}")

        if service == 'nginx':
            path = self.nginx_config['install_path']
        elif service == 'mailcow':
            path = self.mailcow_config['install_path']
        else:
            logger.error(f"Unknown service: {service}")
            return False

        if not os.path.exists(path):
            logger.warning(f"Service directory does not exist: {path}")
            return False

        try:
            with CommandExecutor(f"Uninstalling {service}"):
                # Stop containers
                logger.info("Stopping containers...")
                run_command(
                    ['docker', 'compose', 'down', '-v'],
                    check=False,
                    cwd=path,
                    timeout=120
                )

                # Remove directory
                logger.info(f"Removing directory: {path}")
                shutil.rmtree(path)

                logger.info(f"{service} uninstalled successfully")
                return True

        except Exception as e:
            logger.error(f"Uninstall failed: {e}")
            return False
