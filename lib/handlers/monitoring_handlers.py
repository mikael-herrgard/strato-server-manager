"""
Monitoring Menu Handlers
Handles all monitoring and status-related menu operations
"""

from ..utils import logger


class MonitoringHandlers:
    """Handles monitoring and status menu operations"""

    def __init__(self, ui, monitoring_manager):
        """
        Initialize monitoring handlers

        Args:
            ui: ServerManagerUI instance
            monitoring_manager: MonitoringManager instance (or callable)
        """
        self.ui = ui
        self._monitoring_manager = monitoring_manager

    def _get_monitoring_manager(self):
        """Get monitoring manager (lazy initialization support)"""
        if callable(self._monitoring_manager):
            return self._monitoring_manager()
        return self._monitoring_manager

    def handle_service_status(self):
        """Show service status"""
        try:
            mon_mgr = self._get_monitoring_manager()

            # Get status for all services
            all_status = mon_mgr.get_all_services_status()

            # Build status text
            status_text = "Service Status\n"
            status_text += "=" * 60 + "\n\n"

            for service_name, status in all_status.items():
                status_text += f"{service_name.upper()}:\n"

                if not status['installed']:
                    status_text += "  Status: Not Installed\n"
                    if status['error']:
                        status_text += f"  Error: {status['error']}\n"
                elif status['running']:
                    status_text += "  Status: ✓ Running\n"
                    status_text += f"  Containers: {len(status['containers'])}\n"
                    for container in status['containers']:
                        state_icon = "✓" if container['state'] == 'running' else "✗"
                        status_text += f"    {state_icon} {container['name']}: {container['status']}\n"
                else:
                    status_text += "  Status: ✗ Not Running\n"
                    if status['error']:
                        status_text += f"  Error: {status['error']}\n"

                status_text += "\n"

            self.ui.show_scrollable_text(status_text, "Service Status")

        except Exception as e:
            logger.error(f"Service status error: {e}")
            self.ui.show_error(f"Failed to get service status:\n\n{e}")

    def handle_container_stats(self):
        """Show container statistics"""
        try:
            mon_mgr = self._get_monitoring_manager()

            # Get stats for all containers
            stats = mon_mgr.get_container_stats()

            if not stats:
                self.ui.show_info(
                    "No running containers found.\n\n"
                    "Start some services first:\n"
                    "  • nginx Proxy Manager\n"
                    "  • Mailcow",
                    "No Containers"
                )
                return

            # Build stats text
            stats_text = "Container Resource Usage\n"
            stats_text += "=" * 80 + "\n\n"

            for container in stats:
                stats_text += f"Container: {container['name']}\n"
                stats_text += f"  CPU:     {container['cpu_percent']}\n"
                stats_text += f"  Memory:  {container['memory_usage']} ({container['memory_percent']})\n"
                stats_text += f"  Network: {container['net_io']}\n"
                stats_text += f"  Disk I/O: {container['block_io']}\n"
                stats_text += f"  PIDs:    {container['pids']}\n"
                stats_text += "\n"

            self.ui.show_scrollable_text(stats_text, "Container Statistics")

        except Exception as e:
            logger.error(f"Container stats error: {e}")
            self.ui.show_error(f"Failed to get container statistics:\n\n{e}")

    def handle_system_info(self):
        """Show system information"""
        try:
            mon_mgr = self._get_monitoring_manager()

            info = mon_mgr.get_system_info()

            # Build info text
            info_text = "System Information\n"
            info_text += "=" * 60 + "\n\n"

            info_text += f"Hostname: {info.get('hostname', 'Unknown')}\n"
            info_text += f"IP Address: {info.get('ip_address', 'Unknown')}\n"
            info_text += f"OS: {info.get('os', 'Unknown')}\n"
            info_text += f"Kernel: {info.get('kernel', 'Unknown')}\n"
            info_text += f"Uptime: {info.get('uptime', 'Unknown')}\n"
            info_text += f"Load Average: {info.get('load_average', 'Unknown')}\n\n"

            if 'memory' in info:
                mem = info['memory']
                info_text += "Memory:\n"
                info_text += f"  Total: {mem.get('total_gb', 0)} GB\n"
                info_text += f"  Used: {mem.get('used_gb', 0)} GB\n"
                info_text += f"  Free: {mem.get('free_gb', 0)} GB\n"
                info_text += f"  Usage: {mem.get('percent', 0)}%\n\n"

            if 'disk' in info:
                disk = info['disk']
                info_text += "Disk (/):\n"
                info_text += f"  Total: {disk.get('total_gb', 0)} GB\n"
                info_text += f"  Used: {disk.get('used_gb', 0)} GB\n"
                info_text += f"  Free: {disk.get('free_gb', 0)} GB\n"
                info_text += f"  Usage: {disk.get('percent', 0)}%\n\n"

            if 'docker' in info:
                info_text += f"Docker: {info['docker'].get('version', 'Not installed')}\n"

            self.ui.show_scrollable_text(info_text, "System Information")

        except Exception as e:
            logger.error(f"System info error: {e}")
            self.ui.show_error(f"Failed to get system information:\n\n{e}")

    def handle_disk_usage(self):
        """Show disk usage"""
        try:
            mon_mgr = self._get_monitoring_manager()

            usage = mon_mgr.get_disk_usage()

            # Build usage text
            usage_text = "Disk Usage\n"
            usage_text += "=" * 60 + "\n\n"

            # Partitions
            if 'partitions' in usage and usage['partitions']:
                usage_text += "Partitions:\n"
                for part in usage['partitions']:
                    usage_text += f"  {part['mount']}:\n"
                    usage_text += f"    Total: {part['total_gb']} GB\n"
                    usage_text += f"    Used: {part['used_gb']} GB ({part['percent']}%)\n"
                    usage_text += f"    Free: {part['free_gb']} GB\n\n"

            # Docker
            if 'docker' in usage and usage['docker']:
                usage_text += "Docker:\n"
                docker = usage['docker']
                if 'images_count' in docker:
                    usage_text += f"  Images: {docker['images_count']}\n"
                if 'containers_count' in docker:
                    usage_text += f"  Containers: {docker['containers_count']}\n"
                if 'volumes_count' in docker:
                    usage_text += f"  Volumes: {docker['volumes_count']}\n"
                usage_text += "\n"

            # Services
            if 'services' in usage and usage['services']:
                usage_text += "Services:\n"
                for service, info in usage['services'].items():
                    usage_text += f"  {service}: {info['size_mb']} MB\n"
                usage_text += "\n"

            self.ui.show_scrollable_text(usage_text, "Disk Usage")

        except Exception as e:
            logger.error(f"Disk usage error: {e}")
            self.ui.show_error(f"Failed to get disk usage:\n\n{e}")
