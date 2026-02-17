"""
Backup Menu Handlers
Handles all backup-related menu operations
"""

from ..utils import logger


class BackupHandlers:
    """Handles backup menu operations"""

    def __init__(self, ui, backup_manager):
        """
        Initialize backup handlers

        Args:
            ui: ServerManagerUI instance
            backup_manager: BackupManager instance (or callable to get it)
        """
        self.ui = ui
        self._backup_manager = backup_manager

    def _get_backup_manager(self):
        """Get backup manager (lazy initialization support)"""
        if callable(self._backup_manager):
            return self._backup_manager()
        return self._backup_manager

    def handle_backup_nginx(self):
        """Backup nginx Proxy Manager"""
        if not self.ui.confirm_action(
            "This will create a backup of nginx Proxy Manager.\n\n"
            "The backup will be stored on your rsync server.\n\n"
            "This may take 2-5 minutes.\n\n"
            "Continue?",
            "Backup nginx"
        ):
            return

        try:
            backup_mgr = self._get_backup_manager()

            self.ui.show_infobox("Creating nginx backup...\n\nThis may take a few minutes.")

            success = backup_mgr.backup_nginx(verify=True)

            if success:
                self.ui.show_success(
                    "nginx backup completed successfully!\n\n"
                    "The backup has been stored on your rsync server and verified."
                )
                logger.info("nginx backup completed via TUI")
            else:
                self.ui.show_error("nginx backup failed. Check logs for details.")

        except Exception as e:
            logger.error(f"nginx backup error: {e}")
            self.ui.show_error(f"Backup failed:\n\n{e}")

    def handle_backup_mailcow(self):
        """Backup Mailcow"""
        # Show backup type selection
        backup_types = [
            ("all", "Complete backup (recommended)", True),
            ("config", "Configuration only", False),
            ("mail", "Mail data only", False),
            ("db", "Database only", False)
        ]

        backup_type = self.ui.show_radiolist(
            backup_types,
            "Mailcow Backup Type",
            "Select Mailcow backup type:\n\n"
            "Complete backup includes all data and is recommended."
        )

        if backup_type is None:
            return

        if not self.ui.confirm_action(
            f"This will create a {backup_type} backup of Mailcow.\n\n"
            "The backup will be stored on your rsync server.\n\n"
            "This may take 15-60 minutes depending on your mail volume.\n\n"
            "Continue?",
            "Backup Mailcow"
        ):
            return

        try:
            backup_mgr = self._get_backup_manager()

            self.ui.show_infobox(
                f"Creating Mailcow backup ({backup_type})...\n\n"
                "This may take 15-60 minutes.\n"
                "Please be patient..."
            )

            success = backup_mgr.backup_mailcow(backup_type=backup_type, verify=True)

            if success:
                self.ui.show_success(
                    f"Mailcow backup ({backup_type}) completed successfully!\n\n"
                    "The backup has been stored on your rsync server and verified."
                )
                logger.info(f"Mailcow backup ({backup_type}) completed via TUI")
            else:
                self.ui.show_error("Mailcow backup failed. Check logs for details.")

        except Exception as e:
            logger.error(f"Mailcow backup error: {e}")
            self.ui.show_error(f"Backup failed:\n\n{e}")

    def handle_backup_mailcow_directory(self):
        """Backup Mailcow directory (configuration and certificates)"""
        if not self.ui.confirm_action(
            "This will create a backup of the Mailcow installation directory.\n\n"
            "This includes:\n"
            "  • Configuration files (mailcow.conf)\n"
            "  • SSL certificates\n"
            "  • DKIM keys\n"
            "  • Docker compose files\n\n"
            "The backup will be stored on your rsync server.\n\n"
            "This may take 2-5 minutes.\n\n"
            "Continue?",
            "Backup Mailcow Directory"
        ):
            return

        try:
            backup_mgr = self._get_backup_manager()

            self.ui.show_infobox("Creating Mailcow directory backup...\n\nThis may take a few minutes.")

            success = backup_mgr.backup_mailcow_directory(verify=True)

            if success:
                self.ui.show_success(
                    "Mailcow directory backup completed successfully!\n\n"
                    "The backup has been stored on your rsync server and verified."
                )
                logger.info("Mailcow directory backup completed via TUI")
            else:
                self.ui.show_error("Mailcow directory backup failed. Check logs for details.")

        except Exception as e:
            logger.error(f"Mailcow directory backup error: {e}")
            self.ui.show_error(f"Backup failed:\n\n{e}")

    def handle_backup_server_manager(self):
        """Backup Server-Manager configuration"""
        if not self.ui.confirm_action(
            "This will create a backup of Server-Manager configuration.\n\n"
            "The backup includes:\n"
            "  • settings.yaml\n"
            "  • notifications.yaml\n\n"
            "The backup will be stored on your rsync server.\n\n"
            "Continue?",
            "Backup Server-Manager"
        ):
            return

        try:
            backup_mgr = self._get_backup_manager()

            self.ui.show_infobox("Creating Server-Manager config backup...\n\nThis may take a few minutes.")

            success = backup_mgr.backup_server_manager(verify=True)

            if success:
                self.ui.show_success(
                    "Server-Manager config backup completed successfully!\n\n"
                    "The backup has been stored on your rsync server and verified."
                )
                logger.info("Server-Manager config backup completed via TUI")
            else:
                self.ui.show_error("Server-Manager config backup failed. Check logs for details.")

        except Exception as e:
            logger.error(f"Server-Manager config backup error: {e}")
            self.ui.show_error(f"Backup failed:\n\n{e}")

    def handle_backup_all(self):
        """Backup all services in sequence"""
        if not self.ui.confirm_action(
            "This will backup ALL services in sequence:\n\n"
            "  1. nginx Proxy Manager\n"
            "  2. Mailcow Directory\n"
            "  3. Mailcow Data (complete)\n"
            "  4. Server-Manager Config\n\n"
            "This may take 30-90 minutes depending on data volume.\n\n"
            "Continue?",
            "Backup All Services"
        ):
            return

        try:
            backup_mgr = self._get_backup_manager()

            results = {}

            # 1. nginx
            self.ui.show_infobox("Backing up nginx Proxy Manager...\n\n(Step 1 of 4)")
            results['nginx'] = backup_mgr.backup_nginx(verify=True)

            # 2. Mailcow Directory
            self.ui.show_infobox("Backing up Mailcow Directory...\n\n(Step 2 of 4)")
            results['mailcow-directory'] = backup_mgr.backup_mailcow_directory(verify=True)

            # 3. Mailcow Data
            self.ui.show_infobox("Backing up Mailcow Data...\n\n(Step 3 of 4)\nThis may take a while...")
            results['mailcow'] = backup_mgr.backup_mailcow(backup_type='all', verify=True)

            # 4. Server-Manager
            self.ui.show_infobox("Backing up Server-Manager Config...\n\n(Step 4 of 4)")
            results['server-manager'] = backup_mgr.backup_server_manager(verify=True)

            # Build summary
            succeeded = sum(1 for v in results.values() if v)
            total = len(results)

            summary = f"Backup All Services Complete: {succeeded}/{total} succeeded\n\n"
            for service, success in results.items():
                icon = "OK" if success else "FAILED"
                summary += f"  [{icon}] {service}\n"

            if succeeded == total:
                self.ui.show_success(summary)
                logger.info("Backup all services completed successfully via TUI")
            else:
                summary += "\nCheck logs for details on failed backups."
                self.ui.show_error(summary)
                logger.warning(f"Backup all services: {succeeded}/{total} succeeded")

        except Exception as e:
            logger.error(f"Backup all services error: {e}")
            self.ui.show_error(f"Backup failed:\n\n{e}")

    def handle_view_backup_status(self):
        """View backup status"""
        try:
            backup_mgr = self._get_backup_manager()

            self.ui.show_infobox("Retrieving backup status from remote Borg archive...\n\nPlease wait...")

            status = backup_mgr.get_backup_status()

            # Build status text
            status_text = "Backup Status (Remote rsync/Borg)\n"
            status_text += "=" * 95 + "\n"
            status_text += "Storage: Remote rsync server via Borg repositories\n\n"

            for service, info in status.items():
                status_text += f"{service.upper()}:\n"
                status_text += f"  Repository: {info['repository']}\n"
                status_text += f"  Backup Count: {info['backup_count']}\n"
                if info['latest_backup']:
                    status_text += f"  Latest Backup: {info['latest_backup']}\n"
                else:
                    status_text += "  Latest Backup: None\n"
                status_text += "\n"

            self.ui.show_scrollable_text(status_text, "Backup Status (Remote rsync/Borg)")

        except Exception as e:
            logger.error(f"Failed to get backup status: {e}")
            self.ui.show_error(f"Failed to get backup status:\n\n{e}")
