"""
Installation Menu Handlers
Handles all installation-related menu operations
"""

from ..utils import logger, get_hostname


class InstallationHandlers:
    """Handles installation menu operations"""

    def __init__(self, ui, installation_manager):
        """
        Initialize installation handlers

        Args:
            ui: ServerManagerUI instance
            installation_manager: InstallationManager instance (or callable)
        """
        self.ui = ui
        self._installation_manager = installation_manager

    def _get_installation_manager(self):
        """Get installation manager (lazy initialization support)"""
        if callable(self._installation_manager):
            return self._installation_manager()
        return self._installation_manager

    def handle_check_prerequisites(self):
        """Check system prerequisites"""
        try:
            install_mgr = self._get_installation_manager()
            prereqs = install_mgr.check_prerequisites()

            # Build status text
            status_text = f"""System Prerequisites Check

Disk Space: {'✓' if prereqs['disk_space'] else '✗'} (20GB+ required)
RAM: {'✓' if prereqs['ram'] else '✗'} ({prereqs.get('ram_gb', 0):.1f} GB available, 4GB+ required)
OS: {'✓ Supported' if prereqs['os_supported'] else '✗ Unsupported'}

Docker:
  Docker Engine: {'✓ Installed' if prereqs['docker_installed'] else '✗ Not Installed'}
  Docker Compose: {'✓ Installed' if prereqs['docker_compose_installed'] else '✗ Not Installed'}

Port Availability:
"""

            # Add port status
            for port, available in sorted(prereqs['ports_available'].items()):
                if available is None:
                    status = '? Unknown'
                elif available:
                    status = '✓ Available'
                else:
                    status = '✗ In Use'
                status_text += f"  Port {port}: {status}\n"

            # Add warnings
            warnings = []
            if not prereqs['disk_space']:
                warnings.append("Insufficient disk space (20GB+ required for Mailcow)")
            if not prereqs['ram']:
                warnings.append("Insufficient RAM (4GB+ required for Mailcow)")
            if not prereqs['docker_installed']:
                warnings.append("Docker is not installed")
            if not prereqs['docker_compose_installed']:
                warnings.append("Docker Compose is not installed")

            if warnings:
                status_text += "\nWarnings:\n"
                for warning in warnings:
                    status_text += f"  • {warning}\n"

            self.ui.show_scrollable_text(status_text, "Prerequisites Check")

        except Exception as e:
            logger.error(f"Failed to check prerequisites: {e}")
            self.ui.show_error(f"Failed to check prerequisites:\n\n{e}")

    def handle_install_docker(self):
        """Install Docker"""
        if not self.ui.confirm_action(
            "This will install Docker Engine and Docker Compose.\n\n"
            "The installation may take 5-10 minutes.\n\n"
            "Continue?",
            "Install Docker"
        ):
            return

        try:
            install_mgr = self._get_installation_manager()

            self.ui.show_infobox("Installing Docker and Docker Compose...\n\nThis may take several minutes.")

            success = install_mgr.install_docker()

            if success:
                self.ui.show_success(
                    "Docker installed successfully!\n\n"
                    "Docker Engine and Docker Compose are now available."
                )
                logger.info("Docker installation completed via TUI")
            else:
                self.ui.show_error("Docker installation failed. Check logs for details.")

        except Exception as e:
            logger.error(f"Docker installation error: {e}")
            self.ui.show_error(f"Installation failed:\n\n{e}")

    def handle_install_mailcow(self):
        """Install Mailcow"""
        # Get domain name from user
        code, domain = self.ui.d.inputbox(
            "Enter the primary domain for Mailcow\n"
            "(e.g., mail.example.com):",
            title="Mailcow Domain",
            width=60
        )

        if code != self.ui.d.OK or not domain:
            return

        # Get timezone
        code, timezone = self.ui.d.inputbox(
            "Enter timezone for Mailcow\n"
            "(e.g., America/New_York, Europe/London):",
            title="Mailcow Timezone",
            init="America/New_York",
            width=60
        )

        if code != self.ui.d.OK or not timezone:
            timezone = "America/New_York"

        if not self.ui.confirm_action(
            f"This will install Mailcow with:\n\n"
            f"Domain: {domain}\n"
            f"Timezone: {timezone}\n\n"
            "The installation may take 20-30 minutes.\n\n"
            "Prerequisites:\n"
            "  • Docker must be installed\n"
            "  • At least 20GB free disk space\n"
            "  • At least 4GB RAM\n"
            "  • Ports 25,80,110,143,443,465,587,993,995 available\n\n"
            "Continue?",
            "Install Mailcow"
        ):
            return

        try:
            install_mgr = self._get_installation_manager()

            self.ui.show_infobox(
                f"Installing Mailcow for {domain}...\n\n"
                "This will take 20-30 minutes.\n"
                "Please be patient..."
            )

            success = install_mgr.install_mailcow(domain, timezone)

            if success:
                self.ui.show_success(
                    f"Mailcow installed successfully!\n\n"
                    f"Domain: {domain}\n"
                    f"Admin UI: https://{domain}\n"
                    f"Default login: admin / moohoo\n\n"
                    "IMPORTANT: Configure DNS records before using!\n"
                    "See logs for DNS configuration details."
                )
                logger.info(f"Mailcow installation completed via TUI for {domain}")
            else:
                self.ui.show_error("Mailcow installation failed. Check logs for details.")

        except Exception as e:
            logger.error(f"Mailcow installation error: {e}")
            self.ui.show_error(f"Installation failed:\n\n{e}")

    def handle_install_nginx(self):
        """Install nginx Proxy Manager"""
        if not self.ui.confirm_action(
            "This will install nginx Proxy Manager.\n\n"
            "Prerequisites:\n"
            "  • Docker must be installed\n"
            "  • Ports 80, 81, and 443 must be available\n\n"
            "Installation time: ~5 minutes\n\n"
            "Default access:\n"
            "  URL: http://YOUR_IP:81\n"
            "  Login: admin@example.com / changeme\n\n"
            "Continue?",
            "Install nginx Proxy Manager"
        ):
            return

        try:
            install_mgr = self._get_installation_manager()

            self.ui.show_infobox("Installing nginx Proxy Manager...\n\nThis may take a few minutes.")

            success = install_mgr.install_nginx_proxy_manager()

            if success:
                hostname = get_hostname()
                self.ui.show_success(
                    "nginx Proxy Manager installed successfully!\n\n"
                    f"Access at: http://{hostname}:81\n\n"
                    "Default login:\n"
                    "  Email: admin@example.com\n"
                    "  Password: changeme\n\n"
                    "IMPORTANT: Change the default password!"
                )
                logger.info("nginx Proxy Manager installation completed via TUI")
            else:
                self.ui.show_error("nginx installation failed. Check logs for details.")

        except Exception as e:
            logger.error(f"nginx installation error: {e}")
            self.ui.show_error(f"Installation failed:\n\n{e}")
