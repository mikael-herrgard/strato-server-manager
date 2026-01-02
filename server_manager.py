#!/opt/server-manager/venv/bin/python3
"""
Server Manager - Main Entry Point
Unified TUI application for server management, backups, and disaster recovery
"""

import sys
import os
from pathlib import Path

# Add lib directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.ui import ServerManagerUI
from lib.config import get_config
from lib.utils import logger, check_root, get_hostname, get_ip_address
from lib.backup import BackupManager
from lib.restore import RestoreManager
from lib.installation import InstallationManager
from lib.system_config import SystemConfigManager
from lib.maintenance import MaintenanceManager
from lib.monitoring import MonitoringManager
from lib.scheduling import SchedulingManager
from lib.notifications import NotificationManager

# Import handlers
from lib.handlers import (
    BackupHandlers,
    RestoreHandlers,
    InstallationHandlers,
    SystemHandlers,
    MaintenanceHandlers,
    MonitoringHandlers,
    SchedulingHandlers
)


class ServerManager:
    """Main application controller - thin orchestrator"""

    def __init__(self):
        """Initialize server manager"""
        self.ui = ServerManagerUI("Server Manager")
        self.config = get_config()
        self.running = True

        # Lazy initialization managers
        self.backup_manager = None
        self.restore_manager = None
        self.installation_manager = None
        self.system_config_manager = None
        self.maintenance_manager = None
        self.monitoring_manager = None
        self.scheduling_manager = None
        self.notification_manager = None

        # Initialize handlers (pass manager getters for lazy init)
        self.backup_handlers = BackupHandlers(self.ui, self._get_backup_manager)
        self.restore_handlers = RestoreHandlers(self.ui, self._get_restore_manager)
        self.installation_handlers = InstallationHandlers(self.ui, self._get_installation_manager)
        self.system_handlers = SystemHandlers(self.ui, self._get_system_config_manager)
        self.maintenance_handlers = MaintenanceHandlers(self.ui, self._get_maintenance_manager, self._get_backup_manager)
        self.monitoring_handlers = MonitoringHandlers(self.ui, self._get_monitoring_manager, self._get_restore_manager)
        self.scheduling_handlers = SchedulingHandlers(self.ui, self._get_scheduling_manager, self._get_notification_manager)

        logger.info("Server Manager started")

    # Manager getters (lazy initialization)
    def _get_backup_manager(self) -> BackupManager:
        """Get or create backup manager instance"""
        if self.backup_manager is None:
            try:
                self.backup_manager = BackupManager()
            except Exception as e:
                logger.error(f"Failed to initialize backup manager: {e}")
                self.ui.show_error(f"Failed to initialize backup system:\n\n{e}")
                raise
        return self.backup_manager

    def _get_restore_manager(self) -> RestoreManager:
        """Get or create restore manager instance"""
        if self.restore_manager is None:
            try:
                self.restore_manager = RestoreManager()
            except Exception as e:
                logger.error(f"Failed to initialize restore manager: {e}")
                self.ui.show_error(f"Failed to initialize restore system:\n\n{e}")
                raise
        return self.restore_manager

    def _get_installation_manager(self) -> InstallationManager:
        """Get or create installation manager instance"""
        if self.installation_manager is None:
            try:
                self.installation_manager = InstallationManager()
            except Exception as e:
                logger.error(f"Failed to initialize installation manager: {e}")
                self.ui.show_error(f"Failed to initialize installation system:\n\n{e}")
                raise
        return self.installation_manager

    def _get_system_config_manager(self) -> SystemConfigManager:
        """Get or create system config manager instance"""
        if self.system_config_manager is None:
            try:
                self.system_config_manager = SystemConfigManager()
            except Exception as e:
                logger.error(f"Failed to initialize system config manager: {e}")
                self.ui.show_error(f"Failed to initialize system configuration:\n\n{e}")
                raise
        return self.system_config_manager

    def _get_maintenance_manager(self) -> MaintenanceManager:
        """Get or create maintenance manager instance"""
        if self.maintenance_manager is None:
            try:
                self.maintenance_manager = MaintenanceManager()
            except Exception as e:
                logger.error(f"Failed to initialize maintenance manager: {e}")
                self.ui.show_error(f"Failed to initialize maintenance system:\n\n{e}")
                raise
        return self.maintenance_manager

    def _get_monitoring_manager(self) -> MonitoringManager:
        """Get or create monitoring manager instance"""
        if self.monitoring_manager is None:
            try:
                self.monitoring_manager = MonitoringManager()
            except Exception as e:
                logger.error(f"Failed to initialize monitoring manager: {e}")
                self.ui.show_error(f"Failed to initialize monitoring system:\n\n{e}")
                raise
        return self.monitoring_manager

    def _get_scheduling_manager(self) -> SchedulingManager:
        """Get or create scheduling manager instance"""
        if self.scheduling_manager is None:
            try:
                self.scheduling_manager = SchedulingManager()
            except Exception as e:
                logger.error(f"Failed to initialize scheduling manager: {e}")
                self.ui.show_error(f"Failed to initialize scheduling system:\n\n{e}")
                raise
        return self.scheduling_manager

    def _get_notification_manager(self) -> NotificationManager:
        """Get or create notification manager instance"""
        if self.notification_manager is None:
            try:
                self.notification_manager = NotificationManager()
            except Exception as e:
                logger.error(f"Failed to initialize notification manager: {e}")
                self.ui.show_error(f"Failed to initialize notification system:\n\n{e}")
                raise
        return self.notification_manager

    def run(self):
        """Main application loop"""
        if not check_root():
            self.ui.show_error(
                "This application must be run as root.\n\n"
                "Please run: sudo /opt/server-manager/server_manager.py",
                "Root Required"
            )
            return

        self._check_first_run()

        while self.running:
            try:
                choice = self.ui.show_main_menu()

                if choice == "exit" or choice == "0":
                    if self.ui.confirm_action("Are you sure you want to exit?", "Exit"):
                        self.running = False
                        logger.info("Server Manager exiting")
                elif choice == "1":
                    self._backup_menu()
                elif choice == "2":
                    self._restore_menu()
                elif choice == "3":
                    self._installation_menu()
                elif choice == "4":
                    self._system_menu()
                elif choice == "5":
                    self._maintenance_menu()
                elif choice == "6":
                    self._monitoring_menu()
                elif choice == "7":
                    self._scheduling_menu()
                elif choice == "8":
                    self._settings_menu()

            except KeyboardInterrupt:
                if self.ui.confirm_action("Are you sure you want to exit?", "Exit"):
                    self.running = False
                    logger.info("Server Manager interrupted by user")

            except Exception as e:
                logger.error(f"Error in main loop: {e}", exc_info=True)
                self.ui.show_error(f"An error occurred: {e}", "Error")

    def _check_first_run(self):
        """Check if this is first run and show welcome message"""
        state_file = Path("/opt/server-manager/state/first_run")

        if not state_file.exists():
            hostname = get_hostname()
            ip = get_ip_address()

            welcome_msg = f"""Welcome to Server Manager v1.0!

This is your first time running the application.

Server Information:
  Hostname: {hostname}
  IP Address: {ip}

This tool provides:
  • Automated backups (nginx, Mailcow, application)
  • Disaster recovery and restore
  • Service installation and configuration
  • System maintenance and monitoring

Navigate using arrow keys and Enter.
Press ESC or Cancel to go back.

For help, see: /opt/server-manager/README.md
"""

            self.ui.show_info(welcome_msg, "Welcome")

            # Create state directory and mark first run complete
            state_file.parent.mkdir(parents=True, exist_ok=True)
            state_file.touch()

    # Menu handlers - delegate to handler classes
    def _backup_menu(self):
        """Show backup menu"""
        while True:
            choice = self.ui.show_backup_menu()

            if choice == "1":
                self.backup_handlers.handle_backup_nginx()
            elif choice == "2":
                self.backup_handlers.handle_backup_mailcow()
            elif choice == "3":
                self.backup_handlers.handle_view_backup_status()
            elif choice == "4":
                # Navigate to scheduling menu
                self._scheduling_menu()
            elif choice == "0" or choice == "back":
                break

    def _restore_menu(self):
        """Show restore menu"""
        while True:
            choice = self.ui.show_restore_menu()

            if choice == "1":
                self.restore_handlers.handle_restore_nginx()
            elif choice == "2":
                self.restore_handlers.handle_restore_mailcow()
            elif choice == "3":
                self.restore_handlers.handle_list_backups()
            elif choice == "0" or choice == "back":
                break

    def _installation_menu(self):
        """Show installation menu"""
        while True:
            choice = self.ui.show_installation_menu()

            if choice == "1":
                self.installation_handlers.handle_install_docker()
            elif choice == "2":
                self.installation_handlers.handle_install_nginx()
            elif choice == "3":
                self.installation_handlers.handle_install_mailcow()
            elif choice == "4":
                self._install_portainer_placeholder()
            elif choice == "5":
                self.installation_handlers.handle_check_prerequisites()
            elif choice == "0" or choice == "back":
                break

    def _system_menu(self):
        """Show system configuration menu"""
        while True:
            choice = self.ui.show_system_menu()

            if choice == "1":
                self.system_handlers.handle_disable_ipv6()
            elif choice == "2":
                self.system_handlers.handle_enable_ipv6()
            elif choice == "3":
                # System Information - use monitoring handler
                self.monitoring_handlers.handle_system_info()
            elif choice == "0" or choice == "back":
                break

    def _maintenance_menu(self):
        """Show maintenance menu"""
        while True:
            choice = self.ui.show_maintenance_menu()

            if choice == "1":
                self.maintenance_handlers.handle_update_nginx()
            elif choice == "2":
                self.maintenance_handlers.handle_update_mailcow()
            elif choice == "3":
                self.maintenance_handlers.handle_update_system()
            elif choice == "4":
                self.maintenance_handlers.handle_cleanup_backups()
            elif choice == "5":
                self.maintenance_handlers.handle_cleanup_docker()
            elif choice == "0" or choice == "back":
                break

    def _monitoring_menu(self):
        """Show monitoring menu"""
        while True:
            choice = self.ui.show_monitoring_menu()

            if choice == "1":
                self.monitoring_handlers.handle_service_status()
            elif choice == "2":
                self.monitoring_handlers.handle_disk_usage()
            elif choice == "3":
                self.monitoring_handlers.handle_backup_history()
            elif choice == "4":
                self.monitoring_handlers.handle_container_stats()
            elif choice == "5":
                self._view_logs()
            elif choice == "0" or choice == "back":
                break

    def _scheduling_menu(self):
        """Show scheduling & automation menu"""
        while True:
            choice = self.ui.show_scheduling_menu()

            if choice == "1":
                self.scheduling_handlers.handle_view_schedules()
            elif choice == "2":
                self.scheduling_handlers.handle_schedule_backup()
            elif choice == "3":
                self.scheduling_handlers.handle_schedule_cleanup()
            elif choice == "4":
                self.scheduling_handlers.handle_remove_schedule()
            elif choice == "5":
                self.scheduling_handlers.handle_configure_notifications()
            elif choice == "6":
                self.scheduling_handlers.handle_test_notification()
            elif choice == "7":
                self.scheduling_handlers.handle_notification_status()
            elif choice == "0" or choice == "back":
                break

    def _settings_menu(self):
        """Show settings menu"""
        while True:
            choice = self.ui.show_settings_menu()

            if choice == "1":
                # Navigate to notification configuration
                self.scheduling_handlers.handle_configure_notifications()
            elif choice == "2":
                self._set_retention()
            elif choice == "3":
                self._view_config()
            elif choice == "4":
                self._edit_config_placeholder()
            elif choice == "0" or choice == "back":
                break

    # Placeholder methods (not yet refactored/implemented)
    def _install_portainer_placeholder(self):
        """Install Portainer (placeholder)"""
        self.ui.show_info(
            "Portainer installation will be implemented in a future phase.",
            "Coming Soon"
        )

    def _network_settings_placeholder(self):
        """Network settings (placeholder)"""
        self.ui.show_info(
            "Network settings configuration will be implemented in a future phase.",
            "Coming Soon"
        )

    def _cleanup_backups_placeholder(self):
        """Cleanup old backups (placeholder)"""
        self.ui.show_info(
            "Automated backup cleanup will be implemented in Phase 6.",
            "Coming Soon"
        )

    def _backup_history_placeholder(self):
        """View backup history (placeholder)"""
        self.ui.show_info(
            "Backup history viewing will be implemented in Phase 6.",
            "Coming Soon"
        )

    def _configure_rsync_placeholder(self):
        """Configure rsync settings (placeholder)"""
        self.ui.show_info(
            "rsync configuration will be implemented in a future phase.",
            "Coming Soon"
        )

    def _configure_backup_schedule_placeholder(self):
        """Configure backup schedule (placeholder - now redirects to scheduling)"""
        self._scheduling_menu()

    def _set_backup_retention_placeholder(self):
        """Set backup retention (placeholder)"""
        self.ui.show_info(
            "Backup retention configuration will be implemented in a future phase.\n\n"
            "For now, use the scheduled cleanup feature:\n"
            "  Main Menu → Scheduling & Automation → Schedule Cleanup",
            "Coming Soon"
        )

    def _edit_config_placeholder(self):
        """Edit configuration file (placeholder)"""
        self.ui.show_info(
            "Direct configuration editing will be implemented in a future phase.\n\n"
            "For now, you can manually edit:\n"
            "  /opt/server-manager/config/settings.yaml",
            "Coming Soon"
        )

    # Keep these simple helper methods in main file
    def _view_logs(self):
        """View application logs"""
        log_file = "/opt/server-manager/logs/server-manager.log"

        if not os.path.exists(log_file):
            self.ui.show_error(f"Log file not found: {log_file}")
            return

        try:
            with open(log_file, 'r') as f:
                # Read last 100 lines
                lines = f.readlines()
                log_content = ''.join(lines[-100:])

            self.ui.show_scrollable_text(log_content, "Application Logs (Last 100 lines)")

        except Exception as e:
            logger.error(f"Failed to read logs: {e}")
            self.ui.show_error(f"Failed to read logs:\n\n{e}")

    def _view_config(self):
        """View current configuration"""
        config_file = "/opt/server-manager/config/settings.yaml"

        if not os.path.exists(config_file):
            self.ui.show_error(f"Configuration file not found: {config_file}")
            return

        try:
            with open(config_file, 'r') as f:
                config_content = f.read()

            self.ui.show_scrollable_text(config_content, "Current Configuration")

        except Exception as e:
            logger.error(f"Failed to read config: {e}")
            self.ui.show_error(f"Failed to read configuration:\n\n{e}")

    def _set_retention(self):
        """Edit backup retention policy"""
        try:
            # Get current retention values
            current_retention = self.config.get('borg.retention', {
                'daily': 7,
                'weekly': 4,
                'monthly': 6
            })

            # Get daily retention
            code, daily_str = self.ui.d.inputbox(
                "Enter number of daily backups to keep:\n\n"
                "This determines how many of the most recent daily backups will be retained.",
                height=12,
                width=60,
                init=str(current_retention.get('daily', 7)),
                title="Set Daily Retention"
            )

            if code != self.ui.d.OK:
                return

            # Validate daily input
            try:
                daily = int(daily_str)
                if daily < 1:
                    raise ValueError("Must be at least 1")
            except ValueError as e:
                self.ui.show_error(f"Invalid daily retention value.\n\nMust be a positive integer.")
                return

            # Get weekly retention
            code, weekly_str = self.ui.d.inputbox(
                "Enter number of weekly backups to keep:\n\n"
                "This determines how many weekly backups will be retained.",
                height=12,
                width=60,
                init=str(current_retention.get('weekly', 4)),
                title="Set Weekly Retention"
            )

            if code != self.ui.d.OK:
                return

            # Validate weekly input
            try:
                weekly = int(weekly_str)
                if weekly < 1:
                    raise ValueError("Must be at least 1")
            except ValueError as e:
                self.ui.show_error(f"Invalid weekly retention value.\n\nMust be a positive integer.")
                return

            # Get monthly retention
            code, monthly_str = self.ui.d.inputbox(
                "Enter number of monthly backups to keep:\n\n"
                "This determines how many monthly backups will be retained.",
                height=12,
                width=60,
                init=str(current_retention.get('monthly', 6)),
                title="Set Monthly Retention"
            )

            if code != self.ui.d.OK:
                return

            # Validate monthly input
            try:
                monthly = int(monthly_str)
                if monthly < 1:
                    raise ValueError("Must be at least 1")
            except ValueError as e:
                self.ui.show_error(f"Invalid monthly retention value.\n\nMust be a positive integer.")
                return

            # Confirm changes
            if not self.ui.confirm_action(
                "Confirm new retention policy:\n\n"
                f"  Daily:   {current_retention.get('daily', 7)} → {daily}\n"
                f"  Weekly:  {current_retention.get('weekly', 4)} → {weekly}\n"
                f"  Monthly: {current_retention.get('monthly', 6)} → {monthly}\n\n"
                "These settings will be applied to future backup cleanups.\n\n"
                "Save changes?",
                "Confirm Retention Policy"
            ):
                return

            # Update configuration
            self.config.set('borg.retention.daily', daily)
            self.config.set('borg.retention.weekly', weekly)
            self.config.set('borg.retention.monthly', monthly)

            # Save configuration
            if self.config.save_config():
                self.ui.show_success(
                    "Retention policy updated successfully!\n\n"
                    f"New policy:\n"
                    f"  • Daily: {daily} backups\n"
                    f"  • Weekly: {weekly} backups\n"
                    f"  • Monthly: {monthly} backups\n\n"
                    "These settings will be used for future backup cleanups."
                )
                logger.info(f"Retention policy updated: daily={daily}, weekly={weekly}, monthly={monthly}")
            else:
                self.ui.show_error("Failed to save configuration.\n\nCheck logs for details.")

        except Exception as e:
            logger.error(f"Set retention error: {e}")
            self.ui.show_error(f"Failed to update retention policy:\n\n{e}")


def main():
    """Main entry point"""
    app = ServerManager()
    app.run()


if __name__ == "__main__":
    main()
