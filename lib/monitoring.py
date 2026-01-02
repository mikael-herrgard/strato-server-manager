"""
Monitoring Module
Handles service status, resource monitoring, and health checks
"""

import os
import json
import subprocess
import shutil
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from .utils import (
    logger,
    run_command,
    get_hostname,
    get_ip_address
)
from .config import get_config


class MonitoringManager:
    """Manage monitoring and status operations"""

    def __init__(self):
        """Initialize monitoring manager"""
        self.config = get_config()
        self.nginx_config = self.config.get_nginx_config()
        self.mailcow_config = self.config.get_mailcow_config()

    def get_service_status(self, service: str) -> Dict[str, any]:
        """
        Get status of a service (nginx or mailcow)

        Args:
            service: Service name ('nginx' or 'mailcow')

        Returns:
            Dictionary with service status
        """
        logger.info(f"Getting status for {service}")

        status = {
            'service': service,
            'installed': False,
            'running': False,
            'containers': [],
            'error': None
        }

        if service == 'nginx':
            path = self.nginx_config['install_path']
        elif service == 'mailcow':
            path = self.mailcow_config['install_path']
        else:
            status['error'] = f"Unknown service: {service}"
            return status

        # Check if installed
        if not os.path.exists(path):
            status['error'] = f"Service not installed (directory not found: {path})"
            return status

        status['installed'] = True

        try:
            # Get container status using docker compose
            returncode, stdout, stderr = run_command(
                ['docker', 'compose', 'ps', '--format', 'json'],
                check=False,
                cwd=path,
                timeout=30
            )

            if returncode != 0:
                status['error'] = f"Failed to get container status: {stderr}"
                return status

            # Parse JSON output (one JSON object per line)
            containers = []
            for line in stdout.strip().split('\n'):
                if not line:
                    continue
                try:
                    container = json.loads(line)
                    containers.append({
                        'name': container.get('Name', 'unknown'),
                        'state': container.get('State', 'unknown'),
                        'status': container.get('Status', 'unknown'),
                        'health': container.get('Health', 'N/A')
                    })
                except json.JSONDecodeError:
                    continue

            status['containers'] = containers
            status['running'] = any(c['state'] == 'running' for c in containers)

            return status

        except Exception as e:
            logger.error(f"Failed to get service status: {e}")
            status['error'] = str(e)
            return status

    def get_all_services_status(self) -> Dict[str, any]:
        """
        Get status of all services

        Returns:
            Dictionary with all services status
        """
        return {
            'nginx': self.get_service_status('nginx'),
            'mailcow': self.get_service_status('mailcow')
        }

    def get_container_stats(self, service: Optional[str] = None) -> List[Dict[str, any]]:
        """
        Get resource usage statistics for containers

        Args:
            service: Optional service name to filter ('nginx' or 'mailcow')

        Returns:
            List of container statistics
        """
        logger.info(f"Getting container stats (service={service})")

        stats = []

        try:
            # Get all running containers
            returncode, stdout, stderr = run_command(
                ['docker', 'stats', '--no-stream', '--format',
                 '{{json .}}'],
                check=True,
                timeout=30
            )

            # Parse JSON output
            for line in stdout.strip().split('\n'):
                if not line:
                    continue
                try:
                    container = json.loads(line)

                    # Filter by service if specified
                    if service:
                        if service == 'nginx' and 'nginx' not in container.get('Name', '').lower():
                            continue
                        if service == 'mailcow' and 'mailcow' not in container.get('Name', '').lower():
                            continue

                    stats.append({
                        'name': container.get('Name', 'unknown'),
                        'cpu_percent': container.get('CPUPerc', '0%'),
                        'memory_usage': container.get('MemUsage', '0B / 0B'),
                        'memory_percent': container.get('MemPerc', '0%'),
                        'net_io': container.get('NetIO', '0B / 0B'),
                        'block_io': container.get('BlockIO', '0B / 0B'),
                        'pids': container.get('PIDs', '0')
                    })

                except json.JSONDecodeError:
                    continue

            return stats

        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get container stats: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error getting container stats: {e}")
            return []

    def get_disk_usage(self) -> Dict[str, any]:
        """
        Get detailed disk usage information

        Returns:
            Dictionary with disk usage data
        """
        logger.info("Getting disk usage information")

        usage = {
            'partitions': [],
            'docker': {},
            'services': {}
        }

        try:
            # Get partition usage
            stat = shutil.disk_usage('/')
            usage['partitions'].append({
                'mount': '/',
                'total_gb': round(stat.total / (1024**3), 2),
                'used_gb': round(stat.used / (1024**3), 2),
                'free_gb': round(stat.free / (1024**3), 2),
                'percent': round((stat.used / stat.total) * 100, 1)
            })

            # Get Docker disk usage
            try:
                returncode, stdout, stderr = run_command(
                    ['docker', 'system', 'df', '--format', 'json'],
                    check=True,
                    timeout=30
                )

                # Docker system df returns one big JSON object
                try:
                    docker_data = json.loads(stdout)

                    # Parse Images
                    if 'Images' in docker_data:
                        for img in docker_data['Images']:
                            if 'Size' not in usage['docker']:
                                usage['docker']['images_size'] = 0
                            # Size is usually a string like "123MB"
                            usage['docker']['images_count'] = len(docker_data['Images'])

                    # Parse Containers
                    if 'Containers' in docker_data:
                        usage['docker']['containers_count'] = len(docker_data['Containers'])

                    # Parse Volumes
                    if 'Volumes' in docker_data:
                        usage['docker']['volumes_count'] = len(docker_data['Volumes'])

                except json.JSONDecodeError:
                    # Fallback to text parsing
                    usage['docker']['raw'] = stdout

            except Exception as e:
                logger.warning(f"Could not get Docker disk usage: {e}")

            # Get service directory sizes
            for service_name, service_path in [
                ('nginx', self.nginx_config['install_path']),
                ('mailcow', self.mailcow_config['install_path']),
                ('server-manager', '/opt/server-manager')
            ]:
                if os.path.exists(service_path):
                    try:
                        size_bytes = sum(
                            os.path.getsize(os.path.join(dirpath, filename))
                            for dirpath, dirnames, filenames in os.walk(service_path)
                            for filename in filenames
                        )
                        usage['services'][service_name] = {
                            'path': service_path,
                            'size_mb': round(size_bytes / (1024**2), 2)
                        }
                    except Exception as e:
                        logger.warning(f"Could not get size for {service_name}: {e}")

            return usage

        except Exception as e:
            logger.error(f"Failed to get disk usage: {e}")
            return usage

    def get_system_info(self) -> Dict[str, any]:
        """
        Get comprehensive system information

        Returns:
            Dictionary with system information
        """
        logger.info("Getting system information")

        info = {
            'hostname': get_hostname(),
            'ip_address': get_ip_address(),
            'uptime': '',
            'load_average': '',
            'memory': {},
            'disk': {},
            'docker': {}
        }

        try:
            # Uptime
            with open('/proc/uptime', 'r') as f:
                uptime_seconds = float(f.read().split()[0])
                days = int(uptime_seconds // 86400)
                hours = int((uptime_seconds % 86400) // 3600)
                minutes = int((uptime_seconds % 3600) // 60)
                info['uptime'] = f"{days}d {hours}h {minutes}m"

            # Load average
            with open('/proc/loadavg', 'r') as f:
                loads = f.read().split()[:3]
                info['load_average'] = f"{loads[0]} {loads[1]} {loads[2]}"

            # Memory
            with open('/proc/meminfo', 'r') as f:
                meminfo = {}
                for line in f:
                    parts = line.split(':')
                    if len(parts) == 2:
                        key = parts[0].strip()
                        value = parts[1].strip().split()[0]  # Remove 'kB'
                        meminfo[key] = int(value)

                total_gb = meminfo.get('MemTotal', 0) / (1024 ** 2)
                free_gb = meminfo.get('MemAvailable', 0) / (1024 ** 2)
                used_gb = total_gb - free_gb

                info['memory'] = {
                    'total_gb': round(total_gb, 2),
                    'used_gb': round(used_gb, 2),
                    'free_gb': round(free_gb, 2),
                    'percent': round((used_gb / total_gb) * 100, 1) if total_gb > 0 else 0
                }

            # Disk
            stat = shutil.disk_usage('/')
            info['disk'] = {
                'total_gb': round(stat.total / (1024**3), 2),
                'used_gb': round(stat.used / (1024**3), 2),
                'free_gb': round(stat.free / (1024**3), 2),
                'percent': round((stat.used / stat.total) * 100, 1)
            }

            # Docker version
            try:
                returncode, stdout, stderr = run_command(
                    ['docker', '--version'],
                    check=True,
                    timeout=10
                )
                info['docker']['version'] = stdout.strip()
            except Exception:
                info['docker']['version'] = 'Not installed'

            # OS info
            if os.path.exists('/etc/os-release'):
                with open('/etc/os-release', 'r') as f:
                    for line in f:
                        if line.startswith('PRETTY_NAME='):
                            info['os'] = line.split('=')[1].strip().strip('"')
                            break

            # Kernel version
            with open('/proc/version', 'r') as f:
                version_line = f.read()
                info['kernel'] = version_line.split()[2]

            return info

        except Exception as e:
            logger.error(f"Failed to get system info: {e}")
            return info

    def check_service_health(self, service: str) -> Dict[str, any]:
        """
        Perform health check on a service

        Args:
            service: Service name ('nginx' or 'mailcow')

        Returns:
            Dictionary with health check results
        """
        logger.info(f"Performing health check on {service}")

        health = {
            'service': service,
            'healthy': False,
            'checks': [],
            'issues': []
        }

        status = self.get_service_status(service)

        # Check if installed
        health['checks'].append({
            'name': 'Installed',
            'status': 'PASS' if status['installed'] else 'FAIL'
        })
        if not status['installed']:
            health['issues'].append('Service not installed')
            return health

        # Check if running
        health['checks'].append({
            'name': 'Running',
            'status': 'PASS' if status['running'] else 'FAIL'
        })
        if not status['running']:
            health['issues'].append('Service not running')

        # Check container states
        if status['containers']:
            all_running = all(c['state'] == 'running' for c in status['containers'])
            health['checks'].append({
                'name': 'All Containers Running',
                'status': 'PASS' if all_running else 'FAIL'
            })
            if not all_running:
                health['issues'].append('Some containers not running')
        else:
            health['issues'].append('No containers found')

        # Overall health
        health['healthy'] = len(health['issues']) == 0

        return health

    def get_docker_info(self) -> Dict[str, any]:
        """
        Get Docker system information

        Returns:
            Dictionary with Docker information
        """
        logger.info("Getting Docker information")

        info = {
            'version': '',
            'containers': {
                'total': 0,
                'running': 0,
                'stopped': 0
            },
            'images': 0,
            'volumes': 0,
            'networks': 0
        }

        try:
            # Docker version
            returncode, stdout, stderr = run_command(
                ['docker', '--version'],
                check=True,
                timeout=10
            )
            info['version'] = stdout.strip()

            # Container counts
            returncode, stdout, stderr = run_command(
                ['docker', 'ps', '-a', '--format', '{{.State}}'],
                check=True,
                timeout=30
            )
            states = stdout.strip().split('\n') if stdout.strip() else []
            info['containers']['total'] = len(states)
            info['containers']['running'] = states.count('running')
            info['containers']['stopped'] = info['containers']['total'] - info['containers']['running']

            # Image count
            returncode, stdout, stderr = run_command(
                ['docker', 'images', '-q'],
                check=True,
                timeout=30
            )
            info['images'] = len([l for l in stdout.strip().split('\n') if l])

            # Volume count
            returncode, stdout, stderr = run_command(
                ['docker', 'volume', 'ls', '-q'],
                check=True,
                timeout=30
            )
            info['volumes'] = len([l for l in stdout.strip().split('\n') if l])

            # Network count
            returncode, stdout, stderr = run_command(
                ['docker', 'network', 'ls', '-q'],
                check=True,
                timeout=30
            )
            info['networks'] = len([l for l in stdout.strip().split('\n') if l])

            return info

        except Exception as e:
            logger.error(f"Failed to get Docker info: {e}")
            return info

    def get_logs(self, service: str, lines: int = 100) -> str:
        """
        Get logs for a service

        Args:
            service: Service name ('nginx', 'mailcow', or 'server-manager')
            lines: Number of lines to retrieve

        Returns:
            Log content as string
        """
        logger.info(f"Getting logs for {service} (last {lines} lines)")

        if service == 'server-manager':
            # Application logs
            log_file = '/opt/server-manager/logs/server-manager.log'
            if os.path.exists(log_file):
                try:
                    returncode, stdout, stderr = run_command(
                        ['tail', '-n', str(lines), log_file],
                        check=True,
                        timeout=10
                    )
                    return stdout
                except Exception as e:
                    return f"Failed to read logs: {e}"
            else:
                return f"Log file not found: {log_file}"

        elif service in ['nginx', 'mailcow']:
            # Docker container logs
            if service == 'nginx':
                path = self.nginx_config['install_path']
            else:
                path = self.mailcow_config['install_path']

            if not os.path.exists(path):
                return f"Service not installed: {service}"

            try:
                returncode, stdout, stderr = run_command(
                    ['docker', 'compose', 'logs', '--tail', str(lines)],
                    check=True,
                    cwd=path,
                    timeout=30
                )
                return stdout
            except Exception as e:
                return f"Failed to get logs: {e}"

        else:
            return f"Unknown service: {service}"
