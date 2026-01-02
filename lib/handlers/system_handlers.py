"""
System Configuration Menu Handlers
Handles all system configuration menu operations
"""

import os
import time
from ..utils import logger


class SystemHandlers:
    """Handles system configuration menu operations"""

    def __init__(self, ui, system_config_manager):
        """
        Initialize system handlers

        Args:
            ui: ServerManagerUI instance
            system_config_manager: SystemConfigManager instance (or callable)
        """
        self.ui = ui
        self._system_config_manager = system_config_manager

    def _get_system_config_manager(self):
        """Get system config manager (lazy initialization support)"""
        if callable(self._system_config_manager):
            return self._system_config_manager()
        return self._system_config_manager

    def handle_disable_ipv6(self):
        """Disable IPv6"""
        try:
            sys_config_mgr = self._get_system_config_manager()

            # Check current status
            status = sys_config_mgr.check_ipv6_status()

            if status['grub_disabled']:
                self.ui.show_info(
                    "IPv6 is already disabled in GRUB configuration.\n\n"
                    "If IPv6 is still active, a reboot is required.",
                    "IPv6 Already Disabled"
                )
                return

            if not self.ui.confirm_action(
                "This will disable IPv6 by modifying GRUB configuration.\n\n"
                "A backup of /etc/default/grub will be created.\n\n"
                "WARNING: A system reboot will be required for this change to take effect!\n\n"
                "Continue?",
                "Disable IPv6"
            ):
                return

            self.ui.show_infobox("Disabling IPv6 via GRUB...\n\nPlease wait...")

            success = sys_config_mgr.disable_ipv6()

            if success:
                if self.ui.confirm_action(
                    "IPv6 has been disabled in GRUB configuration.\n\n"
                    "A system reboot is required for the change to take effect.\n\n"
                    "Do you want to reboot now?",
                    "Reboot Required"
                ):
                    logger.info("Rebooting system to apply IPv6 disable")
                    self.ui.show_infobox("Rebooting system...")
                    time.sleep(2)
                    os.system("reboot")
                else:
                    self.ui.show_info(
                        "IPv6 disabled in GRUB.\n\n"
                        "Please reboot manually for changes to take effect:\n"
                        "  sudo reboot",
                        "Reboot Required"
                    )
            else:
                self.ui.show_error("Failed to disable IPv6. Check logs for details.")

        except Exception as e:
            logger.error(f"IPv6 disable error: {e}")
            self.ui.show_error(f"Failed to disable IPv6:\n\n{e}")

    def handle_enable_ipv6(self):
        """Enable IPv6"""
        try:
            sys_config_mgr = self._get_system_config_manager()

            # Check current status
            status = sys_config_mgr.check_ipv6_status()

            if not status['grub_disabled']:
                self.ui.show_info(
                    "IPv6 is already enabled in GRUB configuration.\n\n"
                    "If IPv6 is not working, check your network configuration.",
                    "IPv6 Already Enabled"
                )
                return

            if not self.ui.confirm_action(
                "This will enable IPv6 by modifying GRUB configuration.\n\n"
                "A backup of /etc/default/grub will be created.\n\n"
                "WARNING: A system reboot will be required for this change to take effect!\n\n"
                "Continue?",
                "Enable IPv6"
            ):
                return

            self.ui.show_infobox("Enabling IPv6 via GRUB...\n\nPlease wait...")

            success = sys_config_mgr.enable_ipv6()

            if success:
                if self.ui.confirm_action(
                    "IPv6 has been enabled in GRUB configuration.\n\n"
                    "A system reboot is required for the change to take effect.\n\n"
                    "Do you want to reboot now?",
                    "Reboot Required"
                ):
                    logger.info("Rebooting system to apply IPv6 enable")
                    self.ui.show_infobox("Rebooting system...")
                    time.sleep(2)
                    os.system("reboot")
                else:
                    self.ui.show_info(
                        "IPv6 enabled in GRUB.\n\n"
                        "Please reboot manually for changes to take effect:\n"
                        "  sudo reboot",
                        "Reboot Required"
                    )
            else:
                self.ui.show_error("Failed to enable IPv6. Check logs for details.")

        except Exception as e:
            logger.error(f"IPv6 enable error: {e}")
            self.ui.show_error(f"Failed to enable IPv6:\n\n{e}")

    def handle_configure_firewall(self):
        """Configure firewall"""
        try:
            sys_config_mgr = self._get_system_config_manager()

            # Check current status
            status = sys_config_mgr.check_firewall_status()

            # Show preset selection
            presets = [
                ("mailcow", "Mailcow (SSH, HTTP, HTTPS, SMTP, IMAP, POP3)"),
                ("nginx", "nginx Proxy Manager (SSH, HTTP, HTTPS, nginx Admin)"),
                ("basic", "Basic Web Server (SSH, HTTP, HTTPS)"),
                ("custom", "Custom (manual configuration)")
            ]

            code, preset = self.ui.d.menu(
                "Select firewall preset:\n\n"
                "This will configure UFW (Uncomplicated Firewall) with appropriate rules.\n\n"
                f"Current status: {'Active' if status['ufw_active'] else 'Inactive'}",
                title="Firewall Configuration",
                choices=presets,
                width=70,
                height=20
            )

            if code != self.ui.d.OK:
                return

            if preset == "custom":
                self.ui.show_info(
                    "Custom firewall configuration:\n\n"
                    "Use the following commands to configure manually:\n"
                    "  ufw allow <port>/<protocol>\n"
                    "  ufw status\n"
                    "  ufw enable",
                    "Custom Configuration"
                )
                return

            # Get preset description
            preset_desc = {
                'mailcow': 'SSH, HTTP, HTTPS, SMTP, IMAP, POP3, and mail-related ports',
                'nginx': 'SSH, HTTP, HTTPS, and nginx admin interface (port 81)',
                'basic': 'SSH, HTTP, and HTTPS only'
            }

            if not self.ui.confirm_action(
                f"This will configure the firewall with the '{preset}' preset.\n\n"
                f"Ports to be allowed:\n  {preset_desc.get(preset, 'Unknown')}\n\n"
                "WARNING: This will reset existing firewall rules!\n\n"
                "SSH (port 22) will always be allowed to prevent lockout.\n\n"
                "Continue?",
                "Configure Firewall"
            ):
                return

            self.ui.show_infobox(f"Configuring firewall with {preset} preset...\n\nPlease wait...")

            success = sys_config_mgr.configure_firewall(preset)

            if success:
                self.ui.show_success(
                    f"Firewall configured successfully with '{preset}' preset!\n\n"
                    "Firewall is now active and enabled on boot.\n\n"
                    "To view rules: sudo ufw status verbose"
                )
                logger.info(f"Firewall configured with {preset} preset via TUI")
            else:
                self.ui.show_error("Firewall configuration failed. Check logs for details.")

        except Exception as e:
            logger.error(f"Firewall configuration error: {e}")
            self.ui.show_error(f"Failed to configure firewall:\n\n{e}")
